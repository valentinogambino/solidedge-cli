"""Comandos de chapa metálica: `se sheetmetal flat-dxf`, `tab` y `flange`."""

from __future__ import annotations

from typing import Annotated

import typer

from se_cli.commands._comun import DocOpcion, UnitsOpcion, sin_dialogos, validar_units
from se_cli.core import acceso, brida, chapa, modelado, unidades
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
    sync: Annotated[
        bool,
        typer.Option(
            "--sync",
            help="Creá la base en modo sincrónico (necesario para `sheetmetal flange`). Sin esto, "
            "modo ordenado.",
        ),
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Creá la base de una chapa (Tab) desde un perfil cerrado, con el espesor del material.

    Solo en una chapa sin modelo base (si ya tiene, exit 2) y en modo ordenado, o con --sync, que
    pone el documento en modo sincrónico antes del Tab (la brida solo resuelve sobre esa base).
    Es la base que `sheetmetal flat-dxf --create` puede desarrollar; `se extrude` no crea la base
    de una chapa.
    """
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion,
            lambda a: modelado.crear_tab(acceso.documento(a, doc), profile, direction, sync),
        ),
        modifica=True,
        plan=lambda: modelado.planificar_tab(profile, direction, sync),
    )


@app.command("flange")
def flange(
    ctx: typer.Context,
    edge: Annotated[
        int,
        typer.Option("--edge", help="Arista recta, con el índice de `se edges list` (desde 1)."),
    ],
    length: Annotated[
        str,
        typer.Option(
            "--length", help="Longitud de la brida (ej. 30mm; sin unidad, metros). Mayor que 0."
        ),
    ],
    angle: Annotated[
        float, typer.Option("--angle", help="Ángulo de la brida en grados, entre 0 y 180.")
    ] = brida.ANGULO_POR_DEFECTO,
    direction: Annotated[
        str, typer.Option("--direction", help="normal o reverse (lado hacia el que se levanta).")
    ] = "normal",
    radius: Annotated[
        str | None,
        typer.Option(
            "--radius",
            help="Radio interior del plegado (ej. 1mm). Por defecto, el del documento.",
        ),
    ] = None,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Creá una brida sobre una arista recta de una chapa (Flanges.AddSync).

    Exige una chapa con base creada en modo sincrónico (`se sheetmetal tab --sync`): con la base
    ordenada da exit 6 (`causa: base_ordenada`). Mide el volumen antes y después; si no aumentó,
    deshace la operación y da exit 4 (`causa: brida_sin_efecto`). Arista no recta o argumento
    fuera de rango: exit 2; arista inexistente: exit 5.
    """

    def plan() -> dict:
        validar_units(units)
        return brida.planificar_brida(edge, length, angle, direction, radius)

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sin_dialogos(
            sesion,
            lambda a: brida.crear_brida(
                acceso.documento(a, doc), edge, length, angle, direction, radius, elegidas
            ),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)
