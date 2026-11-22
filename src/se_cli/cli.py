from typing import Annotated

import typer

from se_cli import __version__

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def principal(
    contexto: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Mostrá la versión de se.")] = False,
) -> None:
    """Manejá Solid Edge desde la terminal."""
    if version:
        typer.echo(__version__)
    elif contexto.invoked_subcommand is None:
        typer.echo(contexto.get_help())
