"""Propiedades físicas (masa, volumen, inercia...) de piezas y ensamblajes.

Todo en SI en la API (kg, m, m², m³, kg/m³, kg·m²). Verificado en vivo (Solid Edge
226.00.01.04, 2026-11-23):

- Pieza y chapa: sin densidad se leen las propiedades guardadas en el modelo con
  `Model.GetPhysicalProperties` (solo lectura; `Status` 1 = hay, 2 = no hay y todo viene en cero).
  Un cálculo con densidad recién queda disponible para esa lectura después de guardar el
  documento. Con densidad se recalcula con `Model.ComputePhysicalPropertiesWithSpecifiedDensity`,
  que cambia el estado del documento. `GetUserPhysicalProperties` solo devuelve valores que el
  usuario cargó a mano, así que no sirve para esto.
- Ensamble: no existe un cálculo con densidad (el documento no tiene
  `ComputePhysicalPropertiesWithSpecifiedDensity`); la masa sale de los materiales de las piezas
  con `PhysicalProperties.GetAssemblyPhysicalProperties`, tras `Update()` si está desactualizado.
  Un ensamble no informa el área (la API devuelve -1). Las piezas sin material cuentan con
  densidad 1 kg/m3, aunque se les haya calculado la masa con una densidad.
"""

from __future__ import annotations

import math
from typing import Any

from se_cli.core import unidades
from se_cli.core.acceso import exigir_tipo, leer
from se_cli.core.errors import ArgumentoInvalido, ErrorCom, NoSoportado

TIPOS_SOPORTADOS = ("part", "sheetmetal", "assembly")

# Precisión relativa pedida al cálculo (0.99 = 99 %).
PRECISION = 0.99

_NOMBRES_INERCIA = ("Ixx", "Iyy", "Izz", "Ixy", "Ixz", "Iyz")

# `Status` de `Model.GetPhysicalProperties` cuando hay un cálculo vigente.
ESTADO_CALCULADO = 1

# Cantidad de valores que devuelve el cálculo de un `Model` (con precisión y estado al final).
_LARGO_CALCULO = 11


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


def _leer_pieza_en_com(modelo: Any) -> Any:
    """Única llamada a `Model.GetPhysicalProperties`: tupla de 13 con el estado al principio.

    Los seis arreglos son `[in,out]` y van por nombre, como en el cálculo.
    """
    return leer(
        lambda: modelo.GetPhysicalProperties(
            Density=0.0,
            Accuracy=0.0,
            CenterOfGravity=_buffer(3),
            CenterOfVolume=_buffer(3),
            GlobalMomentsOfInteria=_buffer(6),
            PrincipalMomentsOfInteria=_buffer(3),
            PrincipalAxes=_buffer(9),
            RadiiOfGyration=_buffer(3),
        )
    )


def _largo_invalido(resultado: Any) -> ErrorCom:
    recibido = len(resultado) if isinstance(resultado, tuple) else type(resultado).__name__
    return ErrorCom(f"Solid Edge devolvió {recibido} en lugar de 13 valores de propiedades.")


def _normalizar_lectura_de_pieza(resultado: Any) -> tuple[tuple, float] | None:
    """Pasá la tupla de 13 de `GetPhysicalProperties` a la forma del cálculo; None si no hay."""
    if not isinstance(resultado, tuple) or len(resultado) != 13:
        raise _largo_invalido(resultado)
    estado, densidad, precision, volumen, area, masa, *vectores, _ = resultado
    if estado != ESTADO_CALCULADO or any(v is None for v in vectores):
        return None
    return (volumen, area, masa, *vectores, precision, estado), float(densidad)


def _leer_ensamble_en_com(doc: Any) -> tuple[Any, bool]:
    """`GetAssemblyPhysicalProperties` (tupla de 13) y si hubo que correr `Update()` antes."""
    props = leer(lambda: doc.PhysicalProperties)
    actualizado = False
    if not leer(lambda: props.IsUpToDate):
        leer(props.Update)
        actualizado = True
    return leer(props.GetAssemblyPhysicalProperties), actualizado


def _normalizar_ensamble(resultado: Any) -> tuple:
    """Pasá la tupla de 13 del ensamble a la forma del cálculo (área -1 queda en None)."""
    if not isinstance(resultado, tuple) or len(resultado) != 13:
        raise _largo_invalido(resultado)
    masa, volumen, area, cdm, cdv, momentos, eje1, eje2, eje3, principales, radios, enfermo, _ = (
        resultado
    )
    if enfermo:
        raise ErrorCom("Solid Edge marcó las propiedades físicas del ensamble como inválidas.")
    ejes = (*eje1, *eje2, *eje3)
    area = area if area >= 0 else None
    return (volumen, area, masa, cdm, cdv, momentos, principales, ejes, radios)


def _objeto_de_calculo(doc: Any) -> Any:
    """Pieza y chapa calculan sobre su primer `Model`."""
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
    if not isinstance(resultado, tuple) or len(resultado) not in (9, _LARGO_CALCULO):
        recibido = len(resultado) if isinstance(resultado, tuple) else type(resultado).__name__
        raise ErrorCom(
            f"Solid Edge devolvió {recibido} en lugar de 9 u 11 valores de propiedades "
            "físicas: no se calculó nada."
        )
    volumen, area, masa, cdg, cdv, momentos, principales, ejes, radios, *_ = resultado
    return {
        "volumen": float(volumen),
        "area": None if area is None else float(area),
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
    convertido["area"] = None if si["area"] is None else si["area"] / fl**2
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

    `actualizado` dice si se recalcularon en esta llamada (con `densidad` en pieza y chapa, que
    modifica el documento; o el `Update()` de un ensamble desactualizado) o se leyó el último
    cálculo (`False`, solo lectura).
    """
    tipo = exigir_tipo(doc, TIPOS_SOPORTADOS, "mass")
    actualizado = densidad is not None
    densidad_leida = None
    if tipo == "assembly":
        if densidad is not None:
            raise NoSoportado(
                "Un ensamble no admite --density: la masa sale de los materiales de sus piezas "
                "(una pieza sin material cuenta con densidad 1 kg/m3). Asignales un material."
            )
        crudo, actualizado = _leer_ensamble_en_com(doc)
        resultado = _normalizar_ensamble(crudo)
    elif densidad is not None:
        resultado = _calcular_en_com(_objeto_de_calculo(doc), densidad)
    else:
        lectura = _normalizar_lectura_de_pieza(_leer_pieza_en_com(_objeto_de_calculo(doc)))
        if lectura is None:
            raise ArgumentoInvalido(
                "El documento no tiene propiedades físicas guardadas: pasá --density <kg/m3> "
                "para calcularlas (modifica el estado del documento; recién se pueden leer sin "
                "densidad después de guardarlo)."
            )
        resultado, densidad_leida = lectura
    si = _desempaquetar(resultado)
    if densidad is not None:
        si["densidad"] = densidad
    elif densidad_leida is not None:
        si["densidad"] = densidad_leida
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
        "actualizado": actualizado,
        "unidades": convertido["unidades"],
    }


__all__ = ["PRECISION", "TIPOS_SOPORTADOS", "propiedades", "validar_densidad"]
