"""Errores de uso de Click/Typer como sobre JSON cuando se pasa `--json`.

Click/Typer detectan estos errores (subcomando inexistente, argumento faltante, opción
desconocida, valor inválido) mientras parsean, antes de que `principal` guarde `Opciones`
en `ctx.obj`; por eso `--json` se busca en los argumentos crudos.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

import typer.core
from typer import _click as click  # click vendorizado por Typer (no hay `click` propio)

from se_cli import salida
from se_cli.core.errors import ArgumentoInvalido
from se_cli.core.result import fallo


def pide_json(args: Sequence[str]) -> bool:
    """Criterio simple: hay un token exactamente igual a `--json` entre los argumentos."""
    return "--json" in args


class GrupoSe(typer.core.TyperGroup):
    """Grupo raíz de `se`: con `--json`, un error de uso sale como sobre de error."""

    def main(self, args: Sequence[str] | None = None, *resto: Any, **extra: Any) -> Any:
        crudos = sys.argv[1:] if args is None else args
        if not pide_json(crudos) or not extra.get("standalone_mode", True):
            return super().main(args, *resto, **extra)
        extra["standalone_mode"] = False
        try:
            # Sin standalone, `Exit` vuelve como return (su exit code); los comandos devuelven None.
            codigo = super().main(args, *resto, **extra)
        except click.exceptions.UsageError as error:
            invalido = ArgumentoInvalido(error.format_message())
            salida.forzar_utf8()
            salida.imprimir_json(fallo(invalido))
            sys.exit(invalido.exit_code)
        except typer.core.Exit as salida_click:
            sys.exit(salida_click.exit_code)
        except click.ClickException as error:
            error.show()
            sys.exit(error.exit_code)
        except typer.core.Abort:
            click.echo("Aborted!", file=sys.stderr)
            sys.exit(1)
        sys.exit(codigo if isinstance(codigo, int) else 0)
