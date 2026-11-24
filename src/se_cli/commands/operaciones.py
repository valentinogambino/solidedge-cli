"""Comandos de operaciones del modelo: `se features list|suppress|unsuppress`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
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


SelectorArgumento = Annotated[
    str, typer.Argument(help="Operación: índice (1-based, como `features list`) o nombre.")
]


def _cambiar(ctx: typer.Context, selector: str, doc: str | None, suprimir: bool) -> None:
    accion = "features.suppress" if suprimir else "features.unsuppress"

    def plan() -> dict[str, Any]:
        return {"accion": accion, "operacion": selector.strip()}

    def correr(sesion):
        return sin_dialogos(
            sesion,
            lambda app: operaciones.cambiar_supresion(
                acceso.documento(app, doc), selector, suprimir
            ),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("suppress")
def suprimir(ctx: typer.Context, operacion: SelectorArgumento, doc: DocOpcion = None) -> None:
    """Suprimí una operación (pieza o chapa). Exit 5 si no existe. Ya suprimida: ok sin cambios."""
    _cambiar(ctx, operacion, doc, True)


@app.command("unsuppress")
def reactivar(ctx: typer.Context, operacion: SelectorArgumento, doc: DocOpcion = None) -> None:
    """Reactivá una operación suprimida (pieza o chapa). Exit 5 si no existe."""
    _cambiar(ctx, operacion, doc, False)
