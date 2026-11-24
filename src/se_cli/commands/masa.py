"""Comando de propiedades físicas: `se mass`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, UnitsOpcion, sin_dialogos, validar_units
from se_cli.core import acceso, fisica, unidades
from se_cli.ejecucion import ejecutar


def registrar(app: typer.Typer) -> None:
    @app.command("mass")
    def masa(
        ctx: typer.Context,
        density: Annotated[
            float | None,
            typer.Option(
                "--density",
                help="Densidad en kg/m3: recalcula con ella (modifica el estado del documento). "
                "Sin esto se leen las propiedades físicas ya guardadas.",
            ),
        ] = None,
        units: UnitsOpcion = None,
        doc: DocOpcion = None,
    ) -> None:
        """Masa, volumen, área, centros e inercia de una pieza, chapa o ensamble."""

        def plan() -> dict[str, Any]:
            validar_units(units)
            return {"accion": "mass", "densidad": fisica.validar_densidad(density)}

        def correr(sesion):
            elegidas = unidades.parsear_unidades(units)
            valor = fisica.validar_densidad(density)

            def trabajo(app):
                return fisica.propiedades(acceso.documento(app, doc), valor, elegidas, app=app)

            if valor is None:
                return sesion.llamar(trabajo)
            return sin_dialogos(sesion, trabajo)

        ejecutar(ctx, correr, modifica=density is not None, plan=plan)
