"""Comandos de operaciones del modelo: `se features list`."""

from __future__ import annotations

import typer

from se_cli.commands._comun import DocOpcion
from se_cli.core import acceso, operaciones
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Operaciones (features) de piezas y chapas.", no_args_is_help=True)


@app.command("list")
def listar(ctx: typer.Context, doc: DocOpcion = None) -> None:
    """Listá las operaciones del modelo en orden (solo pieza y chapa; si no, exit 2)."""
    ejecutar(
        ctx,
        lambda sesion: sesion.llamar(lambda app: operaciones.listar(acceso.documento(app, doc))),
    )
