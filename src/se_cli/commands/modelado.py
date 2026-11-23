"""Comandos de modelado: `se sketch rect|circle`, `se extrude`, `se revolve` y `se hole`."""

from __future__ import annotations

from typing import Annotated

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import acceso, modelado
from se_cli.ejecucion import ejecutar

sketch = typer.Typer(
    help="Perfiles (sketch) cerrados en un plano de referencia: top, front, right o un índice.",
    no_args_is_help=True,
)

PlanoOpcion = Annotated[
    str,
    typer.Option(
        "--plane",
        help="top (XY), front (XZ), right (YZ) o el índice de RefPlanes (1, 2, 3...).",
    ),
]
PerfilOpcion = Annotated[
    str | None,
    typer.Option(
        "--profile",
        help="Perfil devuelto por `se sketch` (ej. 2). Por defecto, el último del documento.",
    ),
]
DireccionOpcion = Annotated[str, typer.Option("--direction", help="normal, reverse o symmetric.")]
PuntoOpcion = Annotated[
    str | None,
    typer.Option("--at", help="X,Y con unidad opcional (ej. 10mm,5mm). Por defecto 0,0."),
]


@sketch.command("rect")
def rectangulo(
    ctx: typer.Context,
    width: Annotated[str, typer.Option("--width", help="Ancho (ej. 50mm).")],
    height: Annotated[str, typer.Option("--height", help="Alto (ej. 30mm).")],
    plane: PlanoOpcion = "top",
    at: PuntoOpcion = None,
    centered: Annotated[
        bool, typer.Option("--centered", help="--at es el centro y no la esquina inferior.")
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Creá un perfil rectangular cerrado (devuelve el número de perfil a usar después)."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion,
            lambda app: modelado.crear_rect(
                acceso.documento(app, doc), plane, width, height, at, centered
            ),
        ),
        modifica=True,
        plan=lambda: modelado.planificar_rect(plane, width, height, at, centered),
    )


@sketch.command("circle")
def circulo(
    ctx: typer.Context,
    radius: Annotated[str | None, typer.Option("--radius", help="Radio (ej. 5mm).")] = None,
    diameter: Annotated[str | None, typer.Option("--diameter", help="Diámetro.")] = None,
    plane: PlanoOpcion = "top",
    at: PuntoOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Creá un perfil circular cerrado (--at es el centro)."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion,
            lambda app: modelado.crear_circulo(
                acceso.documento(app, doc), plane, radius, diameter, at
            ),
        ),
        modifica=True,
        plan=lambda: modelado.planificar_circulo(plane, radius, diameter, at),
    )


def registrar(app: typer.Typer) -> None:
    app.add_typer(sketch, name="sketch")

    @app.command("extrude")
    def extruir(
        ctx: typer.Context,
        distance: Annotated[str, typer.Argument(help="Distancia (ej. 10mm).")],
        profile: PerfilOpcion = None,
        direction: DireccionOpcion = "normal",
        cut: Annotated[
            bool, typer.Option("--cut", help="Cortá material del modelo en lugar de agregar.")
        ] = False,
        doc: DocOpcion = None,
    ) -> None:
        """Extruí un perfil (la primera operación crea el modelo base). Con --cut corta."""
        ejecutar(
            ctx,
            lambda sesion: sin_dialogos(
                sesion,
                lambda a: modelado.extruir(
                    acceso.documento(a, doc), distance, profile, direction, cut
                ),
            ),
            modifica=True,
            plan=lambda: modelado.planificar_extrusion(distance, profile, direction, cut),
        )

    @app.command("revolve")
    def revolucionar(
        ctx: typer.Context,
        axis: Annotated[
            str,
            typer.Option(
                "--axis",
                help="Eje de giro en el plano del perfil: x (la recta y=0) o y (la recta x=0).",
            ),
        ],
        angle: Annotated[str, typer.Argument(help="Ángulo (ej. 180deg).")] = "360deg",
        profile: PerfilOpcion = None,
        doc: DocOpcion = None,
    ) -> None:
        """Revolucioná un perfil alrededor de uno de sus ejes."""
        ejecutar(
            ctx,
            lambda sesion: sin_dialogos(
                sesion,
                lambda a: modelado.revolucionar(acceso.documento(a, doc), angle, profile, axis),
            ),
            modifica=True,
            plan=lambda: modelado.planificar_revolucion(angle, profile, axis),
        )

    @app.command("hole")
    def agujero(
        ctx: typer.Context,
        at: Annotated[str, typer.Option("--at", help="Centro X,Y en el plano (ej. 10mm,15mm).")],
        diameter: Annotated[str, typer.Option("--diameter", help="Diámetro (ej. 6mm).")],
        depth: Annotated[str | None, typer.Option("--depth", help="Profundidad.")] = None,
        through: Annotated[bool, typer.Option("--through", help="Agujero pasante.")] = False,
        plane: PlanoOpcion = "top",
        direction: DireccionOpcion = "normal",
        doc: DocOpcion = None,
    ) -> None:
        """Agujero simple sobre un modelo existente (círculo en un plano y corte)."""
        ejecutar(
            ctx,
            lambda sesion: sin_dialogos(
                sesion,
                lambda a: modelado.agujerear(
                    acceso.documento(a, doc), at, diameter, depth, through, plane, direction
                ),
            ),
            modifica=True,
            plan=lambda: modelado.planificar_agujero(
                at, diameter, depth, through, plane, direction
            ),
        )
