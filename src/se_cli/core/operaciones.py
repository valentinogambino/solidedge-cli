"""Operaciones (features) de una pieza o chapa, en el orden del modelo.

La fuente normal es `Models.Item(n).Features`. Una pieza pasada de modo ordenado a sincrónico
deja ese listado vacío y las operaciones solo se ven en `DesignEdgebarFeatures`, que además trae
los planos de referencia; esos no tienen `Suppress`, así que se descartan (una entrada que no
puede responder "¿suprimida?" no es una operación).
"""

from __future__ import annotations

from typing import Any

from se_cli.core.acceso import exigir_tipo, items, leer, opcional
from se_cli.core.constants import FeatureStatusConstants, FeatureTypeConstants
from se_cli.core.errors import DocNoEncontrado, ErrorCom

TIPOS_SOPORTADOS = ("part", "sheetmetal")

_SUPRIMIDA = int(FeatureStatusConstants.igFeatureSuppressed)


def nombre_de_tipo(codigo: Any) -> str | int | None:
    """Nombre legible de `FeatureTypeConstants` (`ExtrudedProtrusion`); el entero si no hay."""
    if codigo is None:
        return None
    try:
        nombre = FeatureTypeConstants(int(codigo)).name
    except (TypeError, ValueError):
        return codigo if isinstance(codigo, int) else None
    return nombre.removeprefix("ig").removesuffix("FeatureObject").removesuffix("Feature")


def nombre_de_estado(codigo: Any) -> str | int | None:
    """Estado legible (`ok`, `failed`, `warned`, `suppressed`, `rolledback`)."""
    if codigo is None:
        return None
    try:
        return FeatureStatusConstants(int(codigo)).name.removeprefix("igFeature").lower()
    except (TypeError, ValueError):
        return codigo if isinstance(codigo, int) else None


def _describir(indice: int, feature: Any) -> dict[str, Any]:
    estado = opcional(lambda: feature.Status)
    suprimida = opcional(lambda: feature.Suppress)
    if suprimida is None and estado is not None:
        suprimida = estado == _SUPRIMIDA
    return {
        "indice": indice,
        "nombre": str(opcional(lambda: feature.Name) or ""),
        "tipo": nombre_de_tipo(opcional(lambda: feature.Type)),
        "suprimida": None if suprimida is None else bool(suprimida),
        "estado": nombre_de_estado(estado),
    }


def _de_modelos(doc: Any) -> list[Any]:
    features: list[Any] = []
    for modelo in items(leer(lambda: doc.Models)):
        coleccion = opcional(lambda modelo=modelo: modelo.Features)
        if coleccion is not None:
            features.extend(items(coleccion))
    return features


def _de_edgebar(doc: Any) -> list[Any]:
    coleccion = opcional(lambda: doc.DesignEdgebarFeatures)
    if coleccion is None:
        return []
    return [f for f in items(coleccion) if opcional(lambda f=f: f.Suppress) is not None]


def _todas(doc: Any) -> list[Any]:
    return _de_modelos(doc) or _de_edgebar(doc)


def listar(doc: Any) -> dict[str, Any]:
    """Operaciones en orden: `{indice (1-based), nombre, tipo, suprimida, estado}`."""
    exigir_tipo(doc, TIPOS_SOPORTADOS, "features list")
    lista = [_describir(i, f) for i, f in enumerate(_todas(doc), start=1)]
    return {"cantidad": len(lista), "operaciones": lista}


def _buscar(features: list[Any], selector: str) -> tuple[int, Any]:
    """Operación por índice (1-based, como `features list`) o nombre exacto; si no, exit 5."""
    texto = selector.strip()
    if texto.isdigit():
        indice = int(texto)
        if 1 <= indice <= len(features):
            return indice, features[indice - 1]
        raise DocNoEncontrado(
            f"No existe la operación con índice {indice}: el documento tiene {len(features)}.",
            details={"indice": indice, "cantidad": len(features)},
        )
    buscado = texto.casefold()
    for indice, feature in enumerate(features, start=1):
        if str(opcional(lambda feature=feature: feature.Name) or "").casefold() == buscado:
            return indice, feature
    raise DocNoEncontrado(
        f"No existe la operación {selector!r} en el documento.", details={"nombre": selector}
    )


def indice_de_operacion(doc: Any, nombre: str) -> int | None:
    """Índice (1-based, como `features list`) de la operación con ese nombre exacto, o None."""
    for indice, feature in enumerate(_todas(doc), start=1):
        if str(opcional(lambda feature=feature: feature.Name) or "") == nombre:
            return indice
    return None


def cambiar_supresion(doc: Any, selector: str, suprimir: bool) -> dict[str, Any]:
    """Suprimí o reactivá una operación. Devuelve su descripción y `changed`.

    Idempotente: si ya está en el estado pedido no se escribe nada y `changed` es `false`.
    Lo que se informa es lo que Solid Edge tiene después de escribir, no lo que se pidió.
    """
    comando = "features suppress" if suprimir else "features unsuppress"
    exigir_tipo(doc, TIPOS_SOPORTADOS, comando)
    indice, feature = _buscar(_todas(doc), selector)
    antes = _describir(indice, feature)
    if antes["suprimida"] is suprimir:
        return {**antes, "changed": False}
    leer(lambda: setattr(feature, "Suppress", suprimir))
    despues = _describir(indice, feature)
    if despues["suprimida"] is not suprimir:
        raise ErrorCom(
            f"Solid Edge no dejó {antes['nombre']!r} "
            f"{'suprimida' if suprimir else 'activa'}: sigue en estado {despues['estado']}.",
            details=despues,
        )
    return {**despues, "changed": True}


__all__ = [
    "TIPOS_SOPORTADOS",
    "cambiar_supresion",
    "indice_de_operacion",
    "listar",
    "nombre_de_estado",
    "nombre_de_tipo",
]
