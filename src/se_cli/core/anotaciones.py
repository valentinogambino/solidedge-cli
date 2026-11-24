"""Anotaciones sobre un Draft: lista de piezas con globos y cotas automáticas.

`se draft parts-list` usa `PartsLists.Add(vista, "", autoGlobos, 1)` del Draft y
`se draft dim --auto` usa `DrawingView.RetrieveDimensions()`; ambas se verificaron en vivo.
Las vistas se numeran de 1 a N como salen de `Sheet.DrawingViews` (el orden en que se agregaron).
Las funciones reciben la `Application` ya verificada y no importan pywin32.
"""

from __future__ import annotations

import os
from typing import Any

from se_cli.core import acceso
from se_cli.core.acceso import leer, opcional
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado


def validar_vista(vista: int) -> int:
    """Número de vista 1-based; menor que 1 es un error de uso (exit 2)."""
    if vista < 1:
        raise ArgumentoInvalido(
            f"--view tiene que ser 1 o más (1-based): {vista}", details={"vista": vista}
        )
    return vista


def planificar_parts_list(vista: int, globos: bool) -> dict[str, Any]:
    """Validá los argumentos de `draft parts-list` sin COM."""
    return {"accion": "draft.parts-list", "vista": validar_vista(vista), "globos": globos}


def planificar_dim(vista: int, auto: bool) -> dict[str, Any]:
    """Validá los argumentos de `draft dim` sin COM: `--auto` es el único modo."""
    if not auto:
        raise ArgumentoInvalido(
            "`draft dim` solo acota automáticamente: `--auto` es obligatorio en esta versión "
            "y es el único modo.",
            details={"auto": False},
        )
    return {"accion": "draft.dim", "vista": validar_vista(vista), "auto": True}


def _contar(coleccion_de: Any) -> int | None:
    """`Count` de la colección que devuelve `coleccion_de()`, o None si la API no la ofrece."""
    cantidad = opcional(lambda: coleccion_de().Count)
    return None if cantidad is None else int(cantidad)


def _draft_y_vista(app: Any, doc: str | None, vista: int, comando: str) -> tuple[Any, Any]:
    """Draft elegido y su vista número `vista`; exit 2 si no es un Draft, 5 si no hay esa vista."""
    draft = acceso.documento(app, doc)
    acceso.exigir_tipo(draft, ("draft",), comando)
    vistas = leer(lambda: draft.ActiveSheet.DrawingViews)
    cantidad = int(leer(lambda: vistas.Count))
    if vista > cantidad:
        raise DocNoEncontrado(
            f"La hoja activa tiene {cantidad} vistas: no existe la vista {vista}.",
            details={"vista": vista, "vistas": cantidad},
        )
    return draft, leer(lambda: vistas.Item(vista))


def lista_de_piezas(app: Any, doc: str | None, vista: int, globos: bool) -> dict[str, Any]:
    """Insertá la lista de piezas de la vista `vista` (de un ensamble), con globos si se pide."""
    draft, dibujo = _draft_y_vista(app, doc, vista, "draft parts-list")
    modelo = opcional(lambda: str(dibujo.ModelLink.FileName))
    if modelo is not None and os.path.splitext(modelo)[1].lower() != ".asm":
        # Solid Edge no la rechaza con una vista de pieza: arma una lista de una sola fila.
        raise ArgumentoInvalido(
            f"La vista {vista} no es de un ensamble (modelo {modelo}): la lista de piezas "
            "necesita una vista de un .asm.",
            details={"vista": vista, "modelo": modelo},
        )
    hoja = leer(lambda: draft.ActiveSheet)
    globos_antes = _contar(lambda: hoja.Balloons)
    listas = leer(lambda: draft.PartsLists)
    lista = leer(lambda: listas.Add(dibujo, "", 1 if globos else 0, 1))
    globos_despues = _contar(lambda: hoja.Balloons)
    filas = opcional(lambda: int(lista.Rows.Count))
    puestos = None
    if globos_antes is not None and globos_despues is not None:
        puestos = globos_despues - globos_antes
    return {
        "vista": vista,
        "modelo": modelo,
        "filas": filas,
        "globos": globos,
        "globos_agregados": puestos,
    }


def cotas_automaticas(app: Any, doc: str | None, vista: int) -> dict[str, Any]:
    """Recuperá las cotas del modelo en la vista `vista` (`RetrieveDimensions`).

    Las cotas se cuentan en toda la hoja (`Sheet.Dimensions`): es lo que la API da. Una vista que
    ya tenía sus cotas recuperadas da 0 agregadas.
    """
    draft, dibujo = _draft_y_vista(app, doc, vista, "draft dim")
    hoja = leer(lambda: draft.ActiveSheet)
    antes = _contar(lambda: hoja.Dimensions)
    leer(lambda: dibujo.RetrieveDimensions())
    despues = _contar(lambda: hoja.Dimensions)
    agregadas = None if antes is None or despues is None else despues - antes
    return {
        "vista": vista,
        "cotas_antes": antes,
        "cotas_despues": despues,
        "cotas_agregadas": agregadas,
    }


__all__ = [
    "cotas_automaticas",
    "lista_de_piezas",
    "planificar_dim",
    "planificar_parts_list",
    "validar_vista",
]
