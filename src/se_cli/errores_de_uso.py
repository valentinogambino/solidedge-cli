"""Errores de uso de Click/Typer como sobre JSON cuando se pasa `--json`.

Click/Typer detectan estos errores (subcomando inexistente, argumento faltante, opción
desconocida, valor inválido) mientras parsean, antes de que `principal` guarde `Opciones`
en `ctx.obj`; por eso `--json` se busca en los argumentos crudos.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any, NoReturn

import typer.core
from typer import _click as click  # click vendorizado por Typer (no hay `click` propio)

from se_cli import salida
from se_cli.core.errors import ArgumentoInvalido, SeError, traducir
from se_cli.core.result import fallo


def pide_json(args: Sequence[str]) -> bool:
    """Criterio simple: hay un token exactamente igual a `--json` entre los argumentos."""
    return "--json" in args


def _salir_con(error: SeError) -> NoReturn:
    """Sobre de error por stdout y salida con el exit code de ese mismo error (tabla estable)."""
    salida.forzar_utf8()
    salida.imprimir_json(fallo(error))
    sys.exit(error.exit_code)


class GrupoSe(typer.core.TyperGroup):
    """Grupo raíz de `se`: con `--json`, un error de uso sale como sobre de error."""

    def main(self, args: Sequence[str] | None = None, *resto: Any, **extra: Any) -> Any:
        # `--help` y los errores de uso de Click escriben antes de que corra ningún comando:
        # sin esto salen en la codificación de la consola (mojibake en Git Bash).
        salida.forzar_utf8()
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
            _salir_con(SeError(error.format_message()))
        except (typer.core.Abort, KeyboardInterrupt):
            _salir_con(SeError("Operación cancelada."))
        except Exception as error:  # noqa: BLE001 - con --json la salida siempre es un sobre
            _salir_con(traducir(error))
        sys.exit(codigo if isinstance(codigo, int) else 0)
