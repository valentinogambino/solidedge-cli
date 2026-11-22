"""Piezas compartidas por los comandos: opciones comunes y escritura sin diálogos."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

import typer

from se_cli.core import unidades
from se_cli.core.session import Sesion

DocOpcion = Annotated[
    str | None,
    typer.Option(
        "--doc",
        help="Documento: índice (1-based, como `docs list`), nombre o ruta. "
        "Por defecto, el activo.",
    ),
]

UnitsOpcion = Annotated[
    str | None,
    typer.Option(
        "--units",
        help="Unidades para mostrar, separadas por coma: mm, cm, m, in, ft, deg, rad, kg, g, lb "
        "(ej. mm,deg). Sin esto sale en SI.",
    ),
]


def sin_dialogos(sesion: Sesion, fn: Callable[[Any], Any]) -> Any:
    """Corré `fn(app)` sin alertas y sin repetirla entera si Solid Edge está ocupado."""
    with sesion.sin_alertas():
        return sesion.llamar(fn, reintentar_todo=False)


def validar_units(units: str | None) -> dict[str, Any]:
    """Validá `--units` antes de conectar (exit 2 si está mal); sirve de `plan` de lectura."""
    unidades.parsear_unidades(units)
    return {}
