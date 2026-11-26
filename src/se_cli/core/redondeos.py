"""Aristas del cuerpo y operaciones sobre ellas: `edges list`, redondeos y chaflanes.

Todo en SI (metros, radianes) hacia y desde Solid Edge; `--units` solo cambia lo que se muestra.
Verificado en vivo (Solid Edge 2026 226.00.01.04, 2026-11-23, caja de 50x30x20 mm):

- `Model.Body.Edges(igQueryAll)` funciona en late binding y da las 12 aristas de la caja, sin
  repetir las que comparten dos caras. El orden es estable mientras el cuerpo no cambia; después
  de cualquier operación que lo modifica (un redondeo agrega aristas) hay que volver a leerlas.
- De una arista se leen `Geometry.Type` (`igLine`, `igCircle`, ...), `IsClosed`,
  `GetEndPoints(...)`, `GetParamExtents()` + `GetLengthAtParam(min, max)` y `GetFaces()` (devuelve
  `(cantidad, (caras...))` con objetos crudos que se comparan con `==` contra `Body.Faces`).
  `Edge.Length`, `Edge.Faces` y `Edge.Name` no existen.
- `Model.Rounds.Add(n, aristas, radios)`, `Model.Chamfers.AddEqualSetback(n, aristas, distancia)`
  y `Model.Chamfers.AddSetbackAngle(cara, n, aristas, distancia, angulo)` aceptan una lista de
  aristas de Python. Una sola operación cubre todas las aristas pedidas.
- Si la geometría no resulta (radio demasiado grande, arista tangente) Solid Edge NO levanta un
  error: crea la operación con `Status == igFeatureFailed` y el resto de las operaciones nuevas
  también fallan hasta que se la borra. Se detecta con `Status` y se deshace con `Delete()`.
- `Round.GetConstantRadii()` devuelve `(n, radios)`; `Chamfer.ChamferSetbackValue1` y
  `ChamferSetbackAngle` devuelven los valores usados.
"""

from __future__ import annotations

import math
import re
from typing import Any

from se_cli.core import unidades
from se_cli.core.acceso import items, leer, opcional, tipo_de
from se_cli.core.constants import (
    FeatureStatusConstants,
    GNTTypePropertyConstants,
)
from se_cli.core.constants import valor as constante
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    ErrorCom,
    NoConectado,
    Ocupado,
)
from se_cli.core.modelado import _modelo, _volumen, exigir_modelable, parsear_longitud
from se_cli.core.operaciones import indice_de_operacion

TODAS = "all"

_ESTADO_FALLIDO = int(FeatureStatusConstants.igFeatureFailed)

_TIPO_DE_CARA = {
    int(GNTTypePropertyConstants.igPlane): "plano",
    int(GNTTypePropertyConstants.igCylinder): "cilindro",
    int(GNTTypePropertyConstants.igCone): "cono",
    int(GNTTypePropertyConstants.igSphere): "esfera",
    int(GNTTypePropertyConstants.igTorus): "toro",
    int(GNTTypePropertyConstants.igBSplineSurface): "bspline",
}


# --- Validación local (sin COM) ---------------------------------------------------------------


def parsear_aristas(texto: str) -> str | list[int]:
    """`all` o una lista de índices 1-based: `1,3,5`, rangos `1-4` o mezclas (`1-3,7`).

    Devuelve `"all"` o los índices sin repetir y ordenados. Exit 2 si no se entiende.
    """
    clave = texto.strip().lower()
    if clave == TODAS:
        return TODAS
    indices: set[int] = set()
    for parte in clave.split(","):
        pedazo = parte.strip()
        rango = re.fullmatch(r"(\d+)\s*-\s*(\d+)", pedazo)
        if rango is not None:
            desde, hasta = int(rango.group(1)), int(rango.group(2))
            if desde < 1 or hasta < desde:
                raise ArgumentoInvalido(
                    f"Rango de aristas inválido: {pedazo!r} (de menor a mayor, desde 1)."
                )
            indices.update(range(desde, hasta + 1))
        elif pedazo.isdigit() and int(pedazo) >= 1:
            indices.add(int(pedazo))
        else:
            raise ArgumentoInvalido(
                f"--edges inválido: {texto!r}. Usá all, índices (1,3,5) o rangos (1-4), "
                "desde 1 (como `se edges list`)."
            )
    return sorted(indices)


def parsear_angulo_de_chaflan(texto: str) -> float:
    """Ángulo en radianes, mayor que 0 y menor que 90 grados (sin unidad = radianes)."""
    cantidad = unidades.parsear_valor(texto)
    if cantidad.dimension not in (None, unidades.ANGULO):
        raise ArgumentoInvalido(f"--angle tiene que ser un ángulo (ej. 30deg): {texto!r}.")
    radianes = cantidad.valor_si
    if not math.isfinite(radianes) or radianes <= 0 or radianes >= math.pi / 2 - 1e-9:
        raise ArgumentoInvalido(f"--angle tiene que estar entre 0 y 90deg: {texto!r}.")
    return radianes


def planificar_round(radio: str, aristas: str) -> dict[str, Any]:
    return {
        "accion": "round",
        "radio_si": parsear_longitud(radio, "El radio"),
        "aristas": parsear_aristas(aristas),
    }


def planificar_chamfer(distancia: str, angulo: str | None, aristas: str) -> dict[str, Any]:
    return {
        "accion": "chamfer",
        "distancia_si": parsear_longitud(distancia, "La distancia"),
        "angulo_si": None if angulo is None else parsear_angulo_de_chaflan(angulo),
        "aristas": parsear_aristas(aristas),
    }


def _convertido(valor_si: float, unidad: str) -> float:
    return round(unidades.de_si(valor_si, unidad), 12) + 0.0


def _mostrar(valor_si: float, dimension: str, elegidas: dict[str, str]) -> float:
    return _convertido(valor_si, _unidad(dimension, elegidas))


def _unidad(dimension: str, elegidas: dict[str, str]) -> str:
    return elegidas.get(dimension, unidades.UNIDAD_SI[dimension])


# --- Lectura de la topología ------------------------------------------------------------------


def _cuerpo(doc: Any, comando: str, *, admite_sincronico: bool = False) -> tuple[Any, Any]:
    """`(modelo, cuerpo)` de una pieza o chapa en modo ordenado; si no, exit 2.

    `admite_sincronico` (solo lectura) deja pasar una chapa en modo sincrónico, la que arma
    `se sheetmetal tab --sync`.
    """
    exigir_modelable(doc, comando, admite_sincronico=admite_sincronico)
    modelo = _modelo(doc)
    if modelo is None:
        raise ArgumentoInvalido(
            f"`{comando}` necesita un modelo con cuerpo: hacé primero una extrusión (`se extrude`)."
        )
    return modelo, leer(lambda: modelo.Body)


def _es_chapa(doc: Any) -> bool:
    return opcional(lambda: tipo_de(doc)) == "sheetmetal"


def _aristas_del(cuerpo: Any) -> list[Any]:
    return list(items(leer(lambda: cuerpo.Edges(constante("igQueryAll")))))


def _caras_del(cuerpo: Any) -> list[Any]:
    return list(items(leer(lambda: cuerpo.Faces(constante("igQueryAll")))))


def _caras_de(arista: Any, caras: list[Any]) -> list[int]:
    """Índices (1-based) en `caras` de las caras que tocan la arista (las no ubicadas se omiten)."""
    crudo = opcional(lambda: arista.GetFaces())
    if crudo is None:
        return []
    lista = crudo[1] if len(crudo) == 2 and isinstance(crudo[0], int) else crudo
    encontradas = []
    for cara in lista or ():
        for indice, candidata in enumerate(caras, start=1):
            if candidata == cara:
                encontradas.append(indice)
                break
    return sorted(set(encontradas))


def _tipo_de_arista(arista: Any) -> str:
    codigo = opcional(lambda: int(arista.Geometry.Type))
    if codigo == int(GNTTypePropertyConstants.igLine):
        return "linea"
    if codigo == int(GNTTypePropertyConstants.igCircle):
        cerrada = opcional(lambda: bool(arista.IsClosed))
        return "circulo" if cerrada else "arco"
    return "otra"


def _longitud(arista: Any) -> float | None:
    def medir() -> float:
        minimo, maximo = arista.GetParamExtents()[:2]
        largo = arista.GetLengthAtParam(minimo, maximo)
        return float(largo[0] if isinstance(largo, tuple) else largo)

    return opcional(medir)


def _extremos(arista: Any) -> tuple[list[float], list[float]] | None:
    def leer_extremos() -> tuple[list[float], list[float]]:
        inicio, fin = arista.GetEndPoints([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])[:2]
        return [float(v) for v in inicio], [float(v) for v in fin]

    return opcional(leer_extremos)


def _describir_arista(
    indice: int, arista: Any, caras: list[Any], tipos_de_cara: dict[int, str], largo: str
) -> dict[str, Any]:
    longitud = _longitud(arista)
    extremos = _extremos(arista)
    return {
        "indice": indice,
        "tipo": _tipo_de_arista(arista),
        "longitud": None if longitud is None else _convertido(longitud, largo),
        "inicio": None if extremos is None else [_convertido(v, largo) for v in extremos[0]],
        "fin": None if extremos is None else [_convertido(v, largo) for v in extremos[1]],
        "caras": [
            {"indice": i, "tipo": tipos_de_cara.get(i, "otra")} for i in _caras_de(arista, caras)
        ],
    }


def _tipos_de_cara(caras: list[Any]) -> dict[int, str]:
    tipos = {}
    for indice, cara in enumerate(caras, start=1):
        codigo = opcional(lambda cara=cara: int(cara.Geometry.Type))
        tipos[indice] = _TIPO_DE_CARA.get(codigo, "otra") if codigo is not None else "otra"
    return tipos


def listar(doc: Any, elegidas: dict[str, str] | None = None) -> dict[str, Any]:
    """Aristas del cuerpo: `{indice, tipo, longitud, inicio, fin, caras}` con índice 1-based.

    El índice vale solo para esta lectura del cuerpo: cambia después de cada operación que lo
    modifica. `caras` son los índices (1-based) de `Body.Faces` que tocan la arista, con su tipo.
    """
    _, cuerpo = _cuerpo(doc, "edges list", admite_sincronico=_es_chapa(doc))
    largo = _unidad(unidades.LONGITUD, elegidas or {})
    aristas = _aristas_del(cuerpo)
    caras = _caras_del(cuerpo)
    tipos = _tipos_de_cara(caras)
    return {
        "cantidad": len(aristas),
        "cantidad_caras": len(caras),
        "aristas": [_describir_arista(i, a, caras, tipos, largo) for i, a in enumerate(aristas, 1)],
        "unidades": {"longitud": largo},
    }


def _seleccionar(aristas: list[Any], pedidas: str | list[int]) -> tuple[list[int], list[Any]]:
    """Índices y objetos de las aristas pedidas; un índice fuera de rango da exit 5."""
    if not aristas:
        raise ArgumentoInvalido("El cuerpo no tiene aristas.")
    if pedidas == TODAS:
        indices = list(range(1, len(aristas) + 1))
    else:
        indices = list(pedidas)
        fuera = [i for i in indices if i > len(aristas)]
        if fuera:
            raise DocNoEncontrado(
                f"No existe la arista {fuera[0]}: el cuerpo tiene {len(aristas)} "
                "(corré `se edges list`; los índices cambian con cada operación).",
                details={"fuera_de_rango": fuera, "cantidad": len(aristas)},
            )
    return indices, [aristas[i - 1] for i in indices]


# --- Operaciones ------------------------------------------------------------------------------


def _borrar_fallida(coleccion: Any, cantidad_antes: int) -> tuple[str | None, bool]:
    """Borra lo último creado si hay algo nuevo; `(nombre, borrada)`."""
    cantidad = int(leer(lambda: coleccion.Count))
    if cantidad <= cantidad_antes:
        return None, True
    nueva = leer(lambda: coleccion.Item(cantidad))
    nombre = str(opcional(lambda: nueva.Name) or "") or None
    try:
        leer(lambda: nueva.Delete())
    except (Ocupado, NoConectado):
        raise
    except Exception:
        return nombre, False
    return nombre, int(leer(lambda: coleccion.Count)) <= cantidad_antes


def _crear(
    doc: Any,
    comando: str,
    coleccion_de: str,
    pedidas: str | list[int],
    que: str,
    agregar: Any,
    cara_comun: bool = False,
) -> tuple[Any, list[int], Any, float | None, float | None]:
    """Corre `agregar(coleccion, aristas, cara)` y verifica la operación que dejó Solid Edge.

    Devuelve `(feature, indices, coleccion, volumen_antes, volumen_despues)`.
    """
    modelo, cuerpo = _cuerpo(doc, comando)
    aristas = _aristas_del(cuerpo)
    indices, elegidas = _seleccionar(aristas, pedidas)
    cara = None
    if cara_comun:
        cara = _cara_de_referencia(cuerpo, elegidas, indices)
    coleccion = leer(lambda: getattr(modelo, coleccion_de))
    cantidad_antes = int(leer(lambda: coleccion.Count))
    antes = _volumen(doc)
    try:
        feature = leer(lambda: agregar(coleccion, elegidas, cara))
    except (Ocupado, NoConectado):
        raise
    except Exception:
        _borrar_fallida(coleccion, cantidad_antes)
        raise
    estado = opcional(lambda: int(feature.Status))
    if estado == _ESTADO_FALLIDO:
        nombre, borrada = _borrar_fallida(coleccion, cantidad_antes)
        consecuencia = (
            "se borró, así que el modelo quedó como estaba."
            if borrada
            else f"no se pudo borrar: borrá {nombre or 'la operación'} a mano en Solid Edge."
        )
        raise ErrorCom(
            f"Solid Edge no pudo crear {que} con esas aristas (geometría imposible, por ejemplo "
            f"un valor demasiado grande): la operación quedó fallida y {consecuencia}",
            details={
                "operacion_fallida": nombre,
                "borrada": borrada,
                "aristas": indices,
                "estado": "failed",
            },
        )
    return feature, indices, coleccion, antes, _volumen(doc)


def _cara_de_referencia(cuerpo: Any, elegidas: list[Any], indices: list[int]) -> Any:
    """Cara común a todas las aristas: el chaflán distancia + ángulo se mide desde ella."""
    caras = _caras_del(cuerpo)
    comunes: set[int] | None = None
    for arista in elegidas:
        de_esta = set(_caras_de(arista, caras))
        comunes = de_esta if comunes is None else comunes & de_esta
    if not comunes:
        raise ArgumentoInvalido(
            "Con --angle todas las aristas tienen que compartir una cara (el ángulo se mide "
            "desde ella). Elegí aristas de una misma cara (ver `caras` en `se edges list`).",
            details={"aristas": indices},
        )
    return caras[min(comunes) - 1]


def _datos_comunes(
    feature: Any,
    indices: list[int],
    coleccion: Any,
    doc: Any,
    antes: float | None,
    despues: float | None,
) -> dict[str, Any]:
    nombre = str(opcional(lambda: feature.Name) or "")
    estado = opcional(lambda: int(feature.Status))
    quitado = None if antes is None or despues is None else antes - despues
    return {
        "nombre": nombre,
        "indice": opcional(lambda: indice_de_operacion(doc, nombre)),
        "cantidad_aristas": len(indices),
        "aristas": indices,
        "estado": "ok" if estado == int(FeatureStatusConstants.igFeatureOK) else estado,
        "volumen_si": despues,
        "volumen_quitado_si": quitado,
    }


def redondear(
    doc: Any, radio: str, aristas: str, elegidas: dict[str, str] | None = None
) -> dict[str, Any]:
    """Redondeo de radio constante sobre las aristas pedidas (una sola operación)."""
    datos = planificar_round(radio, aristas)
    r = datos["radio_si"]

    def agregar(coleccion: Any, seleccion: list[Any], _cara: Any) -> Any:
        return coleccion.Add(len(seleccion), seleccion, [r] * len(seleccion))

    feature, indices, coleccion, antes, despues = _crear(
        doc, "round", "Rounds", datos["aristas"], "el redondeo", agregar
    )
    leido = opcional(lambda: float(feature.GetConstantRadii()[1][0]))
    elegidas = elegidas or {}
    return {
        "operacion": "redondeo",
        **_datos_comunes(feature, indices, coleccion, doc, antes, despues),
        "radio": _mostrar(r if leido is None else leido, unidades.LONGITUD, elegidas),
        "unidades": {"longitud": _unidad(unidades.LONGITUD, elegidas)},
    }


def achaflanar(
    doc: Any,
    distancia: str,
    angulo: str | None,
    aristas: str,
    elegidas: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Chaflán de distancias iguales; con `angulo`, distancia + ángulo desde una cara común."""
    datos = planificar_chamfer(distancia, angulo, aristas)
    d, a = datos["distancia_si"], datos["angulo_si"]

    def agregar(coleccion: Any, seleccion: list[Any], cara: Any) -> Any:
        if a is None:
            return coleccion.AddEqualSetback(len(seleccion), seleccion, d)
        return coleccion.AddSetbackAngle(cara, len(seleccion), seleccion, d, a)

    feature, indices, coleccion, antes, despues = _crear(
        doc,
        "chamfer",
        "Chamfers",
        datos["aristas"],
        "el chaflán",
        agregar,
        cara_comun=a is not None,
    )
    leida = opcional(lambda: float(feature.ChamferSetbackValue1))
    leido_angulo = None
    if a is not None:
        leido_angulo = opcional(lambda: float(feature.ChamferSetbackAngle))
    elegidas = elegidas or {}
    return {
        "operacion": "chaflan",
        **_datos_comunes(feature, indices, coleccion, doc, antes, despues),
        "distancia": _mostrar(d if leida is None else leida, unidades.LONGITUD, elegidas),
        "angulo": (
            None
            if a is None
            else _mostrar(a if leido_angulo is None else leido_angulo, unidades.ANGULO, elegidas)
        ),
        "unidades": {
            "longitud": _unidad(unidades.LONGITUD, elegidas),
            "angulo": _unidad(unidades.ANGULO, elegidas),
        },
    }


__all__ = [
    "achaflanar",
    "listar",
    "parsear_aristas",
    "planificar_chamfer",
    "planificar_round",
    "redondear",
]
