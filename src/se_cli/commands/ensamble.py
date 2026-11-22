"""Comandos de ensambles: `se asm tree`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion
from se_cli.core import acceso, ensamble
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Estructura de ensambles.", no_args_is_help=True)


@app.command("tree")
def arbol(
    ctx: typer.Context,
    depth: Annotated[
        int,
        typer.Option("--depth", help="Niveles a expandir (1 = solo el primer nivel)."),
    ] = ensamble.PROFUNDIDAD_POR_DEFECTO,
    flat: Annotated[
        bool,
        typer.Option("--flat", help="Lista de materiales agregada por archivo en vez del árbol."),
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Árbol de ocurrencias de un ensamble (exit 2 si el documento no es un ensamble)."""

    def plan() -> dict[str, Any]:
        ensamble.validar_profundidad(depth)
        return {}

    ejecutar(
        ctx,
        lambda sesion: sesion.llamar(
            lambda app: ensamble.arbol(acceso.documento(app, doc), depth, flat)
        ),
        plan=plan,
    )
