"""Latido y cancelación cooperativa de una tarea del STA."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from se_cli.core.errors import TiempoAgotado

_local = threading.local()


class Plazo:
    def __init__(self, segundos: float) -> None:
        self.segundos = segundos
        self.latido = time.monotonic()
        self.inicio_cancelacion: float | None = None
        self.pausas = 0
        self.candado = threading.RLock()
        self.apartado: str | None = None
        self.resultados_del_lote: Callable[[TiempoAgotado], list[dict]] | None = None

    def vencer(self) -> bool:
        with self.candado:
            ahora = time.monotonic()
            if not self.pausas and ahora - self.latido >= self.segundos:
                self.inicio_cancelacion = ahora
                return True
            return False

    def error(self, cancelacion: str = "cancelada", hresult: int | None = None) -> TiempoAgotado:
        with self.candado:
            error = TiempoAgotado(
                self.segundos, time.monotonic() - self.latido, cancelacion, hresult=hresult
            )
            if self.apartado is not None:
                error.details["apartado"] = self.apartado
            if cancelacion == "abandonada" and self.resultados_del_lote is not None:
                error.details["resultados"] = self.resultados_del_lote(error)
            return error


def inicio_tarea(plazo: Plazo | None) -> None:
    _local.plazo = plazo
    antes_de_llamar()


def fin_tarea() -> None:
    _local.plazo = None


def _actual() -> Plazo | None:
    return getattr(_local, "plazo", None)


def antes_de_llamar() -> None:
    actual = _actual()
    if actual is not None:
        with actual.candado:
            if actual.inicio_cancelacion is None:
                actual.latido = time.monotonic()
                return
        raise actual.error()


def cancelada() -> bool:
    actual = _actual()
    return actual is not None and actual.inicio_cancelacion is not None


def error_cancelado(hresult: int | None = None) -> TiempoAgotado:
    return _actual().error(hresult=hresult)


def comprobar_cancelacion() -> None:
    if cancelada():
        raise error_cancelado()


def registrar_apartado(ruta: str | None) -> None:
    actual = _actual()
    if actual is not None:
        with actual.candado:
            actual.apartado = ruta


@contextmanager
def suspendido() -> Iterator[None]:
    actual = _actual()
    if actual is not None:
        with actual.candado:
            actual.pausas += 1
    try:
        comprobar_cancelacion()
        yield
    finally:
        if actual is not None:
            with actual.candado:
                actual.pausas -= 1
                if actual.inicio_cancelacion is None:
                    actual.latido = time.monotonic()


@contextmanager
def proteger_archivos() -> Iterator[None]:
    """Coordiná cambios al respaldo con la publicación del timeout."""
    actual = _actual()
    if actual is None:
        yield
    else:
        with actual.candado:
            comprobar_cancelacion()
            yield


def registrar_lote(resultados: Callable[[TiempoAgotado], list[dict]] | None) -> None:
    actual = _actual()
    if actual is not None:
        with actual.candado:
            actual.resultados_del_lote = resultados


@contextmanager
def publicar_progreso() -> Iterator[None]:
    actual = _actual()
    if actual is None:
        yield
    else:
        with actual.candado:
            yield
