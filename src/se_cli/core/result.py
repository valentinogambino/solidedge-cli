"""Sobre de resultado `{ok, data, error}` y serialización JSON segura."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date, datetime, time
from enum import Enum
from pathlib import PurePath
from typing import Any

from se_cli.core.errors import SeError

LARGO_REPR = 80


def ok(data: Any = None) -> dict[str, Any]:
    """Sobre de éxito: `{"ok": True, "data": data, "error": None}`."""
    return {"ok": True, "data": data, "error": None}


def fallo(error: SeError) -> dict[str, Any]:
    """Sobre de fallo: `{"ok": False, "data": None, "error": {code, message, ...}}`."""
    return {"ok": False, "data": None, "error": error.a_dict()}


def _repr_corto(valor: Any) -> str:
    texto = repr(valor)
    return texto if len(texto) <= LARGO_REPR else texto[: LARGO_REPR - 3] + "..."


def a_serializable(valor: Any) -> Any:
    """Convertí a tipos JSON los valores típicos de COM.

    Fechas (incluidas las de `pywintypes`, que son `datetime`) a ISO, tuplas y sets a listas,
    enums a su valor, rutas a texto, NaN e infinitos a None y cualquier otro objeto
    (por ejemplo un COM) a un `repr` corto.
    """
    if valor is None or isinstance(valor, (bool, int, str)):
        return valor
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return a_serializable(valor.value)
    if isinstance(valor, PurePath):
        return str(valor)
    if isinstance(valor, Mapping):
        return {str(clave): a_serializable(item) for clave, item in valor.items()}
    if isinstance(valor, (set, frozenset)):
        return sorted((a_serializable(item) for item in valor), key=repr)
    if isinstance(valor, (list, tuple)):
        return [a_serializable(item) for item in valor]
    return _repr_corto(valor)


def a_json(resultado: Any, *, indent: int | None = None) -> str:
    """Serializá un sobre (o cualquier dato) a JSON, sin escapar no ASCII."""
    return json.dumps(a_serializable(resultado), ensure_ascii=False, indent=indent)
