"""Comandos de documentos: `se docs list|active|open|new|save|save-as|close`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.core import documentos
from se_cli.core.session import Sesion
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Documentos abiertos de Solid Edge.", no_args_is_help=True)

Selector = Annotated[
    str | None,
    typer.Argument(
        help="Índice (1-based, como `docs list`), nombre o ruta completa. Por defecto, el activo."
    ),
]


def _sin_dialogos(sesion: Sesion, fn):
    """Corré `fn(app)` sin alertas y sin repetirla entera si Solid Edge está ocupado."""
    with sesion.sin_alertas():
        return sesion.llamar(fn, reintentar_todo=False)


@app.command("list")
def listar(ctx: typer.Context) -> None:
    """Listá los documentos abiertos."""

    def correr(sesion):
        lista = sesion.llamar(documentos.listar)
        return {"cantidad": len(lista), "documentos": lista}

    ejecutar(ctx, correr)


@app.command("active")
def activo(ctx: typer.Context) -> None:
    """Mostrá el documento activo (exit 5 si no hay)."""
    ejecutar(ctx, lambda sesion: sesion.llamar(documentos.activo))


@app.command("open")
def abrir(
    ctx: typer.Context,
    ruta: Annotated[str, typer.Argument(help="Archivo a abrir.")],
    read_only_doc: Annotated[
        bool, typer.Option("--read-only-doc", help="Abrí el documento en solo lectura.")
    ] = False,
) -> None:
    """Abrí un documento; si ya está abierto, lo activa."""

    def plan() -> dict[str, Any]:
        absoluta = documentos.validar_ruta_existente(ruta)
        return {"accion": "docs.open", "ruta": absoluta, "solo_lectura": read_only_doc}

    ejecutar(
        ctx,
        lambda sesion: _sin_dialogos(sesion, lambda a: documentos.abrir(a, ruta, read_only_doc)),
        modifica=True,
        plan=plan,
    )


@app.command("new")
def nuevo(
    ctx: typer.Context,
    tipo: Annotated[str, typer.Argument(help="part, assembly, draft, sheetmetal o weldment.")],
    template: Annotated[
        str | None, typer.Option("--template", help="Plantilla (ruta a un .par, .asm, ...).")
    ] = None,
) -> None:
    """Creá un documento nuevo."""

    def plan() -> dict[str, Any]:
        clave = documentos.validar_tipo_nuevo(tipo, template)
        if template:
            documentos.validar_ruta_existente(template, "La plantilla")
        return {
            "accion": "docs.new",
            "tipo": clave,
            "progid": documentos.TIPOS_NUEVOS[clave],
            "plantilla": documentos.ruta_absoluta(template) if template else None,
        }

    ejecutar(
        ctx,
        lambda sesion: _sin_dialogos(sesion, lambda a: documentos.nuevo(a, tipo, template)),
        modifica=True,
        plan=plan,
    )
