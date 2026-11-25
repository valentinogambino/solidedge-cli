"""Comandos de chapa metálica: `se sheetmetal flat-dxf` y `se sheetmetal tab`."""

from __future__ import annotations

from typing import Annotated

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import acceso, chapa, modelado
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
    create: Annotated[
        bool,
        typer.Option(
            "--create",
            help="Si la chapa no tiene desarrollo, crealo (cara plana de mayor área), guardá la "
            "chapa, reabrila y exportá. Exige una chapa guardada y no de solo lectura.",
        ),
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Exportá el desarrollo (flat pattern) de una chapa a DXF.

    Usa el desarrollo que ya tiene la chapa; si no tiene, da exit 5 salvo con --create, que lo crea
    por API, guarda la chapa (con cualquier cambio pendiente), la cierra, la reabre y exporta.
    Si Solid Edge no puede desarrollar la chapa, --create da exit 6 sin guardarla, con la causa
    probable en el error. Un documento que no es chapa da exit 2. En Community Edition puede salir
    con marca de agua.
    """
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda a: chapa.exportar_dxf(a, archivo, doc, out, overwrite, create)
        ),
        modifica=True,
        plan=lambda: chapa.planificar(archivo, doc, out, overwrite, create),
    )


@app.command("tab")
def tab(
    ctx: typer.Context,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Perfil devuelto por `se sketch` (ej. 2). Por defecto, el último del documento.",
        ),
    ] = None,
    direction: Annotated[
        str, typer.Option("--direction", help="normal o reverse (lado del plano del perfil).")
    ] = "normal",
    doc: DocOpcion = None,
) -> None:
    """Creá la base de una chapa (Tab) desde un perfil cerrado, con el espesor del material.

    Solo en una chapa en modo ordenado y sin modelo base (si ya tiene, exit 2). Es la base que
    `sheetmetal flat-dxf --create` puede desarrollar; `se extrude` no crea la base de una chapa.
    """
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion,
            lambda a: modelado.crear_tab(acceso.documento(a, doc), profile, direction),
        ),
        modifica=True,
        plan=lambda: modelado.planificar_tab(profile, direction),
    )
