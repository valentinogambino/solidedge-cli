"""Unidades: conversión entre SI y unidades de usuario. Python puro, sin COM.

La API de Solid Edge trabaja siempre en SI (metros, radianes, kilogramos). Acá se parsean
valores con unidad (`10mm`, `2.5 in`, `45deg`, `0.01`) y se formatean para mostrarlos en
la unidad pedida. Un valor sin unidad es SI. Solo se acepta el punto como separador decimal.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from se_cli.core.errors import ArgumentoInvalido

LONGITUD = "longitud"
ANGULO = "angulo"
MASA = "masa"

# Factores a SI. 1 in = 0.0254 m exacto, 1 ft = 12 in, 1 lb = 0.45359237 kg (definición legal).
FACTORES: dict[str, dict[str, float]] = {
    LONGITUD: {"m": 1.0, "mm": 0.001, "cm": 0.01, "in": 0.0254, "ft": 0.3048},
    ANGULO: {"rad": 1.0, "deg": math.pi / 180.0},
    MASA: {"kg": 1.0, "g": 0.001, "lb": 0.45359237},
}

UNIDAD_SI: dict[str, str] = {LONGITUD: "m", ANGULO: "rad", MASA: "kg"}

_DIMENSION_DE: dict[str, str] = {
    unidad: dimension for dimension, tabla in FACTORES.items() for unidad in tabla
}

UNIDADES_VALIDAS: tuple[str, ...] = tuple(_DIMENSION_DE)

_NUMERO = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z]*)\s*$")


@dataclass(frozen=True)
class Cantidad:
    """Valor parseado: en SI, con la unidad y dimensión que el usuario escribió (o None)."""

    valor_si: float
    unidad: str | None
    dimension: str | None


def dimension_de(unidad: str) -> str:
    """Dimensión (`longitud`, `angulo`, `masa`) de una unidad, o exit 2 si no existe."""
    clave = unidad.strip()
    if clave not in _DIMENSION_DE:
        raise ArgumentoInvalido(
            f"Unidad desconocida: {unidad!r}. Usá {', '.join(UNIDADES_VALIDAS)}.",
            details={"validas": list(UNIDADES_VALIDAS)},
        )
    return _DIMENSION_DE[clave]


def a_si(valor: float, unidad: str) -> float:
    """Convertí `valor` expresado en `unidad` a SI."""
    return valor * FACTORES[dimension_de(unidad)][unidad.strip()]


def de_si(valor_si: float, unidad: str) -> float:
    """Convertí un valor en SI a `unidad`."""
    return valor_si / FACTORES[dimension_de(unidad)][unidad.strip()]


def parsear_valor(texto: str) -> Cantidad:
    """Parseá `10mm`, `2.5 in`, `45deg` o `0.01` (sin unidad = SI).

    Solo punto decimal: `1,5mm` da exit 2. Cualquier otra cosa que no sea número con unidad
    conocida también.
    """
    if "," in texto:
        raise ArgumentoInvalido(
            f"Valor inválido: {texto!r}. El separador decimal es el punto, no la coma."
        )
    coincidencia = _NUMERO.match(texto)
    if coincidencia is None:
        raise ArgumentoInvalido(
            f"Valor inválido: {texto!r}. Usá un número con unidad opcional (ej. 10mm, 45deg)."
        )
    numero = float(coincidencia.group(1))
    unidad = coincidencia.group(2)
    if not unidad:
        return Cantidad(numero, None, None)
    dimension = dimension_de(unidad)
    return Cantidad(a_si(numero, unidad), unidad, dimension)


def parsear_unidades(texto: str | None) -> dict[str, str]:
    """Parseá `--units`: lista separada por comas, a lo sumo una unidad por dimensión.

    `mm` → `{longitud: mm}`; `mm,deg,lb` → una por dimensión. Vacío o None → `{}`.
    """
    elegidas: dict[str, str] = {}
    if not texto:
        return elegidas
    for parte in texto.split(","):
        unidad = parte.strip()
        if not unidad:
            continue
        dimension = dimension_de(unidad)
        if dimension in elegidas:
            raise ArgumentoInvalido(
                f"--units trae dos unidades de {dimension}: {elegidas[dimension]} y {unidad}."
            )
        elegidas[dimension] = unidad
    return elegidas


def convertir(
    valor_si: float, dimension: str | None, elegidas: dict[str, str]
) -> tuple[float, str | None]:
    """`(valor, unidad)` para mostrar: en la unidad pedida si hay una de esa dimensión.

    Sin unidad pedida (o dimensión desconocida) queda en SI, con su unidad SI si la hay.
    """
    if dimension is None:
        return valor_si, None
    unidad = elegidas.get(dimension, UNIDAD_SI[dimension])
    return de_si(valor_si, unidad), unidad


__all__ = [
    "ANGULO",
    "FACTORES",
    "LONGITUD",
    "MASA",
    "UNIDADES_VALIDAS",
    "UNIDAD_SI",
    "Cantidad",
    "a_si",
    "convertir",
    "de_si",
    "dimension_de",
    "parsear_unidades",
    "parsear_valor",
]
