import math
from typing import Annotated

import typer

from se_cli import __version__
from se_cli.commands import (
    chapa,
    com,
    docs,
    draft,
    ensamble,
    exportar,
    masa,
    modelado,
    operaciones,
    propiedades,
    redondeos,
    sesion,
    variables,
)
from se_cli.ejecucion import Opciones
from se_cli.errores_de_uso import GrupoSe

app = typer.Typer(add_completion=False, invoke_without_command=True, cls=GrupoSe)
sesion.registrar(app)
app.add_typer(docs.app, name="docs")
app.add_typer(variables.app, name="vars")
app.add_typer(propiedades.app, name="props")
app.add_typer(ensamble.app, name="asm")
app.add_typer(operaciones.app, name="features")
app.add_typer(draft.app, name="draft")
app.add_typer(chapa.app, name="sheetmetal")
masa.registrar(app)
modelado.registrar(app)
redondeos.registrar(app)
com.registrar(app)
exportar.registrar(app)


@app.callback()
def principal(
    contexto: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Mostrá la versión de se.")] = False,
    json: Annotated[
        bool,
        typer.Option("--json", help="Salida como {ok, data, error} en una línea, sin colores."),
    ] = False,
    readonly: Annotated[
        bool, typer.Option("--readonly", help="Bloqueá todo comando que modifique (exit 6).")
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Los comandos que modifican informan qué harían."),
    ] = False,
    timeout: Annotated[
        float | None,
        typer.Option(
            "--timeout",
            envvar="SE_TIMEOUT",
            metavar="SEG",
            help="Segundos máximos esperando que Solid Edge responda una llamada COM "
            "(exit 7 al vencer). Sin esto, espera sin límite.",
        ),
    ] = None,
) -> None:
    """Manejá Solid Edge desde la terminal."""
    if timeout is not None and not (math.isfinite(timeout) and 0 < timeout <= 3600):
        raise typer.BadParameter(
            "tiene que ser un número de segundos mayor que 0 y hasta 3600.",
            param_hint="--timeout",
        )
    contexto.obj = Opciones(json=json, readonly=readonly, dry_run=dry_run, timeout=timeout)
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if contexto.invoked_subcommand is None:
        typer.echo(contexto.get_help())
