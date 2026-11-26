"""Comandos de material: `se material list|get|set`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import materiales
from se_cli.ejecucion import ejecutar

app = typer.Typer(
    help="Material de la pieza o chapa (de las bibliotecas de Solid Edge).",
    no_args_is_help=True,
)

BibliotecaOpcion = Annotated[
    str | None,
    typer.Option(
        "--library",
        help="Biblioteca de materiales (ej. Materials, Materials-DIN). Por defecto, todas.",
    ),
]


@app.command("list")
def listar(ctx: typer.Context, library: BibliotecaOpcion = None) -> None:
    """Listá los materiales disponibles por biblioteca (exit 5 si la biblioteca no existe)."""
    ejecutar(ctx, lambda sesion: sesion.llamar(lambda app: materiales.listar(app, library)))


@app.command("get")
def obtener(ctx: typer.Context, doc: DocOpcion = None) -> None:
    """Mostrá el material del documento (null si no tiene)."""
    ejecutar(ctx, lambda sesion: sesion.llamar(lambda app: materiales.obtener(app, doc)))


@app.command("set")
def asignar(
    ctx: typer.Context,
    nombre: Annotated[
        str,
        typer.Argument(help="Material, como en `se material list` (sin distinguir mayúsculas)."),
    ],
    library: BibliotecaOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Asigná un material (con su densidad) a una pieza o chapa. No guarda el documento.

    Con material, `se mass` sin --density lee la masa sin estado 2. Exit 5 si no existe.
    """

    def plan() -> dict[str, Any]:
        return {
            "accion": "material.set",
            "material": materiales.validar_nombre(nombre),
            "biblioteca": library,
        }

    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda app: materiales.asignar(app, doc, nombre, library)
        ),
        modifica=True,
        plan=plan,
    )
