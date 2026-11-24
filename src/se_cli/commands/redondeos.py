"""Comandos de aristas: `se edges list`, `se round` y `se chamfer`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, UnitsOpcion, sin_dialogos, validar_units
from se_cli.core import acceso, redondeos, unidades
from se_cli.ejecucion import ejecutar

edges = typer.Typer(help="Aristas del cuerpo de una pieza o chapa.", no_args_is_help=True)

AristasOpcion = Annotated[
    str,
    typer.Option(
        "--edges",
        help="Aristas: all, índices 1-based de `se edges list` (1,3,5) o rangos (1-4). "
        "Los índices cambian después de cada operación que modifica el cuerpo.",
    ),
]


@edges.command("list")
def listar(ctx: typer.Context, units: UnitsOpcion = None, doc: DocOpcion = None) -> None:
    """Listá las aristas (índice, tipo, longitud, extremos y caras) de una pieza o chapa."""

    def correr(sesion):
        elegidas = unidades.parsear_unidades(units)
        return sesion.llamar(lambda app: redondeos.listar(acceso.documento(app, doc), elegidas))

    ejecutar(ctx, correr, plan=lambda: validar_units(units))


def registrar(app: typer.Typer) -> None:
    app.add_typer(edges, name="edges")

    @app.command("round")
    def redondear(
        ctx: typer.Context,
        radius: Annotated[str, typer.Argument(help="Radio (ej. 2mm). Sin unidad, metros.")],
        aristas: AristasOpcion,
        units: UnitsOpcion = None,
        doc: DocOpcion = None,
    ) -> None:
        """Redondeo de radio constante sobre las aristas elegidas (una sola operación)."""

        def plan() -> dict[str, Any]:
            validar_units(units)
            return redondeos.planificar_round(radius, aristas)

        def correr(sesion):
            elegidas = unidades.parsear_unidades(units)
            return sin_dialogos(
                sesion,
                lambda app: redondeos.redondear(
                    acceso.documento(app, doc), radius, aristas, elegidas
                ),
            )

        ejecutar(ctx, correr, modifica=True, plan=plan)

    @app.command("chamfer")
    def achaflanar(
        ctx: typer.Context,
        distance: Annotated[str, typer.Argument(help="Distancia (ej. 1mm). Sin unidad, metros.")],
        aristas: AristasOpcion,
        angle: Annotated[
            str | None,
            typer.Option(
                "--angle",
                help="Ángulo (ej. 30deg; sin unidad, radianes): chaflán distancia + ángulo, "
                "con todas las aristas en una misma cara. Sin esto, distancias iguales.",
            ),
        ] = None,
        units: UnitsOpcion = None,
        doc: DocOpcion = None,
    ) -> None:
        """Chaflán de distancias iguales (o distancia + ángulo con --angle) en las aristas."""

        def plan() -> dict[str, Any]:
            validar_units(units)
            return redondeos.planificar_chamfer(distance, angle, aristas)

        def correr(sesion):
            elegidas = unidades.parsear_unidades(units)
            return sin_dialogos(
                sesion,
                lambda app: redondeos.achaflanar(
                    acceso.documento(app, doc), distance, angle, aristas, elegidas
                ),
            )

        ejecutar(ctx, correr, modifica=True, plan=plan)
