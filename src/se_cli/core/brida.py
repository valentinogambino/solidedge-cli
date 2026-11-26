"""Brida de chapa: `se sheetmetal flange` sobre `Flanges.AddSync`.

Todo en SI (metros, radianes) hacia y desde Solid Edge; `--units` solo cambia lo que se muestra.
Verificado en vivo antes de este comando (Solid Edge 2026, `tests/test_vivo_chapa.py`, y el MCP
de referencia): la brida solo resuelve con `Flanges.AddSync` sobre una base creada en modo
sincrónico (`se sheetmetal tab --sync`); en modo ordenado `Flanges.Add*` registra una operación
que nunca resuelve. Cambiar el modo después de un Tab ordenado da E_FAIL.

Firma usada (typelib `part.tlb`):
`AddSync(pLocatedEdge, FlangeLength, ThicknessSide, InsideRadius, DimSide, BRType, BRWidth,
BRLength, CRType, NeutralFactor, BnParamType, BendAngle, FlangeType, PartialFlangeStartPoint)`.
Los argumentos que no se piden van como `VT_EMPTY` y toman el valor por defecto de Solid Edge.
Se pasan los doce primeros (hasta `BendAngle`), como el script de `test_vivo_chapa.py`.

Sin probar en vivo todavía (ver `PENDIENTE-VIVO` en el README): la semántica exacta de
`FlangeLength`, el valor de `ThicknessSide` para `--direction reverse` y si `InsideRadius` vacío
toma el radio de plegado del documento.
"""

from __future__ import annotations

import math
from typing import Any

from se_cli.core import unidades
from se_cli.core.acceso import exigir_tipo, leer, opcional
from se_cli.core.constants import valor as constante
from se_cli.core.errors import ArgumentoInvalido, ErrorCom, NoConectado, NoSoportado, Ocupado
from se_cli.core.modelado import (
    DIRECCIONES_DE_TAB,
    _lado,
    _modelo,
    _ultimo_nombre,
    _volumen,
    parsear_longitud,
    validar_direccion,
)
from se_cli.core.redondeos import _aristas_del, _seleccionar, _tipo_de_arista

ANGULO_POR_DEFECTO = 90.0

PISTA_BASE_ORDENADA = (
    "Creá la base de la chapa con `se sheetmetal tab --sync` (modo sincrónico) y después la brida."
)


# --- Validación local (sin COM) ---------------------------------------------------------------


def validar_arista(arista: int) -> int:
    if isinstance(arista, bool) or not isinstance(arista, int) or arista < 1:
        raise ArgumentoInvalido(
            f"--edge inválido: {arista!r}. Usá el índice (desde 1) de `se edges list`."
        )
    return arista


def validar_angulo(grados: float) -> float:
    """Ángulo de la brida en grados, en el rango abierto (0, 180)."""
    if not math.isfinite(grados) or grados <= 0 or grados >= 180:
        raise ArgumentoInvalido(f"--angle tiene que estar entre 0 y 180 grados: {grados!r}.")
    return float(grados)


def planificar_brida(
    arista: int, longitud: str, angulo: float, direccion: str, radio: str | None
) -> dict[str, Any]:
    direccion = validar_direccion(direccion)
    if direccion not in DIRECCIONES_DE_TAB:
        raise ArgumentoInvalido(
            f"Una brida no admite --direction {direccion}: usá normal o reverse.",
            details={"validas": list(DIRECCIONES_DE_TAB)},
        )
    return {
        "accion": "sheetmetal.flange",
        "arista": validar_arista(arista),
        "longitud_si": parsear_longitud(longitud, "--length"),
        "angulo": validar_angulo(angulo),
        "direccion": direccion,
        "radio_si": None if radio is None else parsear_longitud(radio, "--radius"),
    }


# --- Acceso COM -------------------------------------------------------------------------------


def _vacio() -> Any:
    import pythoncom
    from win32com.client import VARIANT

    return VARIANT(pythoncom.VT_EMPTY, None)


def _exigir_base_sincronica(doc: Any) -> Any:
    """Modelo base de una chapa en modo sincrónico; si no, exit 2 (sin base) o 6 (ordenada)."""
    exigir_tipo(doc, ("sheetmetal",), "sheetmetal flange")
    modelo = _modelo(doc)
    if modelo is None:
        raise ArgumentoInvalido(
            "La chapa no tiene base: creala con `se sheetmetal tab --sync` antes de la brida.",
            details={"modelo_base": False, "hint": PISTA_BASE_ORDENADA},
        )
    modo = opcional(lambda: int(doc.ModelingMode))
    if modo == constante("seModelingModeOrdered"):
        raise NoSoportado(
            "La brida solo funciona sobre una base creada en modo sincrónico, y esta chapa está "
            f"en modo ordenado. {PISTA_BASE_ORDENADA}",
            details={"causa": "base_ordenada", "modo": "ordenado", "hint": PISTA_BASE_ORDENADA},
        )
    return modelo


def _deshacer(doc: Any) -> bool:
    try:
        leer(lambda: doc.Undo())
    except (Ocupado, NoConectado):
        raise
    except Exception:
        return False
    return True


def crear_brida(
    doc: Any,
    arista: int,
    longitud: str,
    angulo: float,
    direccion: str,
    radio: str | None,
    elegidas: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Brida sobre una arista recta del cuerpo (`Flanges.AddSync`), verificada por volumen."""
    datos = planificar_brida(arista, longitud, angulo, direccion, radio)
    modelo = _exigir_base_sincronica(doc)
    aristas = _aristas_del(leer(lambda: modelo.Body))
    _, elegida = _seleccionar(aristas, [datos["arista"]])
    objeto = elegida[0]
    tipo = _tipo_de_arista(objeto)
    if tipo != "linea":
        raise ArgumentoInvalido(
            f"La arista {datos['arista']} no es recta (es {tipo}): la brida va sobre una arista "
            "recta. Elegí otra con `se edges list` (tipo `linea`).",
            details={"arista": datos["arista"], "tipo": tipo},
        )
    vacio = _vacio()
    radio_si = datos["radio_si"]
    lado = vacio if datos["direccion"] == "normal" else _lado("reverse")
    angulo_com = vacio if datos["angulo"] == ANGULO_POR_DEFECTO else math.radians(datos["angulo"])
    antes = _volumen(doc)
    flanges = leer(lambda: modelo.Flanges)
    feature = leer(
        lambda: flanges.AddSync(
            objeto,
            datos["longitud_si"],
            lado,
            vacio if radio_si is None else radio_si,
            *([vacio] * 7),
            angulo_com,
        )
    )
    despues = _volumen(doc)
    if antes is None or despues is None or despues - antes <= max(1e-15, abs(antes) * 1e-9):
        deshecho = _deshacer(doc)
        raise ErrorCom(
            "Solid Edge no levantó la brida (el volumen no aumentó)"
            + (": se deshizo." if deshecho else " y no se pudo deshacer: revisá el modelo."),
            details={
                "causa": "brida_sin_efecto",
                "arista": datos["arista"],
                "deshecho": deshecho,
                "volumen_antes": antes,
                "volumen_despues": despues,
            },
        )
    elegidas = elegidas or {}
    largo = elegidas.get(unidades.LONGITUD, unidades.UNIDAD_SI[unidades.LONGITUD])
    nombre = opcional(lambda: str(feature.Name)) or _ultimo_nombre(flanges)
    return {
        "operacion": "brida",
        "nombre": nombre,
        "arista": datos["arista"],
        "longitud_si": datos["longitud_si"],
        "longitud": round(unidades.de_si(datos["longitud_si"], largo), 12) + 0.0,
        "angulo": datos["angulo"],
        "direccion": datos["direccion"],
        "radio_si": radio_si,
        "radio": None if radio_si is None else round(unidades.de_si(radio_si, largo), 12) + 0.0,
        "volumen_antes": antes,
        "volumen_despues": despues,
        "unidades": {"longitud": largo, "angulo": "deg"},
    }


__all__ = ["crear_brida", "planificar_brida"]
