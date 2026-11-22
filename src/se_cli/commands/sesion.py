"""Comandos de sesión: `se connect`, `se status` y `se quit`."""

from __future__ import annotations

from typing import Annotated

import typer

from se_cli.core import documentos
from se_cli.core.errors import ArgumentoInvalido, NoConectado
from se_cli.ejecucion import ejecutar


def registrar(app: typer.Typer) -> None:
    @app.command("connect")
    def connect(
        ctx: typer.Context,
        launch: Annotated[
            bool, typer.Option("--launch", help="Lanzá Solid Edge si no hay una instancia abierta.")
        ] = False,
    ) -> None:
        """Enganchate a Solid Edge abierto. Solo `--launch` lo arranca."""
        ejecutar(
            ctx,
            lambda sesion: sesion.conectar(lanzar=launch),
            modifica=launch,
            plan=lambda: {"accion": "connect", "launch": True},
            conectar=False,
        )

    @app.command("status")
    def status(ctx: typer.Context) -> None:
        """Estado de Solid Edge. Sin instancia abierta informa `conectado: false` (exit 0)."""

        def correr(sesion):
            try:
                sesion.conectar()
            except NoConectado:
                return {
                    "conectado": False,
                    "version": None,
                    "nombre": None,
                    "visible": None,
                    "documentos": 0,
                    "activo": None,
                }
            return sesion.llamar(documentos.estado)

        ejecutar(ctx, correr, conectar=False)

    @app.command("quit")
    def quit_(
        ctx: typer.Context,
        yes: Annotated[bool, typer.Option("--yes", help="Confirmá que querés cerrar.")] = False,
        discard: Annotated[
            bool, typer.Option("--discard", help="Descartá los cambios sin guardar.")
        ] = False,
    ) -> None:
        """Cerrá Solid Edge. Exige --yes; con cambios sin guardar exige además --discard."""

        def plan():
            if not yes:
                raise ArgumentoInvalido("Cerrar Solid Edge es destructivo: repetí con --yes.")
            return {"accion": "quit", "discard": discard}

        def correr(sesion):
            return sesion.llamar(lambda app: documentos.salir(app, discard), reintentar_todo=False)

        ejecutar(ctx, correr, modifica=True, plan=plan)
