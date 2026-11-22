"""Comandos de chapa metálica: `se sheetmetal flat-dxf`."""

from __future__ import annotations

from typing import Annotated

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import chapa
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Chapa metálica.", no_args_is_help=True)


@app.command("flat-dxf")
def desarrollo_dxf(
    ctx: typer.Context,
    archivo: Annotated[
        str | None,
        typer.Argument(help="Chapa .psm. Sin esto, el documento activo (o --doc)."),
    ] = None,
    out: Annotated[
        str | None,
        typer.Option("--out", help="Archivo .dxf o carpeta. Por defecto, junto a la chapa."),
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Reemplazá el DXF si ya existe.")
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Exportá el desarrollo (flat pattern) de una chapa a DXF.

    Usa el desarrollo que ya tiene la chapa; si no tiene, da exit 5 y pide crearlo en Solid Edge.
    Un documento que no es chapa da exit 2. En Community Edition puede salir con marca de agua.
    """
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda a: chapa.exportar_dxf(a, archivo, doc, out, overwrite)
        ),
        modifica=True,
        plan=lambda: chapa.planificar(archivo, doc, out, overwrite),
    )
