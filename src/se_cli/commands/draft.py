"""Comandos de Draft: `se draft from-part`, `parts-list` y `dim`."""

from __future__ import annotations

from typing import Annotated, Any

import typer

from se_cli.commands._comun import DocOpcion, sin_dialogos
from se_cli.core import anotaciones, draft
from se_cli.ejecucion import ejecutar

app = typer.Typer(help="Planos (Draft) de Solid Edge.", no_args_is_help=True)


@app.command("from-part")
def desde_modelo(
    ctx: typer.Context,
    modelo: Annotated[str, typer.Argument(help="Modelo .par, .psm o .asm.")],
    out: Annotated[
        str | None,
        typer.Option("--out", help="Destino .dft. Por defecto, junto al modelo."),
    ] = None,
    views: Annotated[
        str | None,
        typer.Option(
            "--views",
            help="Vistas separadas por coma: front, top, right, left, bottom, back, iso. "
            "Por defecto front,top,right,iso.",
        ),
    ] = None,
    scale: Annotated[
        str,
        typer.Option(
            "--scale",
            help="Escala: 1:2, 2:1, 0.5 o auto (la normalizada más grande que entra).",
        ),
    ] = "auto",
    sheet: Annotated[
        str | None,
        typer.Option("--sheet", help="Hoja ISO apaisada: A5, A4, A3, A2, A1 o A0."),
    ] = None,
    template: Annotated[
        str | None, typer.Option("--template", help="Plantilla de Draft (.dft).")
    ] = None,
    pdf: Annotated[bool, typer.Option("--pdf", help="Exportá también el PDF.")] = False,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Reemplazá el .dft y el PDF si ya existen.")
    ] = False,
    keep_open: Annotated[
        bool, typer.Option("--keep-open", help="Dejá el Draft abierto al terminar.")
    ] = False,
) -> None:
    """Creá un Draft con las vistas de un modelo y guardalo.

    Nunca cierra ni modifica el modelo fuente. El PDF puede salir con marca de agua en Community
    Edition (leyenda "Solid Edge Community Edition" abajo a la izquierda).
    """
    planes: list[draft.Plan] = []

    def plan() -> dict[str, Any]:
        planes[:] = [draft.planificar(modelo, out, views, scale, sheet, template, pdf, overwrite)]
        return {**planes[0].a_dict(), "overwrite": overwrite, "keep_open": keep_open}

    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda a: draft.crear(a, planes[0], overwrite, keep_open)
        ),
        modifica=True,
        plan=plan,
    )


VistaOpcion = Annotated[
    int, typer.Option("--view", help="Vista de la hoja activa, 1-based (por defecto 1).")
]


@app.command("parts-list")
def lista_de_piezas(
    ctx: typer.Context,
    view: VistaOpcion = 1,
    balloons: Annotated[
        bool, typer.Option("--balloons", help="Agregá también los globos automáticos.")
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Insertá la lista de piezas de una vista de ensamble del Draft activo (o `--doc`)."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(
            sesion, lambda a: anotaciones.lista_de_piezas(a, doc, view, balloons)
        ),
        modifica=True,
        plan=lambda: anotaciones.planificar_parts_list(view, balloons),
    )


@app.command("dim")
def acotar(
    ctx: typer.Context,
    view: VistaOpcion = 1,
    auto: Annotated[
        bool,
        typer.Option("--auto", help="Cotas automáticas del modelo (único modo; obligatorio)."),
    ] = False,
    doc: DocOpcion = None,
) -> None:
    """Acotá automáticamente una vista del Draft activo (o `--doc`) con las cotas del modelo."""
    ejecutar(
        ctx,
        lambda sesion: sin_dialogos(sesion, lambda a: anotaciones.cotas_automaticas(a, doc, view)),
        modifica=True,
        plan=lambda: anotaciones.planificar_dim(view, auto),
    )
