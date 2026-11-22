"""Hilo STA único: todo acceso COM del proyecto corre en un solo worker.

Los objetos COM viven y mueren en ese hilo; hacia afuera solo salen datos planos.
"""

from __future__ import annotations

import atexit
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any, TypeVar

from se_cli.core.errors import SeError

T = TypeVar("T")


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
    ) -> None:
        self._init = init
        self._uninit = uninit
        self._cola: queue.Queue[tuple[Callable[..., Any], tuple, dict, Future] | None] = (
            queue.Queue()
        )
        self._hilo: threading.Thread | None = None
        self._candado = threading.Lock()
        self._listo = threading.Event()
        self._error_init: BaseException | None = None
        self._cerrado = False

    @property
    def ident(self) -> int | None:
        """Identificador del hilo STA, o None si todavía no arrancó."""
        return self._hilo.ident if self._hilo else None

    def en_hilo(self) -> bool:
        """True si el llamador es el propio hilo STA."""
        return self._hilo is not None and threading.get_ident() == self._hilo.ident

    def _arrancar(self) -> None:
        with self._candado:
            if self._cerrado:
                raise SeError("El hilo STA ya está cerrado.")
            if self._hilo is not None:
                return
            if self._init is None or self._uninit is None:
                self._init, self._uninit = _com_real()
            self._hilo = threading.Thread(target=self._bucle, name="se-sta", daemon=True)
            self._hilo.start()
            atexit.register(self.cerrar)
        self._listo.wait()

    def _bucle(self) -> None:
        try:
            self._init()
        except BaseException as error:
            self._error_init = error
            self._listo.set()
            return
        self._listo.set()
        try:
            while True:
                tarea = self._cola.get()
                if tarea is None:
                    break
                fn, args, kwargs, futuro = tarea
                if not futuro.set_running_or_notify_cancel():
                    continue
                try:
                    futuro.set_result(fn(*args, **kwargs))
                except BaseException as error:
                    futuro.set_exception(error)
        finally:
            self._uninit()

    def ejecutar(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Corré `fn(*args, **kwargs)` en el hilo STA y devolvé su resultado.

        Relanza en el hilo llamador la excepción que haya levantado `fn`. Si se llama desde
        el propio hilo STA ejecuta directo, sin encolar (evita el deadlock).
        """
        if self.en_hilo():
            return fn(*args, **kwargs)
        self._arrancar()
        if self._error_init is not None:
            raise SeError(f"No se pudo inicializar COM: {self._error_init}") from self._error_init
        futuro: Future = Future()
        with self._candado:
            if self._cerrado:
                raise SeError("El hilo STA ya está cerrado.")
            self._cola.put((fn, args, kwargs, futuro))
        return futuro.result()

    def cerrar(self) -> None:
        """Terminá el worker (`CoUninitialize` incluido) y esperá a que salga. Idempotente."""
        with self._candado:
            if self._cerrado:
                return
            self._cerrado = True
            hilo = self._hilo
            if hilo is not None:
                self._cola.put(None)
        if hilo is not None and threading.get_ident() != hilo.ident:
            hilo.join()
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
