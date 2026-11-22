"""Comando `se export`: exporta documentos a STEP, STL, Parasolid, IGES, PDF, DXF y PNG."""

from __future__ import annotations

import os
from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import documentos, exportar
from se_cli.ejecucion import ejecutar


def registrar(app: typer.Typer) -> None:
    @app.command("export")
    def exportar_cmd(
        ctx: typer.Context,
        formato: Annotated[
            str,
            typer.Option(
                "--format",
                help="step, stl, x_t, igs (alias: stp, iges, parasolid).",
            ),
        ],
        out: Annotated[
            str | None,
            typer.Option(
                "--out", help="Archivo de salida o carpeta. Por defecto, junto al origen."
            ),
        ] = None,
        overwrite: Annotated[
            bool, typer.Option("--overwrite", help="Reemplazá la salida si ya existe.")
        ] = False,
        doc: DocOpcion = None,
    ) -> None:
        """Exportá el documento activo (o `--doc`) sin cerrarlo ni modificarlo."""

        def plan() -> dict[str, Any]:
            fmt = exportar.formato_de(formato)
            salida = None
            if out is not None:
                salida = _validar_salida(fmt, out, overwrite)
            return {
                "accion": "export",
                "formato": fmt.clave,
                "entradas": [{"entrada": doc or "activo", "salida": salida}],
                "overwrite": overwrite,
            }

        def correr(sesion):
            fmt = exportar.formato_de(formato)
            return sin_dialogos(
                sesion, lambda a: exportar.exportar_individual(a, doc, fmt, out, overwrite)
            )

        ejecutar(
            ctx,
            correr,
            modifica=True,
            plan=plan,
        )


def _validar_salida(fmt: exportar.Formato, out: str, overwrite: bool) -> str | None:
    """Validá `--out` sin COM. Devuelve la ruta de archivo, o None si es una carpeta."""
    if out.endswith(("/", "\\")):
        return None
    if os.path.isdir(out):
        return None
    ruta = exportar.salida_individual(fmt, None, out)
    return documentos.validar_destino(ruta, overwrite)
