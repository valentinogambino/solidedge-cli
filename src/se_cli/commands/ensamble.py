"""Comandos de ensambles: `se asm tree|add|ground|move|remove`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, UnitsOpcion, sin_dialogos, validar_units
from se_cli.core import acceso, ensamble, unidades
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Estructura y armado de ensambles.", no_args_is_help=True)


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


OcurrenciaArgumento = Annotated[
    str,
    typer.Argument(
        help="Ocurrencia: índice (1-based, el `indice` de `asm tree`) o nombre (sin distinguir "
        "mayúsculas, ej. caja.par:1)."
    ),
]
RotOpcion = Annotated[
    str | None,
    typer.Option(
        "--rot",
        help="Ángulos de Euler absolutos RX,RY,RZ (ej. 0,0,90deg). Sin unidad, radianes.",
    ),
]


@app.command("add")
def agregar(
    ctx: typer.Context,
    archivo: Annotated[str, typer.Argument(help="Pieza, chapa o ensamble (.par, .psm, .asm).")],
    at: Annotated[
        str | None,
        typer.Option("--at", help="Posición X,Y,Z (ej. 10mm,0,5mm). Sin unidad, metros."),
    ] = None,
    rot: RotOpcion = None,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Insertá un archivo como ocurrencia (exit 5 si no existe, 2 si el doc no es ensamble)."""

    def plan() -> dict[str, Any]:
        validar_units(units)
        return ensamble.planificar_add(archivo, at, rot)

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sin_dialogos(
            sesion,
            lambda app: ensamble.agregar(acceso.documento(app, doc), archivo, at, rot, elegidas),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("ground")
def fijar(
    ctx: typer.Context,
    ocurrencia: OcurrenciaArgumento,
    release: Annotated[
        bool, typer.Option("--release", help="Soltá la ocurrencia en vez de fijarla.")
    ] = False,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Fijá una ocurrencia (relación ground). Ya fija: ok sin cambios (`changed: false`).

    Solid Edge crea toda ocurrencia ya fija; `--release` le quita esa relación.
    """

    def plan() -> dict[str, Any]:
        validar_units(units)
        return ensamble.planificar_ground(ocurrencia, release)

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sin_dialogos(
            sesion,
            lambda app: ensamble.fijar(acceso.documento(app, doc), ocurrencia, release, elegidas),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("move")
def mover(
    ctx: typer.Context,
    ocurrencia: OcurrenciaArgumento,
    at: Annotated[
        str | None,
        typer.Option("--at", help="Posición absoluta X,Y,Z (ej. 10mm,0,5mm). Sin unidad, metros."),
    ] = None,
    by: Annotated[
        str | None,
        typer.Option("--by", help="Desplazamiento DX,DY,DZ (ej. 5mm,0,0). No va con --at."),
    ] = None,
    rot: RotOpcion = None,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Reubicá una ocurrencia: --at (absoluto) o --by (relativo), y --rot (ángulos absolutos)."""

    def plan() -> dict[str, Any]:
        validar_units(units)
        return ensamble.planificar_move(ocurrencia, at, by, rot)

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sin_dialogos(
            sesion,
            lambda app: ensamble.mover(
                acceso.documento(app, doc), ocurrencia, at, by, rot, elegidas
            ),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("remove")
def quitar(ctx: typer.Context, ocurrencia: OcurrenciaArgumento, doc: DocOpcion = None) -> None:
    """Borrá una ocurrencia del ensamble (no borra el archivo de la pieza)."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda app: ensamble.quitar(acceso.documento(app, doc), ocurrencia)
        ),
        modifica=True,
        plan=lambda: ensamble.planificar_remove(ocurrencia),
    )
