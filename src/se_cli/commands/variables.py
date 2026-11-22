"""Comandos de variables y cotas: `se vars list|get|set|add`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, UnitsOpcion, sin_dialogos, validar_units
from se_cli.core import acceso, unidades, variables
from se_cli.ejecucion import ejecutar

app = typer.Typer(
    help="Variables y cotas del documento (valores en SI; --units para mostrarlos en otra unidad).",
    no_args_is_help=True,
)


@app.command("list")
def listar(
    ctx: typer.Context,
    filtro: Annotated[
        str | None,
        typer.Option(
            "--filter", help="Patrón con comodines * y ? (ej. 'Largo*'). Por defecto todas."
        ),
    ] = None,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Listá las variables y cotas del documento."""
    ejecutar(
        ctx,
        lambda sesion: sesion.llamar(
            lambda app: variables.listar(
                acceso.documento(app, doc), filtro, unidades.parsear_unidades(units)
            )
        ),
        plan=lambda: validar_units(units),
    )


@app.command("get")
def obtener(
    ctx: typer.Context,
    nombre: Annotated[str, typer.Argument(help="Nombre de la variable.")],
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Mostrá una variable (exit 5 si no existe)."""
    ejecutar(
        ctx,
        lambda sesion: sesion.llamar(
            lambda app: variables.obtener(
                acceso.documento(app, doc), nombre, unidades.parsear_unidades(units)
            )
        ),
        plan=lambda: validar_units(units),
    )


@app.command("set")
def modificar(
    ctx: typer.Context,
    nombre: Annotated[str, typer.Argument(help="Nombre de la variable.")],
    valor: Annotated[
        str | None,
        typer.Argument(
            help="Valor con unidad opcional (120mm, 45deg, 0.12). Sin unidad es SI. "
            "Un valor negativo va después de `--`."
        ),
    ] = None,
    formula: Annotated[
        str | None, typer.Option("--formula", help="Fórmula en lugar de un valor (ej. 'Ancho*2').")
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Intentá escribir aunque sea de solo lectura o tenga fórmula."
        ),
    ] = False,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Cambiá el valor o la fórmula de una variable. Devuelve `{nombre, antes, despues}`."""

    def plan() -> dict[str, Any]:
        validar_units(units)
        orden = variables.preparar_set(valor, formula)
        return {
            "accion": "vars.set",
            "nombre": nombre,
            "valor_si": None if orden.cantidad is None else orden.cantidad.valor_si,
            "formula": orden.formula,
            "force": force,
        }

    def correr(sesion):
        orden = variables.preparar_set(valor, formula)
        return sin_dialogos(
            sesion,
            lambda app: variables.modificar(
                acceso.documento(app, doc),
                nombre,
                orden,
                force=force,
                elegidas=unidades.parsear_unidades(units),
            ),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("add")
def agregar(
    ctx: typer.Context,
    nombre: Annotated[str, typer.Argument(help="Nombre de la variable nueva.")],
    valor: Annotated[str, typer.Argument(help="Valor con unidad opcional (120mm, 45deg, 0.12).")],
    unit_type: Annotated[
        str | None,
        typer.Option(
            "--unit-type",
            help="Tipo de unidad: distance, angle, mass, scalar, area, volume... "
            "Por defecto se deduce de la unidad del valor.",
        ),
    ] = None,
    units: UnitsOpcion = None,
    doc: DocOpcion = None,
) -> None:
    """Creá una variable de usuario (exit 6 si ya existe)."""

    def plan() -> dict[str, Any]:
        validar_units(units)
        cantidad, codigo = variables.parsear_nueva(nombre, valor, unit_type)
        return {
            "accion": "vars.add",
            "nombre": nombre.strip(),
            "valor_si": cantidad.valor_si,
            "tipo_unidad": codigo,
        }

    def correr(sesion):
        cantidad, codigo = variables.parsear_nueva(nombre, valor, unit_type)
        return sin_dialogos(
            sesion,
            lambda app: variables.agregar(
                acceso.documento(app, doc),
                nombre,
                cantidad,
                codigo,
                unidades.parsear_unidades(units),
            ),
        )

    ejecutar(ctx, correr, modifica=True, plan=plan)
