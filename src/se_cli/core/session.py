"""Sesión con Solid Edge: conexión, verificación, reconexión y puerta única de llamadas.

Todo corre en el hilo STA único. Los comandos usan `Sesion.llamar(fn)`; `fn` recibe la
`Application` (late binding) y tiene que devolver datos planos, nunca objetos COM.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from se_cli.core.errors import (
    MK_E_UNAVAILABLE,
    NoConectado,
    Ocupado,
    SeError,
    hresult_de,
    traducir,
)
from se_cli.core.retry import ESPERA_POR_DEFECTO, INTENTOS_POR_DEFECTO, reintentar
from se_cli.core.sta import HiloSta, sta_por_defecto

T = TypeVar("T")

PROGID = "SolidEdge.Application"


def enganchar_instancia() -> Any:
    """Enganchate a la instancia abierta de Solid Edge sin lanzar nada (late binding).

    Usa `pythoncom.GetActiveObject` y envuelve el `IDispatch` con `dynamic.Dispatch`:
    nunca `gencache.EnsureDispatch`, porque gen_py enlaza mal `DrawingViews`.
    """
    import pythoncom
    from win32com.client import dynamic

    activa = pythoncom.GetActiveObject(PROGID)
    return dynamic.Dispatch(activa.QueryInterface(pythoncom.IID_IDispatch))


def lanzar_instancia() -> Any:
    """Lanzá Solid Edge (solo con `lanzar=True` explícito), también con late binding."""
    from win32com.client import dynamic

    return dynamic.Dispatch(PROGID)


class Sesion:
    """Conexión a Solid Edge sobre el hilo STA único.

    `proveedor` engancha a la instancia abierta y `lanzador` lanza una nueva; los dos son
    inyectables para usar el COM falso en los tests.
    """

    def __init__(
        self,
        *,
        sta: HiloSta | None = None,
        proveedor: Callable[[], Any] = enganchar_instancia,
        lanzador: Callable[[], Any] = lanzar_instancia,
        intentos: int = INTENTOS_POR_DEFECTO,
        espera: float = ESPERA_POR_DEFECTO,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sta = sta or sta_por_defecto()
        self._proveedor = proveedor
        self._lanzador = lanzador
        self._intentos = intentos
        self._espera = espera
        self._sleep = sleep
        self._app: Any = None

    # Todo lo que sigue que toca `self._app` corre en el hilo STA.

    def _reintentar(self, fn: Callable[[], T]) -> T:
        return reintentar(fn, self._intentos, self._espera, sleep=self._sleep)

    def _enganchar(self) -> Any:
        try:
            return self._proveedor()
        except Exception as error:
            hresult = hresult_de(error)
            motivo = (
                "No hay una instancia de Solid Edge abierta."
                if hresult in (None, MK_E_UNAVAILABLE)
                else "No se pudo enganchar a Solid Edge."
            )
            raise NoConectado(motivo, hresult=hresult) from error

    def conectar(self, lanzar: bool = False) -> dict[str, Any]:
        """Enganchate a la instancia abierta; con `lanzar=True` la lanza si no hay ninguna.

        Sin `lanzar` y sin instancia levanta `NoConectado` (exit 3) y no lanza nada.
        Devuelve datos planos: `{"version", "nombre", "lanzada"}`.
        """
        return self._sta.ejecutar(self._conectar, lanzar)

    def _conectar(self, lanzar: bool) -> dict[str, Any]:
        lanzada = False
        try:
            app = self._enganchar()
        except NoConectado:
            if not lanzar:
                raise
            try:
                app = self._lanzador()
            except Exception as error:
                raise NoConectado(
                    "No se pudo lanzar Solid Edge.", hresult=hresult_de(error)
                ) from error
            lanzada = True
        self._app = app
        app = self._app_verificada()
        if lanzada:
            # Verificado en vivo: una instancia lanzada por automatización arranca oculta
            # (`Visible=False`) y sigue viva al terminar `se`; se la deja visible.
            self._reintentar(lambda: setattr(app, "Visible", True))
        return {
            "version": str(self._reintentar(lambda: app.Version)),
            "nombre": str(self._reintentar(lambda: app.Name)),
            "lanzada": lanzada,
        }

    def _app_verificada(self) -> Any:
        """Devolvé la app tras leer `.Version`; si falla, reconectá una vez."""
        if self._app is None:
            raise NoConectado("No hay sesión con Solid Edge; conectate primero.")
        try:
            self._reintentar(lambda: self._app.Version)
        except Exception as error:
            if isinstance(error, Ocupado):
                raise
            self._app = None
            try:
                self._app = self._enganchar()
                self._reintentar(lambda: self._app.Version)
            except Exception as segundo:
                self._app = None
                if isinstance(segundo, NoConectado):
                    raise
                raise NoConectado(
                    "La instancia de Solid Edge no responde.", hresult=hresult_de(segundo)
                ) from segundo
        return self._app

    @property
    def app(self) -> Any:
        """`Application` verificada. Solo se puede usar dentro del hilo STA (vía `llamar`)."""
        if not self._sta.en_hilo():
            raise SeError("`app` solo se usa dentro de `llamar` (hilo STA).")
        return self._app_verificada()

    def llamar(self, fn: Callable[[Any], T], *, reintentar_todo: bool = True) -> T:
        """Puerta única: corré `fn(app)` en el hilo STA con la app ya verificada.

        Reintenta ante "Solid Edge ocupado" y traduce todo error a `SeError`. Con
        `reintentar_todo=False` no repite `fn` (para comandos que modifican varias cosas;
        ahí conviene usar `core.retry.reintentar` por llamada).
        """

        def correr() -> T:
            app = self._app_verificada()
            if reintentar_todo:
                return self._reintentar(lambda: fn(app))
            return fn(app)

        try:
            return self._sta.ejecutar(correr)
        except SeError:
            raise
        except Exception as error:
            raise traducir(error) from error

    @contextlib.contextmanager
    def sin_alertas(self) -> Iterator[None]:
        """Poné `DisplayAlerts=False` y restaurá el valor previo al salir, aun con excepción."""
        previo = self.llamar(lambda app: app.DisplayAlerts)
        self.llamar(lambda app: setattr(app, "DisplayAlerts", False))
        try:
            yield
        finally:
            self.llamar(lambda app: setattr(app, "DisplayAlerts", previo))

    def cerrar(self) -> None:
        """Soltá la referencia a la app en el hilo STA. No cierra Solid Edge."""
        if self._app is not None:
            self._sta.ejecutar(self._soltar)

    def _soltar(self) -> None:
        self._app = None


__all__ = ["PROGID", "Sesion", "enganchar_instancia", "lanzar_instancia"]
