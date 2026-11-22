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


def listar(doc: Any) -> dict[str, Any]:
    """Operaciones en orden: `{indice (1-based), nombre, tipo, suprimida, estado}`."""
    exigir_tipo(doc, TIPOS_SOPORTADOS, "features list")
    features = _de_modelos(doc) or _de_edgebar(doc)
    lista = [_describir(i, f) for i, f in enumerate(features, start=1)]
    return {"cantidad": len(lista), "operaciones": lista}


__all__ = ["TIPOS_SOPORTADOS", "listar", "nombre_de_estado", "nombre_de_tipo"]
