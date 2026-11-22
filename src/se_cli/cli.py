from typing import Annotated

import typer

from se_cli import __version__
from se_cli.commands import (
    docs,
    draft,
    ensamble,
    exportar,
    masa,
    operaciones,
    propiedades,
    sesion,
    variables,
)
from se_cli.ejecucion import Opciones

app = typer.Typer(add_completion=False, invoke_without_command=True)
sesion.registrar(app)
app.add_typer(docs.app, name="docs")
app.add_typer(variables.app, name="vars")
app.add_typer(propiedades.app, name="props")
app.add_typer(ensamble.app, name="asm")
app.add_typer(operaciones.app, name="features")
app.add_typer(draft.app, name="draft")
masa.registrar(app)
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
) -> None:
    """Manejá Solid Edge desde la terminal."""
    contexto.obj = Opciones(json=json, readonly=readonly, dry_run=dry_run)
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if contexto.invoked_subcommand is None:
        typer.echo(contexto.get_help())
