"""Comandos de documentos: `se docs list|active|open|new|save|save-as|close`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import sin_dialogos
from se_cli.core import documentos
from se_cli.core.errors import ArgumentoInvalido, TiempoAgotado
from se_cli.core.session import Sesion
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Documentos abiertos de Solid Edge.", no_args_is_help=True)

Selector = Annotated[
    str | None,
    typer.Argument(
        help="Índice (1-based, como `docs list`), nombre o ruta completa. Por defecto, el activo."
    ),
]


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
        bool,
        typer.Option("--read-only-doc", help="Pedí solo lectura (la API no lo soporta: avisa)."),
    ] = False,
) -> None:
    """Abrí un documento; si ya está abierto, lo activa."""

    def plan() -> dict[str, Any]:
        absoluta = documentos.validar_ruta_existente(ruta)
        return {"accion": "docs.open", "ruta": absoluta, "solo_lectura": read_only_doc}

    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(sesion, lambda a: documentos.abrir(a, ruta, read_only_doc)),
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

    def correr(sesion):
        try:
            return sin_dialogos(sesion, lambda a: documentos.nuevo(a, tipo, template))
        except TiempoAgotado as error:
            # `Documents.Add` sigue en Solid Edge aunque se deje de esperar: no se cierra solo.
            error.mensaje += (
                " El documento nuevo pudo quedar creado igual: revisá `se docs list` antes de "
                "repetir el comando."
            )
            error.args = (error.mensaje,)
            error.details["documento_pudo_crearse"] = True
            raise

    ejecutar(ctx, correr, modifica=True, plan=plan)


@app.command("save")
def guardar(ctx: typer.Context, documento: Selector = None) -> None:
    """Guardá el documento activo o el indicado."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(sesion, lambda a: documentos.guardar(a, documento)),
        modifica=True,
        plan=lambda: {"accion": "docs.save", "documento": documento or "activo"},
    )


@app.command("save-as")
def guardar_como(
    ctx: typer.Context,
    destino: Annotated[str, typer.Argument(help="Ruta del archivo de destino.")],
    documento: Selector = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Reemplazá el destino si ya existe.")
    ] = False,
) -> None:
    """Guardá el documento en otra ruta. No pisa un archivo existente sin --overwrite."""

    def plan() -> dict[str, Any]:
        absoluta = documentos.validar_destino(destino, overwrite)
        return {
            "accion": "docs.save-as",
            "documento": documento or "activo",
            "destino": absoluta,
            "overwrite": overwrite,
        }

    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda a: documentos.guardar_como(a, destino, documento, overwrite)
        ),
        modifica=True,
        plan=plan,
    )


@app.command("close")
def cerrar(
    ctx: typer.Context,
    documento: Selector = None,
    save: Annotated[
        bool, typer.Option("--save", help="Guardá los cambios antes de cerrar.")
    ] = False,
    discard: Annotated[
        bool, typer.Option("--discard", help="Descartá los cambios sin guardar.")
    ] = False,
    todos: Annotated[bool, typer.Option("--all", help="Cerrá todos (exige --yes).")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirmá --all.")] = False,
) -> None:
    """Cerrá un documento. Con cambios sin guardar exige --save o --discard."""

    def plan() -> dict[str, Any]:
        if save and discard:
            raise ArgumentoInvalido("--save y --discard son excluyentes.")
        if todos and documento is not None:
            raise ArgumentoInvalido("--all no se combina con un documento.")
        if todos and not yes:
            raise ArgumentoInvalido("Cerrar todos los documentos exige --yes.")
        return {
            "accion": "docs.close",
            "documento": "todos" if todos else (documento or "activo"),
            "save": save,
            "discard": discard,
        }

    def correr(sesion: Sesion):
        if todos:
            return sin_dialogos(sesion, lambda a: documentos.cerrar_todos(a, save, discard))
        return sin_dialogos(sesion, lambda a: documentos.cerrar(a, documento, save, discard))

    ejecutar(ctx, correr, modifica=True, plan=plan)
