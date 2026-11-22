"""Propiedades físicas (masa, volumen, inercia...) de piezas y ensamblajes.

Todo en SI en la API (kg, m, m², m³, kg/m³, kg·m²). Sin densidad se lee lo que el modelo ya
tiene guardado (`GetUserPhysicalProperties`, solo lectura). Con densidad se recalcula con
`ComputePhysicalPropertiesWithSpecifiedDensity`, que cambia el estado del documento.
"""

from __future__ import annotations

import math
from typing import Any

from se_cli.core import unidades
from se_cli.core.acceso import exigir_tipo, leer
from se_cli.core.errors import ArgumentoInvalido, ErrorCom, NoConectado, Ocupado

TIPOS_SOPORTADOS = ("part", "sheetmetal", "assembly")

# Precisión relativa pedida al cálculo (0.99 = 99 %).
PRECISION = 0.99

_NOMBRES_INERCIA = ("Ixx", "Iyy", "Izz", "Ixy", "Ixz", "Iyz")

# Cantidad de valores que devuelve cada llamada: 9 (guardadas) u 11 (calculadas, con precisión y
# estado al final).
_LARGOS_VALIDOS = (9, 11)


def validar_densidad(densidad: float | None) -> float | None:
    """La densidad, en kg/m³, tiene que ser un número positivo (exit 2 si no)."""
    if densidad is None:
        return None
    if not math.isfinite(densidad) or densidad <= 0:
        raise ArgumentoInvalido(f"La densidad tiene que ser mayor que 0 (kg/m3): {densidad}.")
    return float(densidad)


def _buffer(n: int) -> list[float]:
    """Arreglo de `n` doubles para un parámetro `[in,out]` (pywin32 lo marshala por referencia)."""
    return [0.0] * n


def _calcular_en_com(objeto: Any, densidad: float) -> Any:
    """Única llamada a `ComputePhysicalPropertiesWithSpecifiedDensity`; corregir acá si falla.

    Los seis arreglos son `[in,out]` y van por nombre (Volume, Area, Mass y los dos últimos son
    `[out]` y vuelven en la tupla de retorno). `Interia` es el typo de Siemens: se respeta.
    Devuelve la tupla de 11: (volumen, área, masa, cdg, cdv, momentos globales, momentos
    principales, ejes principales, radios de giro, precisión lograda, estado).
    """
    return leer(
        lambda: objeto.ComputePhysicalPropertiesWithSpecifiedDensity(
            Density=densidad,
            Accuracy=PRECISION,
            CenterOfGravity=_buffer(3),
            CenterOfVolume=_buffer(3),
            GlobalMomentsOfInteria=_buffer(6),
            PrincipalMomentsOfInteria=_buffer(3),
            PrincipalAxes=_buffer(9),
            RadiiOfGyration=_buffer(3),
        )
    )


def _leer_guardadas_en_com(doc: Any) -> Any:
    """Única llamada a `GetUserPhysicalProperties`: tupla de 9, o `None` si no hay guardadas."""
    try:
        return leer(doc.GetUserPhysicalProperties)
    except (Ocupado, NoConectado):
        raise
    except Exception:
        return None


def _objeto_de_calculo(doc: Any, tipo: str) -> Any:
    """Pieza y chapa calculan sobre su primer `Model`; el ensamble, sobre el documento."""
    if tipo == "assembly":
        return doc
    modelos = leer(lambda: doc.Models)
    if int(leer(lambda: modelos.Count)) < 1:
        raise ArgumentoInvalido("El documento no tiene ningún cuerpo para calcular.")
    return leer(lambda: modelos.Item(1))


def _vector(valores: Any, n: int) -> list[float]:
    try:
        lista = [float(v) for v in valores]
    except (TypeError, ValueError):
        lista = []
    if len(lista) < n:
        raise ErrorCom("Solid Edge devolvió propiedades físicas incompletas.")
    return lista[:n]


def _desempaquetar(resultado: Any) -> dict[str, Any]:
    """Nombrá los valores de la tupla; algo que no sea de 9 u 11 no es un cálculo válido."""
    if not isinstance(resultado, tuple) or len(resultado) not in _LARGOS_VALIDOS:
        recibido = len(resultado) if isinstance(resultado, tuple) else type(resultado).__name__
        raise ErrorCom(
            f"Solid Edge devolvió {recibido} en lugar de 9 u 11 valores de propiedades "
            "físicas: no se calculó nada."
        )
    volumen, area, masa, cdg, cdv, momentos, principales, ejes, radios, *_ = resultado
    return {
        "volumen": float(volumen),
        "area": float(area),
        "masa": float(masa),
        "centro_de_masa": _vector(cdg, 3),
        "centro_de_volumen": _vector(cdv, 3),
        "momentos_de_inercia": dict(zip(_NOMBRES_INERCIA, _vector(momentos, 6), strict=True)),
        "momentos_principales": _vector(principales, 3),
        "ejes_principales": _vector(ejes, 9),
        "radios_de_giro": _vector(radios, 3),
    }


def _factor(elegidas: dict[str, str], dimension: str) -> tuple[str, float]:
    unidad = elegidas.get(dimension, unidades.UNIDAD_SI[dimension])
    return unidad, unidades.FACTORES[dimension][unidad]


def _convertir(si: dict[str, Any], elegidas: dict[str, str]) -> dict[str, Any]:
    """Pasá los campos de SI a las unidades pedidas (`--units`); los ejes no tienen unidad."""
    largo, fl = _factor(elegidas, unidades.LONGITUD)
    masa, fm = _factor(elegidas, unidades.MASA)
    inercia = fm * fl**2

    convertido = dict(si)
    convertido["masa"] = si["masa"] / fm
    convertido["volumen"] = si["volumen"] / fl**3
    convertido["area"] = si["area"] / fl**2
    convertido["densidad"] = None if si["densidad"] is None else si["densidad"] * fl**3 / fm
    for clave in ("centro_de_masa", "centro_de_volumen", "radios_de_giro"):
        convertido[clave] = [v / fl for v in si[clave]]
    convertido["momentos_de_inercia"] = {
        k: v / inercia for k, v in si["momentos_de_inercia"].items()
    }
    convertido["momentos_principales"] = [v / inercia for v in si["momentos_principales"]]
    convertido["unidades"] = {
        "masa": masa,
        "longitud": largo,
        "volumen": f"{largo}^3",
        "area": f"{largo}^2",
        "densidad": f"{masa}/{largo}^3",
        "inercia": f"{masa}*{largo}^2",
    }
    return convertido


def propiedades(
    doc: Any, densidad: float | None = None, elegidas: dict[str, str] | None = None
) -> dict[str, Any]:
    """Propiedades físicas del documento.

    `actualizado` dice si se recalcularon en esta llamada (con `densidad`, que modifica el
    documento) o se leyeron las ya guardadas (`False`, solo lectura).
    """
    tipo = exigir_tipo(doc, TIPOS_SOPORTADOS, "mass")
    if densidad is not None:
        resultado = _calcular_en_com(_objeto_de_calculo(doc, tipo), densidad)
    else:
        resultado = _leer_guardadas_en_com(doc)
        if resultado is None:
            raise ArgumentoInvalido(
                "El documento no tiene propiedades físicas guardadas: pasá --density <kg/m3> "
                "para calcularlas (modifica el estado del documento)."
            )
    si = _desempaquetar(resultado)
    if densidad is not None:
        si["densidad"] = densidad
    else:
        si["densidad"] = si["masa"] / si["volumen"] if si["volumen"] > 0 else None
    convertido = _convertir(si, elegidas or {})
    claves = (
        "masa",
        "volumen",
        "area",
        "densidad",
        "centro_de_masa",
        "centro_de_volumen",
        "momentos_de_inercia",
        "momentos_principales",
        "ejes_principales",
        "radios_de_giro",
    )
    return {
        **{clave: convertido[clave] for clave in claves},
        "actualizado": densidad is not None,
        "unidades": convertido["unidades"],
    }


__all__ = ["PRECISION", "TIPOS_SOPORTADOS", "propiedades", "validar_densidad"]
