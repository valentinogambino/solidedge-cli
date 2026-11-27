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

Medido en vivo (2026-11-26, Solid Edge 2026 Community, chapa de 1 mm, arista sobre la cara que
mira hacia donde se levanta la brida):
- `FlangeLength` con `DimSide = igLeft` (`--measure face`, el valor por defecto) se mide desde el
  plano de la cara que contiene la arista hasta el borde libre, siguiendo la cara interior de la
  pared: la pared recta mide `L - r*cot(angulo/2)` y a 90° la altura total sobre la cara opuesta
  es largo + espesor. Es igual con `normal` y con `reverse`. Con `L <= r*cot(angulo/2)` Solid Edge
  rechaza la brida.
- Con `DimSide = igRight` (`--measure opposite`) se mide desde el plano de la cara opuesta, o sea
  contando el espesor: la pared recta mide `L - (r+t)*cot(angulo/2)` (a 90° la altura total es L)
  y Solid Edge rechaza la brida con `L <= (r+t)*cot(angulo/2)`. La base queda igual que con
  `igLeft`. Medido en vivo el 2026-11-27 (45, 60 y 90° con `normal` y `reverse`, y 60° con
  `--length 20mm --radius 2mm`): el volumen calculado coincide con el medido a la décima de mm³.
- `ThicknessSide` no es un sentido sino de qué lado de la arista queda el material: `normal` =
  `seFlangeMaterialInside` (4, la cara exterior de la pared pasa por la arista: pared dentro de la
  huella) y `reverse` = `seFlangeMaterialOutside` (5, la cara interior pasa por la arista: pared
  fuera de la huella). `igLeft`/`igRight` dan E_FAIL (`0x80070057`). El sentido de levante lo fija
  la arista elegida: una arista de la cara superior levanta hacia arriba y una de la inferior,
  hacia abajo. La base siempre se recorta: queda de `W - r*cot(angulo/2)` con `reverse` y de ese
  valor menos `t/sen(angulo)` con `normal`; la pared de `reverse` no es más corta, la base sí es
  más larga (README, "se sheetmetal flange"). `--angle` es el ángulo entre la pared y la base: el
  doblez barre 180 - angulo.
- Verificado en vivo el 2026-11-27 (unas 70 corridas, volumen calculado contra medido a la
  centésima de mm3): espesores de 0,5, 1 y 2 mm (la variable `MaterialThickness`; `BendRadius` no
  la sigue), ángulos de 45, 60, 90, 120 y 135° (Solid Edge acepta más de 90° y la fórmula sigue
  valiendo), base de 100 x 50 y 100 x 80 y brida en el borde corto. El largo mínimo es
  `r*cot(angulo/2)` con `face` y `(r+t)*cot(angulo/2)` con `opposite` a 45, 60, 90 y 120° (a +-1 %).
  Con una pared casi nula a 45 y 120° el volumen baja (la base recortada pesa más que pared y
  doblez): la brida existe, así que `brida_sin_efecto` es un volumen que no cambia, no uno que no
  aumenta. El desarrollo (`flat-dxf --create`) mide `a` por `b + s + (pi - angulo)*(r + K*t)`, con
  `K` = `NeutralFactor`.
- `InsideRadius` vacío toma la variable `BendRadius` del documento al momento de crear la brida;
  el comando la lee y la informa.
- `BendAngle` se pasa en radianes.
"""

from __future__ import annotations

import math
from typing import Any

from se_cli.core import unidades, variables
from se_cli.core.acceso import exigir_tipo, leer, opcional
from se_cli.core.constants import valor as constante
from se_cli.core.errors import (
    ArgumentoInvalido,
    ErrorCom,
    NoConectado,
    NoSoportado,
    Ocupado,
    traducir,
)
from se_cli.core.modelado import (
    DIRECCIONES_DE_TAB,
    _modelo,
    _ultimo_nombre,
    _volumen,
    parsear_longitud,
    validar_direccion,
)
from se_cli.core.redondeos import _aristas_del, _seleccionar, _tipo_de_arista

ANGULO_POR_DEFECTO = 90.0

# `ThicknessSide`: de qué lado de la arista queda el material de la pared (ver el docstring).
LADOS_DE_MATERIAL = {"normal": "seFlangeMaterialInside", "reverse": "seFlangeMaterialOutside"}

# `DimSide` de `FlangeLength`: desde dónde se mide `--length` (ver el docstring).
MEDIDAS = {"face": "igLeft", "opposite": "igRight"}
MEDIDA_POR_DEFECTO = "face"

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


def validar_medida(texto: str) -> str:
    clave = str(texto).strip().lower()
    if clave not in MEDIDAS:
        raise ArgumentoInvalido(
            f"--measure inválido: {texto!r}. Usá {' o '.join(MEDIDAS)}.",
            details={"validas": list(MEDIDAS)},
        )
    return clave


def planificar_brida(
    arista: int,
    longitud: str,
    angulo: float,
    direccion: str,
    radio: str | None,
    medida: str = MEDIDA_POR_DEFECTO,
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
        "medida": validar_medida(medida),
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


def _radio_del_documento(doc: Any) -> float | None:
    """Radio de plegado (variable `BendRadius`) que Solid Edge usa si no se pasa `--radius`."""
    try:
        valor = variables.obtener(doc, "BendRadius")["valor_si"]
    except (Ocupado, NoConectado):
        raise
    except Exception:  # noqa: BLE001 - sin la variable solo se pierde el dato informado
        return None
    return float(valor) if isinstance(valor, (int, float)) else None


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
    medida: str = MEDIDA_POR_DEFECTO,
) -> dict[str, Any]:
    """Brida sobre una arista recta del cuerpo (`Flanges.AddSync`), verificada por volumen."""
    datos = planificar_brida(arista, longitud, angulo, direccion, radio, medida)
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
    radio_origen = "explicito"
    if radio_si is None:
        radio_si, radio_origen = _radio_del_documento(doc), "documento"
        explicito = False
    else:
        explicito = True
    lado = constante(LADOS_DE_MATERIAL[datos["direccion"]])
    medida_desde = constante(MEDIDAS[datos["medida"]])
    angulo_com = vacio if datos["angulo"] == ANGULO_POR_DEFECTO else math.radians(datos["angulo"])
    minimo = (
        "mayor que radio*cot(ángulo/2), el radio a 90°"
        if datos["medida"] == "face"
        else "mayor que (radio+espesor)*cot(ángulo/2), radio+espesor a 90°"
    )
    antes = _volumen(doc)
    flanges = leer(lambda: modelo.Flanges)
    try:
        feature = leer(
            lambda: flanges.AddSync(
                objeto,
                datos["longitud_si"],
                lado,
                radio_si if explicito else vacio,
                medida_desde,
                *([vacio] * 6),
                angulo_com,
            )
        )
    except Exception as causa:  # noqa: BLE001 - se traduce y se vuelve a levantar
        error = traducir(causa)
        if not isinstance(error, ErrorCom):
            raise error from causa
        raise ErrorCom(
            "Solid Edge rechazó la brida con esos parámetros (no cambió el modelo). Probá otro "
            f"--length ({minimo}), --angle (entre unos 2 y 178) o --radius, o --direction "
            f"{'normal' if datos['direccion'] == 'reverse' else 'reverse'}"
            ", o revisá que la arista sirva para una brida.",
            hresult=error.hresult,
            details={
                **(error.details or {}),
                "causa": "brida_rechazada",
                "arista": datos["arista"],
                "longitud_si": datos["longitud_si"],
                "angulo": datos["angulo"],
                "radio_si": radio_si,
            },
        ) from causa
    despues = _volumen(doc)
    if antes is None or despues is None or abs(despues - antes) <= max(1e-15, abs(antes) * 1e-9):
        deshecho = _deshacer(doc)
        raise ErrorCom(
            "Solid Edge no levantó la brida (el volumen no cambió)"
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
        "medida": datos["medida"],
        "radio_si": radio_si,
        "radio_origen": radio_origen if radio_si is not None else None,
        "radio": None if radio_si is None else round(unidades.de_si(radio_si, largo), 12) + 0.0,
        "volumen_antes": antes,
        "volumen_despues": despues,
        "unidades": {"longitud": largo, "angulo": "deg"},
    }


__all__ = ["crear_brida", "planificar_brida", "validar_medida"]
