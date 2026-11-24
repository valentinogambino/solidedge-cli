"""Comandos de ensambles: `se asm tree|add|ground|move|remove|relate|relations`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, UnitsOpcion, sin_dialogos, validar_units
from se_cli.core import acceso, ensamble, relaciones, unidades
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


_AYUDA_CARA = (
    "<occ>:<cara>: ocurrencia (índice de `asm tree` o nombre) y cara (índice 1-based del cuerpo "
    "de su pieza, el `indice` de cara de `se edges list`). Ej. 1:3 o caja.par:2:5."
)


@app.command("relate")
def relacionar(
    ctx: typer.Context,
    tipo: Annotated[
        str,
        typer.Argument(
            help="mate (caras planas enfrentadas), align (caras planas alineadas) o axial "
            "(ejes de dos caras cilíndricas coincidentes)."
        ),
    ],
    a: Annotated[str, typer.Option("--a", help=_AYUDA_CARA)],
    b: Annotated[str, typer.Option("--b", help=_AYUDA_CARA)],
    offset: Annotated[
        str | None,
        typer.Option(
            "--offset",
            help="Distancia entre las caras (ej. 5mm); solo mate y align. Sin unidad, m.",
        ),
    ] = None,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Creá una relación 3D entre una cara de cada ocurrencia.

    Las ocurrencias nacen fijas: soltá una con `se asm ground <occ> --release` antes de relacionar.
    """

    def plan() -> dict[str, Any]:
        validar_units(units)
        return relaciones.planificar_relate(tipo, a, b, offset)

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sin_dialogos(
            sesion,
            lambda app: relaciones.relacionar(
                acceso.documento(app, doc), tipo, a, b, offset, elegidas
            ),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)


relations_app = typer.Typer(help="Relaciones 3D del ensamble.", no_args_is_help=True)
app.add_typer(relations_app, name="relations")


@relations_app.command("list")
def listar_relaciones(ctx: typer.Context, units: UnitsOpcion = None, doc: DocOpcion = None) -> None:
    """Listá las relaciones: índice, tipo, ocurrencias, offset y estado."""

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sesion.llamar(lambda app: relaciones.listar(acceso.documento(app, doc), elegidas))

    ejecutar(ctx, correr, plan=lambda: validar_units(units))


@relations_app.command("delete")
def borrar_relacion(
    ctx: typer.Context,
    indice: Annotated[str, typer.Argument(help="Índice de la relación (de `asm relations list`).")],
    doc: DocOpcion = None,
) -> None:
    """Borrá una relación del ensamble (exit 5 si no existe)."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda app: relaciones.borrar(acceso.documento(app, doc), indice)
        ),
        modifica=True,
        plan=lambda: relaciones.planificar_delete(indice),
    )
