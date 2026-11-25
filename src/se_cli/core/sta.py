"""Hilo STA único: todo acceso COM del proyecto corre en un solo worker.

Los objetos COM viven y mueren en ese hilo; hacia afuera solo salen datos planos.
"""

from __future__ import annotations

import atexit
import contextlib
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, wait
from typing import Any, TypeVar

from se_cli.core import plazo as reloj
from se_cli.core.errors import HRESULTS_CANCELADO, SeError, TiempoAgotado, hresult_de

T = TypeVar("T")
TICK = 0.2
GRACIA = 5.0
CANCELAR_POR_COM = True

Tarea = tuple[Callable[..., Any], tuple, dict, Future, reloj.Plazo | None]


def _habilitar() -> None:
    import pythoncom

    # pywin32 pasa NULL a ole32; su envoltorio Python no recibe argumentos.
    pythoncom.CoEnableCallCancellation()


def _cancelar(tid: int) -> None:
    import ctypes

    ctypes.windll.ole32.CoCancelCall(tid, 0)


def _com_real() -> tuple[Callable[[], None], Callable[[], None]]:
    """Devolvé (init, uninit) de pythoncom; el import es perezoso."""
    import pythoncom

    def iniciar() -> None:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)

    return iniciar, pythoncom.CoUninitialize


class HiloSta:
    """Worker dedicado con `CoInitializeEx(COINIT_APARTMENTTHREADED)`.

    Arranca perezoso en el primer `ejecutar`. `init` y `uninit` son inyectables para testear
    sin pywin32: por defecto usan `pythoncom`.
    """

    def __init__(
        self,
        init: Callable[[], None] | None = None,
        uninit: Callable[[], None] | None = None,
        *,
        habilitar: Callable[[], None] = _habilitar,
        cancelar: Callable[[int], None] = _cancelar,
        gracia: float = GRACIA,
    ) -> None:
        self._init = init
        self._uninit = uninit
        self._habilitar = habilitar
        self._cancelar = cancelar
        self._gracia = gracia
        self._cola: queue.Queue[Tarea | None] = queue.Queue()
        self._hilo: threading.Thread | None = None
        self._candado = threading.Lock()
        self._turno = threading.Lock()
        self._local = threading.local()
        self._listo = threading.Event()
        self._error_init: BaseException | None = None
        self._cerrado = False
        self._generacion = 0

    @property
    def generacion(self) -> int:
        return self._generacion

    @property
    def ident(self) -> int | None:
        """Identificador del hilo STA, o None si todavía no arrancó."""
        return self._hilo.ident if self._hilo else None

    def en_hilo(self) -> bool:
        """True si el llamador es el propio hilo STA vigente."""
        return getattr(self._local, "generacion", None) == self._generacion

    def _arrancar(self) -> None:
        with self._candado:
            if self._cerrado:
                raise SeError("El hilo STA ya está cerrado.")
            if self._hilo is not None:
                return
            if self._init is None or self._uninit is None:
                self._init, self._uninit = _com_real()
            self._hilo = threading.Thread(
                target=self._bucle,
                args=(self._cola, self._generacion),
                name="se-sta",
                daemon=True,
            )
            self._hilo.start()
            if self._generacion == 0:
                atexit.register(self.cerrar)
        self._listo.wait()

    def _bucle(self, cola: queue.Queue[Tarea | None], generacion: int) -> None:
        self._local.generacion = generacion
        try:
            self._init()
        except BaseException as error:
            self._error_init = error
            self._listo.set()
            return
        self._listo.set()
        habilitada = False
        try:
            while generacion == self._generacion:
                tarea = cola.get()
                if tarea is None:
                    break
                fn, args, kwargs, futuro, estado = tarea
                try:
                    reloj.inicio_tarea(estado)
                    if estado is not None and CANCELAR_POR_COM and not habilitada:
                        self._habilitar()
                        habilitada = True
                    resultado = fn(*args, **kwargs)
                    reloj.comprobar_cancelacion()
                except BaseException as error:
                    futuro.set_exception(error)
                else:
                    futuro.set_result(resultado)
                finally:
                    reloj.fin_tarea()
        finally:
            self._uninit()

    def ejecutar(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Corré la tarea en el STA sin plazo."""
        return self.ejecutar_con_plazo(None, fn, *args, **kwargs)

    def ejecutar_con_plazo(
        self, plazo: float | None, fn: Callable[..., T], /, *args: Any, **kwargs: Any
    ) -> T:
        """Corré la tarea en el STA y vigilá su plazo de inactividad, si se indicó."""
        if hasattr(self._local, "generacion"):
            reloj.comprobar_cancelacion()
            return fn(*args, **kwargs)
        # Solo se vigila la tarea en curso. Las otras esperan su turno sin consumir plazo.
        with self._turno:
            self._arrancar()
            if self._error_init is not None:
                raise SeError(
                    f"No se pudo inicializar COM: {self._error_init}"
                ) from self._error_init
            estado = reloj.Plazo(plazo) if plazo is not None else None
            futuro: Future[T] = Future()
            with self._candado:
                if self._cerrado:
                    raise SeError("El hilo STA ya está cerrado.")
                self._cola.put((fn, args, kwargs, futuro, estado))
                tid = self._hilo.native_id
            if estado is None:
                return futuro.result()
            return self._vigilar(futuro, estado, tid)

    def _vigilar(self, futuro: Future[T], estado: reloj.Plazo, tid: int) -> T:
        while True:
            espera = min(TICK, max(0, estado.latido + estado.segundos - time.monotonic()))
            if estado.pausas:
                espera = TICK
            try:
                return futuro.result(timeout=espera)
            except TimeoutError:
                if futuro.done():
                    return futuro.result()
                if estado.vencer():
                    break

        if CANCELAR_POR_COM:
            limite = estado.inicio_cancelacion + self._gracia
            while not futuro.done() and time.monotonic() < limite:
                # Un fallo al solicitar la cancelación no debe impedir el abandono.
                with contextlib.suppress(OSError):
                    self._cancelar(tid)
                esperar = min(TICK, max(0, limite - time.monotonic()))
                wait((futuro,), timeout=esperar)
            if futuro.done():
                causa = futuro.exception()
                hr = hresult_de(causa)
                hr = hr if hr in HRESULTS_CANCELADO else None
                error = estado.error(hresult=hr)
                if isinstance(causa, TiempoAgotado):
                    error.details.update(
                        (k, v) for k, v in causa.details.items() if k not in error.details
                    )
                raise error from causa

        with self._candado:
            self._generacion += 1
            # Despertá también al worker si finalizó justo al decidir el abandono.
            self._cola.put(None)
            self._cola = queue.Queue()
            self._hilo = None
            self._listo = threading.Event()
            self._error_init = None
        raise estado.error("abandonada")

    def cerrar(self) -> None:
        """Terminá el worker vigente y esperá hasta cinco segundos. Idempotente."""
        with self._candado:
            if self._cerrado:
                return
            self._cerrado = True
            hilo = self._hilo
            if hilo is not None:
                self._cola.put(None)
        if hilo is not None and threading.get_ident() != hilo.ident:
            hilo.join(timeout=5)
        atexit.unregister(self.cerrar)

    def __enter__(self) -> HiloSta:
        return self

    def __exit__(self, *_: object) -> None:
        self.cerrar()


_por_defecto: HiloSta | None = None
_candado_global = threading.Lock()


def sta_por_defecto() -> HiloSta:
    """Hilo STA compartido del proceso (se crea la primera vez que se pide)."""
    global _por_defecto
    with _candado_global:
        if _por_defecto is None or _por_defecto._cerrado:
            _por_defecto = HiloSta()
        return _por_defecto
