"""Comando `se export`: exporta documentos a STEP, STL, Parasolid, IGES, PDF, DXF y PNG."""

from __future__ import annotations

import os
from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import documentos, exportar, lote
from se_cli.core.errors import ArgumentoInvalido
from se_cli.ejecucion import ejecutar


def registrar(app: typer.Typer) -> None:
    @app.command("export")
    def exportar_cmd(
        ctx: typer.Context,
        formato: Annotated[
            str,
            typer.Option(
                "--format",
                help="step, stl, x_t, igs (alias: stp, iges, parasolid), pdf, dxf, png.",
            ),
        ],
        entradas: Annotated[
            list[str] | None,
            typer.Argument(
                help="Archivos, carpetas o globs (lote). Sin entradas, el documento activo."
            ),
        ] = None,
        out: Annotated[
            str | None,
            typer.Option(
                "--out",
                help="Archivo de salida o carpeta (en un lote, siempre carpeta; se crea). "
                "Por defecto, junto al origen.",
            ),
        ] = None,
        overwrite: Annotated[
            bool, typer.Option("--overwrite", help="Reemplazá la salida si ya existe.")
        ] = False,
        recursive: Annotated[
            bool, typer.Option("--recursive", help="En un lote, bajá por las subcarpetas.")
        ] = False,
        doc: DocOpcion = None,
    ) -> None:
        """Exportá el documento activo (o `--doc`), o un lote de archivos.

        Un archivo del lote que ya está abierto se usa sin cerrarlo; si no, se abre, se exporta y
        se cierra sin guardar. Un archivo que falla no corta el lote (exit 1 si alguno falló).
        """
        items: list[lote.Item] = []

        def plan() -> dict[str, Any]:
            fmt = exportar.formato_de(formato)
            if entradas:
                if doc is not None:
                    raise ArgumentoInvalido("--doc no se combina con entradas (lote).")
                items[:] = lote.planificar(entradas, fmt, out, recursive)
                return {
                    "accion": "export",
                    "formato": fmt.clave,
                    "entradas": [{"entrada": i.entrada, "salida": i.salida} for i in items],
                    "overwrite": overwrite,
                }
            salida = _validar_salida(fmt, out, overwrite) if out is not None else None
            return {
                "accion": "export",
                "formato": fmt.clave,
                "entradas": [{"entrada": doc or "activo", "salida": salida}],
                "overwrite": overwrite,
            }

        def correr(sesion):
            fmt = exportar.formato_de(formato)
            if entradas:
                return sin_dialogos(
                    sesion, lambda a: lote.exportar(a, list(items), fmt, out, overwrite)
                )
            return sin_dialogos(
                sesion, lambda a: exportar.exportar_individual(a, doc, fmt, out, overwrite)
            )

        ejecutar(ctx, correr, modifica=True, plan=plan)


def _validar_salida(fmt: exportar.Formato, out: str, overwrite: bool) -> str | None:
    """Validá `--out` sin COM. Devuelve la ruta de archivo, o None si es una carpeta."""
    if out.endswith(("/", "\\")) or os.path.isdir(out):
        return None
    ruta = exportar.salida_individual(fmt, None, out)
    return documentos.validar_destino(ruta, overwrite)
