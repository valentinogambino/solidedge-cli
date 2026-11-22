"""Comandos de propiedades de archivo: `se props get|set`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import acceso, propiedades
from se_cli.core.errors import ArgumentoInvalido
from se_cli.ejecucion import ejecutar

app = typer.Typer(
    help="Propiedades de archivo del documento (Summary, Project, Custom...).",
    no_args_is_help=True,
)


@app.command("get")
def obtener(
    ctx: typer.Context,
    nombre: Annotated[
        str | None, typer.Argument(help="Propiedad. Sin nombre, lista todas.")
    ] = None,
    conjunto: Annotated[
        str | None,
        typer.Option("--set", help="Conjunto (SummaryInformation, ProjectInformation, Custom...)."),
    ] = None,
    doc: DocOpcion = None,
) -> None:
    """Listá las propiedades de archivo, o mostrá una (exit 5 si no existe)."""
    ejecutar(
        ctx,
        lambda sesion: sesion.llamar(
            lambda app: propiedades.obtener(acceso.documento(app, doc), nombre, conjunto)
        ),
    )


@app.command("set")
def modificar(
    ctx: typer.Context,
    nombre: Annotated[str, typer.Argument(help="Propiedad a escribir.")],
    valor: Annotated[str, typer.Argument(help="Valor (texto).")],
    conjunto: Annotated[
        str,
        typer.Option(
            "--set", help="Conjunto. En Custom la propiedad se crea si no existe; en otros, exit 5."
        ),
    ] = propiedades.CONJUNTO_PERSONALIZADO,
    save: Annotated[
        bool, typer.Option("--save", help="Guardá el documento después de escribir.")
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Escribí una propiedad de archivo. No guarda el documento salvo `--save`."""

    def plan() -> dict[str, Any]:
        if not nombre.strip():
            raise ArgumentoInvalido("El nombre de la propiedad está vacío.")
        return {
            "accion": "props.set",
            "conjunto": conjunto,
            "nombre": nombre.strip(),
            "valor": valor,
            "save": save,
        }

    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda app: propiedades.modificar(app, doc, nombre, valor, conjunto, save)
        ),
        modifica=True,
        plan=plan,
    )
