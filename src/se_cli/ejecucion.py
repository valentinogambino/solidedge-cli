"""Punto único de ejecución de comandos: sesión, bloqueos, salida y códigos de salida.

Cada invocación de `se` es un proceso nuevo: la `Sesion` se crea al empezar, se engancha a la
instancia abierta (nunca lanza Solid Edge salvo `se connect --launch`) y se suelta al terminar.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import typer

from se_cli import salida
from se_cli.core.errors import SoloLectura, traducir
from se_cli.core.session import Sesion


@dataclass(frozen=True)
class Opciones:
    """Opciones globales de `se`, guardadas en `ctx.obj`."""

    json: bool = False
    readonly: bool = False
    dry_run: bool = False


def crear_sesion() -> Sesion:
    """Fábrica de `Sesion`. Los tests la parchean (`se_cli.ejecucion.crear_sesion`)."""
    return Sesion()


def opciones_de(ctx: typer.Context) -> Opciones:
    raiz = ctx.find_root()
    return raiz.obj if isinstance(raiz.obj, Opciones) else Opciones()


def ejecutar(
    ctx: typer.Context,
    fn: Callable[[Sesion], Any],
    *,
    modifica: bool = False,
    plan: Callable[[], dict[str, Any]] | None = None,
    conectar: bool = True,
) -> None:
    """Corré un comando de punta a punta e imprimí su resultado.

    - `fn(sesion)` hace el trabajo y devuelve datos planos (nunca objetos COM). Con
      `conectar=True` (por defecto) la sesión ya viene enganchada; con `False` el comando
      decide cuándo y cómo conectar (`status`, `connect`).
    - `modifica=True` marca un comando que cambia el estado: `--readonly` lo bloquea
      (exit 6, `solo_lectura`) y `--dry-run` informa `{"dry_run": true, ...}` sin llamar a COM.
    - `plan()` devuelve un dict que describe la acción. Se corre antes de tocar COM, tanto en
      modo real como en `--dry-run`, así valida argumentos locales; si levanta `SeError`
      sale el error normal. En `--dry-run` su resultado es el `data`.

    Éxito: exit 0. Error: sobre `{ok:false}` (JSON) o mensaje en stderr (humano) y
    `typer.Exit` con el exit code de `core/errors.py`. Una excepción no prevista es exit 1.
    """
    opciones = opciones_de(ctx)
    salida.forzar_utf8()
    try:
        data = _correr(opciones, fn, modifica, plan, conectar)
    except Exception as error:  # noqa: BLE001 - todo error se traduce a SeError
        traducido = traducir(error)
        salida.emitir_error(traducido, como_json=opciones.json)
        raise typer.Exit(traducido.exit_code) from None
    salida.emitir_ok(data, como_json=opciones.json)


def _correr(
    opciones: Opciones,
    fn: Callable[[Sesion], Any],
    modifica: bool,
    plan: Callable[[], dict[str, Any]] | None,
    conectar: bool,
) -> Any:
    if modifica and opciones.readonly:
        raise SoloLectura("Bloqueado por --readonly: este comando modifica Solid Edge.")
    descripcion = plan() if plan is not None else {}
    if modifica and opciones.dry_run:
        return {"dry_run": True, **descripcion}

    sesion = crear_sesion()
    try:
        if conectar:
            sesion.conectar()
        return fn(sesion)
    finally:
        with contextlib.suppress(Exception):
            sesion.cerrar()


__all__ = ["Opciones", "crear_sesion", "ejecutar", "opciones_de"]
