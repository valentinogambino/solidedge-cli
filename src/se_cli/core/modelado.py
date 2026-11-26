"""Modelado básico de piezas: perfiles (sketch), extrusión, revolución y agujeros.

Las funciones reciben el documento COM ya resuelto y no importan pywin32. Todo en SI (metros,
radianes). Verificado en vivo (Solid Edge 2026 226.00.01.04, 2026-11-23):

- Planos de referencia de la plantilla de Part: `RefPlanes.Item(1)` es `top` (plano XY, normal
  +Z), `Item(2)` es `right` (plano YZ, normal +X) y `Item(3)` es `front` (plano XZ, normal -Y).
  En el perfil, `x` e `y` son: top = (X, Y), right = (Y, Z), front = (X, Z).
- Un perfil es un `ProfileSet` con un `Profile`. Después de crear una operación el perfil
  sigue en `ProfileSets` y se puede reutilizar. El identificador estable del perfil es el
  índice (1-based) de su `ProfileSet`.
- `Profile.End(igProfileClosed)` devuelve -103 con un rectángulo de cuatro líneas aunque es válido
  (con un círculo devuelve 0): se aceptan los dos.
- La primera operación crea el modelo (`Models.AddFinite...`); las siguientes se agregan con
  `Model.ExtrudedProtrusions.AddFiniteMulti`, `ExtrudedCutouts.AddFiniteMulti`,
  `ExtrudedCutouts.AddThroughAllMulti` y `RevolvedProtrusions.AddFiniteMulti`.
- Un corte que no toca material no da error: crea una operación vacía. Se detecta comparando
  `Body.Volume` antes y después y se deshace con `Feature.Delete()`.
- El eje de una revolución es una línea de construcción del perfil (`ToggleConstruction`) marcada
  con `Profile.SetAxisOfRevolution`; se puede agregar aun con el perfil ya cerrado.
"""

from __future__ import annotations

import contextlib
import math
import re
from typing import Any

from se_cli.core import croquis, unidades
from se_cli.core.acceso import exigir_tipo, leer, opcional
from se_cli.core.constants import valor as constante
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    ErrorCom,
    NoSoportado,
    SeError,
    traducir,
)

TIPOS_MODELABLES = ("part", "sheetmetal")

PLANOS: dict[str, int] = {"top": 1, "right": 2, "front": 3}
_NOMBRE_DE_PLANO = {indice: nombre for nombre, indice in PLANOS.items()}

DIRECCIONES: dict[str, str] = {
    "normal": "igRight",
    "reverse": "igLeft",
    "symmetric": "igSymmetric",
}

EJES = ("x", "y")

# `Profile.End` devuelve 0 o -103 con un perfil bien armado (ver el docstring del módulo).
FIN_DE_PERFIL_VALIDO = (0, -103)

# Bandera de `Profile.End` que admite lazos anidados (un círculo o un contorno dentro de otro). No
# está en el typelib: la documenta el MCP y se verificó en vivo (2026-11-24). Sin ella un perfil
# con un lazo adentro de otro da -113 al cerrarlo y no extruye; con ella, y con los extremos
# unidos por relaciones, cierra con 0 y extruye con el agujero.
PERFIL_ANIDADO = 8192

# Largo (en metros) de la línea de construcción que hace de eje de revolución.
LARGO_DE_EJE = 0.5


# --- Validación local (sin COM) ---------------------------------------------------------------


def parsear_longitud(texto: str, que: str, *, positiva: bool = True) -> float:
    """Longitud en SI de `10mm` (o un número sin unidad = metros). Exit 2 si no sirve."""
    cantidad = unidades.parsear_valor(texto)
    if cantidad.dimension not in (None, unidades.LONGITUD):
        raise ArgumentoInvalido(f"{que} tiene que ser una longitud (ej. 10mm): {texto!r}.")
    if not math.isfinite(cantidad.valor_si):
        raise ArgumentoInvalido(f"{que} no es un número finito: {texto!r}.")
    if positiva and cantidad.valor_si <= 0:
        raise ArgumentoInvalido(f"{que} tiene que ser mayor que 0: {texto!r}.")
    return cantidad.valor_si


def parsear_angulo(texto: str, que: str = "El ángulo") -> float:
    """Ángulo en radianes de `90deg` (o un número sin unidad = radianes), mayor que 0 y ≤ 360°."""
    cantidad = unidades.parsear_valor(texto)
    if cantidad.dimension not in (None, unidades.ANGULO):
        raise ArgumentoInvalido(f"{que} tiene que ser un ángulo (ej. 90deg): {texto!r}.")
    radianes = cantidad.valor_si
    if not math.isfinite(radianes) or radianes <= 0 or radianes > 2 * math.pi + 1e-9:
        raise ArgumentoInvalido(f"{que} tiene que estar entre 0 y 360deg: {texto!r}.")
    return min(radianes, 2 * math.pi)


def parsear_punto(texto: str | None, que: str = "--at") -> tuple[float, float]:
    """`X,Y` con unidad opcional en cada valor. Sin texto es el origen."""
    if texto is None:
        return 0.0, 0.0
    partes = texto.split(",")
    if len(partes) != 2 or not all(p.strip() for p in partes):
        raise ArgumentoInvalido(f"{que} tiene que ser X,Y (ej. 10mm,5mm): {texto!r}.")
    x, y = (parsear_longitud(p, f"{que} (coordenada)", positiva=False) for p in partes)
    return x, y


def validar_plano(texto: str) -> int | str:
    """Plano `top|front|right` (devuelve su índice COM) o un índice numérico (1-based)."""
    clave = texto.strip().lower()
    if clave in PLANOS:
        return PLANOS[clave]
    if clave.isdigit() and int(clave) >= 1:
        return int(clave)
    raise ArgumentoInvalido(
        f"Plano inválido: {texto!r}. Usá top, front, right o un índice de RefPlanes (1, 2, 3...).",
        details={"validos": [*PLANOS, "<índice>"]},
    )


def validar_direccion(texto: str) -> str:
    clave = texto.strip().lower()
    if clave not in DIRECCIONES:
        raise ArgumentoInvalido(
            f"Dirección inválida: {texto!r}. Usá {', '.join(DIRECCIONES)}.",
            details={"validas": list(DIRECCIONES)},
        )
    return clave


def validar_eje(texto: str) -> str:
    clave = texto.strip().lower()
    if clave not in EJES:
        raise ArgumentoInvalido(
            f"Eje inválido: {texto!r}. Usá x (la recta y=0 del perfil) o y (la recta x=0)."
        )
    return clave


def validar_perfil(texto: str | None) -> int | None:
    """Identificador de perfil: `3` o `ProfileSet_3`. None = el último disponible."""
    if texto is None:
        return None
    clave = texto.strip()
    coincidencia = re.fullmatch(r"(?:ProfileSet_)?(\d+)", clave, flags=re.IGNORECASE)
    if coincidencia is None or int(coincidencia.group(1)) < 1:
        raise ArgumentoInvalido(
            f"Perfil inválido: {texto!r}. Usá el número devuelto por `se sketch` (ej. 2)."
        )
    return int(coincidencia.group(1))


def _lado(direccion: str) -> int:
    return constante(DIRECCIONES[direccion])


def _nombre_de_plano(indice: int) -> str:
    return _NOMBRE_DE_PLANO.get(indice, f"plano {indice}")


# --- Acceso COM -------------------------------------------------------------------------------


def exigir_modelable(doc: Any, comando: str, *, admite_sincronico: bool = False) -> str:
    """Pieza o chapa en modo ordenado; si no, exit 2 con la explicación.

    Con `admite_sincronico` (solo para leer, sin modificar) también acepta el modo sincrónico.
    """
    tipo = exigir_tipo(doc, TIPOS_MODELABLES, comando)
    modo = opcional(lambda: int(doc.ModelingMode))
    if modo == constante("seModelingModeSynchronous") and not admite_sincronico:
        raise ArgumentoInvalido(
            f"`{comando}` solo funciona con el documento en modo ordenado, y este está en modo "
            "sincrónico. Cambiá a modo ordenado en Solid Edge.",
            details={"modo": "sincronico"},
        )
    return tipo


def _plano(doc: Any, indice: int) -> Any:
    planos = leer(lambda: doc.RefPlanes)
    cantidad = int(leer(lambda: planos.Count))
    if indice > cantidad:
        raise ArgumentoInvalido(
            f"El documento tiene {cantidad} planos de referencia; no existe el {indice}.",
            details={"planos": cantidad},
        )
    return leer(lambda: planos.Item(indice))


def _volumen(doc: Any) -> float | None:
    """`Body.Volume` del primer modelo (siempre se vuelve a pedir: el cuerpo cambia)."""
    valor = opcional(lambda: float(doc.Models.Item(1).Body.Volume))
    return None if valor is None else float(valor)


def _modelo(doc: Any) -> Any | None:
    """Primer modelo del documento, o None si todavía no hay ninguna operación."""
    modelos = leer(lambda: doc.Models)
    if int(leer(lambda: modelos.Count)) == 0:
        return None
    return leer(lambda: modelos.Item(1))


def _nuevo_perfil(doc: Any, indice_plano: int) -> tuple[int, Any]:
    plano = _plano(doc, indice_plano)
    conjuntos = leer(lambda: doc.ProfileSets)
    conjunto = leer(lambda: conjuntos.Add())
    perfil = leer(lambda: conjunto.Profiles.Add(plano))
    return int(leer(lambda: conjuntos.Count)), perfil


def _cerrar_perfil(perfil: Any, anidado: bool = False) -> int:
    bandera = constante("igProfileClosed") | (PERFIL_ANIDADO if anidado else 0)
    codigo = leer(lambda: perfil.End(bandera))
    codigo = int(codigo or 0)
    if codigo not in FIN_DE_PERFIL_VALIDO:
        raise ErrorCom(
            f"Solid Edge no pudo cerrar el perfil (Profile.End devolvió {codigo}).",
            details={"codigo_end": codigo},
        )
    return codigo


def resolver_perfil(doc: Any, identificador: int | None) -> tuple[int, Any]:
    """`(índice, Profile)`: el indicado, o el último `ProfileSet` que tenga un perfil."""
    conjuntos = leer(lambda: doc.ProfileSets)
    cantidad = int(leer(lambda: conjuntos.Count))
    if identificador is None:
        for indice in range(cantidad, 0, -1):
            conjunto = leer(lambda i=indice: conjuntos.Item(i))
            if int(leer(lambda c=conjunto: c.Profiles.Count)) > 0:
                return indice, leer(lambda c=conjunto: c.Profiles.Item(1))
        raise DocNoEncontrado(
            "El documento no tiene perfiles. Creá uno con `se sketch rect` o `se sketch circle`.",
            details={"perfiles": 0},
        )
    if identificador > cantidad:
        raise DocNoEncontrado(
            f"No existe el perfil {identificador} (el documento tiene {cantidad}).",
            details={"perfiles": cantidad},
        )
    conjunto = leer(lambda: conjuntos.Item(identificador))
    if int(leer(lambda: conjunto.Profiles.Count)) == 0:
        raise DocNoEncontrado(f"El perfil {identificador} está vacío.")
    return identificador, leer(lambda: conjunto.Profiles.Item(1))


# --- Sketch -----------------------------------------------------------------------------------


def planificar_rect(
    plano: str, ancho: str, alto: str, en: str | None, centrado: bool
) -> dict[str, Any]:
    indice = validar_plano(plano)
    x, y = parsear_punto(en)
    return {
        "accion": "sketch.rect",
        "plano": plano,
        "plano_indice": indice,
        "ancho_si": parsear_longitud(ancho, "--width"),
        "alto_si": parsear_longitud(alto, "--height"),
        "x_si": x,
        "y_si": y,
        "centrado": centrado,
    }


def planificar_circulo(
    plano: str, radio: str | None, diametro: str | None, en: str | None
) -> dict[str, Any]:
    indice = validar_plano(plano)
    x, y = parsear_punto(en)
    return {
        "accion": "sketch.circle",
        "plano": plano,
        "plano_indice": indice,
        "radio_si": _radio(radio, diametro),
        "x_si": x,
        "y_si": y,
    }


def _radio(radio: str | None, diametro: str | None) -> float:
    if (radio is None) == (diametro is None):
        raise ArgumentoInvalido("Pasá --radius o --diameter (uno solo).")
    if radio is not None:
        return parsear_longitud(radio, "--radius")
    return parsear_longitud(diametro or "", "--diameter") / 2.0


def crear_rect(doc: Any, plano: str, ancho: str, alto: str, en: str | None, centrado: bool) -> Any:
    """Perfil rectangular cerrado en un plano de referencia."""
    datos = planificar_rect(plano, ancho, alto, en, centrado)
    exigir_modelable(doc, "sketch rect")
    w, h = datos["ancho_si"], datos["alto_si"]
    x, y = datos["x_si"], datos["y_si"]
    x0, y0 = (x - w / 2, y - h / 2) if centrado else (x, y)
    indice, perfil = _nuevo_perfil(doc, datos["plano_indice"])
    lineas = leer(lambda: perfil.Lines2d)
    vertices = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]
    for origen, destino in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        leer(lambda o=origen, d=destino: lineas.AddBy2Points(*o, *d))
    codigo = _cerrar_perfil(perfil)
    return _resultado_de_perfil(
        indice,
        datos["plano_indice"],
        "rect",
        {"ancho": w, "alto": h, "x": x, "y": y, "centrado": centrado},
        codigo,
    )


def crear_circulo(
    doc: Any, plano: str, radio: str | None, diametro: str | None, en: str | None
) -> Any:
    """Perfil circular cerrado en un plano de referencia."""
    datos = planificar_circulo(plano, radio, diametro, en)
    exigir_modelable(doc, "sketch circle")
    r, x, y = datos["radio_si"], datos["x_si"], datos["y_si"]
    indice, perfil = _nuevo_perfil(doc, datos["plano_indice"])
    circulos = leer(lambda: perfil.Circles2d)
    leer(lambda: circulos.AddByCenterRadius(x, y, r))
    codigo = _cerrar_perfil(perfil)
    return _resultado_de_perfil(
        indice,
        datos["plano_indice"],
        "circulo",
        {"radio": r, "diametro": 2 * r, "x": x, "y": y},
        codigo,
    )


# --- Perfil declarativo (`sketch profile`) ----------------------------------------------------

# Índices de keypoint de `Relations2d.AddKeypoint`, verificados en vivo (2026-11-24): línea
# 0=inicio, 1=fin, 2=medio; arco 0=centro, 1=inicio, 2=fin, 3=medio; círculo 0=centro. El arco
# de `Arcs2d.AddByCenterStartEnd` siempre barre antihorario de inicio a fin: uno `cw` se crea
# con inicio y fin intercambiados, y sus keypoints start/end se cruzan.
_KEYPOINT = {
    "line": {"start": 0, "end": 1},
    "arc": {"start": 1, "end": 2, "center": 0},
    "circle": {"center": 0},
}
_RELACION_DE = {
    "horizontal": "AddHorizontal",
    "vertical": "AddVertical",
    "parallel": "AddParallel",
    "perpendicular": "AddPerpendicular",
    "equal": "AddEqual",
    "concentric": "AddConcentric",
    "tangent": "AddTangent",
}


def planificar_perfil(perfil: croquis.Perfil) -> dict[str, Any]:
    return perfil.plan()


def _keypoint(entidad: dict[str, Any], punto: str) -> int:
    if entidad["tipo"] == "arc" and entidad["dir"] == "cw" and punto in ("start", "end"):
        punto = "end" if punto == "start" else "start"
    return _KEYPOINT[entidad["tipo"]][punto]


def _agregar_entidad(perfil: Any, entidad: dict[str, Any]) -> Any:
    tipo = entidad["tipo"]
    if tipo == "line":
        lineas = leer(lambda: perfil.Lines2d)
        return leer(lambda: lineas.AddBy2Points(*entidad["desde"], *entidad["hasta"]))
    if tipo == "circle":
        circulos = leer(lambda: perfil.Circles2d)
        return leer(lambda: circulos.AddByCenterRadius(*entidad["centro"], entidad["radio"]))
    inicio, fin = entidad["inicio"], entidad["fin"]
    if entidad["dir"] == "cw":
        inicio, fin = fin, inicio
    arcos = leer(lambda: perfil.Arcs2d)
    return leer(lambda: arcos.AddByCenterStartEnd(*entidad["centro"], *inicio, *fin))


def _agregar_restriccion(
    relaciones: Any, restriccion: dict[str, Any], objetos: dict[str, Any], datos: dict[str, Any]
) -> None:
    if restriccion["tipo"] == "connect":
        (id_a, punto_a), (id_b, punto_b) = restriccion["a"], restriccion["b"]
        kp_a, kp_b = _keypoint(datos[id_a], punto_a), _keypoint(datos[id_b], punto_b)
        leer(lambda: relaciones.AddKeypoint(objetos[id_a], kp_a, objetos[id_b], kp_b))
        return
    metodo = _RELACION_DE[restriccion["tipo"]]
    argumentos = [objetos[i] for i in restriccion["entidades"]]
    leer(lambda: getattr(relaciones, metodo)(*argumentos))


def _borrar_conjunto(conjunto: Any) -> bool:
    try:
        leer(lambda: conjunto.Delete())
    except Exception:  # noqa: BLE001 - es limpieza: el error original es el que importa
        return False
    return True


def _con_etapa(error: Exception, etapa: str, borrado: bool, extra: dict[str, Any]) -> SeError:
    traducido = traducir(error)
    if traducido.codigo == "interno":
        traducido = ErrorCom(f"{type(error).__name__}: {error}")
    traducido.details = {
        **(traducido.details or {}),
        "etapa": etapa,
        **extra,
        "perfil_borrado": borrado,
    }
    return traducido


def crear_perfil(doc: Any, perfil: croquis.Perfil) -> dict[str, Any]:
    """Perfil cerrado de líneas, arcos y círculos con restricciones (ya validado, ver `croquis`).

    Si algo falla una vez creado el `ProfileSet`, se borra y el error sale con la etapa en
    `details` (`perfil`, `entidades`, `restricciones` o `cierre`).
    """
    exigir_modelable(doc, "sketch profile")
    plano_indice = int(perfil.plano_indice)
    plano = _plano(doc, plano_indice)
    conjunto: Any = None
    etapa: str = "perfil"
    extra: dict[str, Any] = {}
    try:
        conjuntos = leer(lambda: doc.ProfileSets)
        conjunto = leer(lambda: conjuntos.Add())
        objeto = leer(lambda: conjunto.Profiles.Add(plano))
        indice = int(leer(lambda: conjuntos.Count))
        etapa = "entidades"
        objetos: dict[str, Any] = {}
        for entidad in perfil.entidades:
            extra = {"entidad": entidad["id"]}
            objetos[entidad["id"]] = _agregar_entidad(objeto, entidad)
        datos = {e["id"]: e for e in perfil.entidades}
        etapa = "restricciones"
        relaciones = leer(lambda: objeto.Relations2d) if perfil.restricciones else None
        for numero, restriccion in enumerate(perfil.restricciones, start=1):
            extra = {"restriccion": numero, "tipo": restriccion["tipo"]}
            _agregar_restriccion(relaciones, restriccion, objetos, datos)
        etapa, extra = "cierre", {}
        codigo = _cerrar_perfil(objeto, anidado=True)
    except Exception as error:  # noqa: BLE001 - se traduce y se limpia
        borrado = conjunto is not None and _borrar_conjunto(conjunto)
        raise _con_etapa(error, etapa, borrado, extra) from error
    resultado = _resultado_de_perfil(
        indice, plano_indice, "perfil", croquis.caja_de(perfil), codigo
    )
    resultado["entidades"] = perfil.conteos()
    resultado["restricciones"] = {
        "aplicadas": len(perfil.restricciones),
        "por_tipo": perfil.por_tipo_de_restriccion(),
    }
    return resultado


def _resultado_de_perfil(
    indice: int, plano: int, tipo: str, dimensiones: dict[str, Any], codigo: int
) -> dict[str, Any]:
    return {
        "perfil": indice,
        "plano": _nombre_de_plano(plano),
        "plano_indice": plano,
        "tipo": tipo,
        "dimensiones_si": dimensiones,
        "valido": True,
        "codigo_end": codigo,
    }


# --- Extrusión --------------------------------------------------------------------------------


def planificar_extrusion(
    distancia: str, perfil: str | None, direccion: str, corte: bool
) -> dict[str, Any]:
    return {
        "accion": "extrude",
        "distancia_si": parsear_longitud(distancia, "La distancia"),
        "perfil": validar_perfil(perfil),
        "direccion": validar_direccion(direccion),
        "corte": corte,
    }


def _ultimo_nombre(coleccion: Any) -> str | None:
    cantidad = int(leer(lambda: coleccion.Count))
    if cantidad == 0:
        return None
    return str(opcional(lambda: coleccion.Item(cantidad).Name) or "") or None


def _deshacer_ultima(coleccion: Any) -> None:
    cantidad = int(leer(lambda: coleccion.Count))
    leer(lambda: coleccion.Item(cantidad).Delete())


def _exigir_efecto(
    coleccion: Any, antes: float | None, despues: float | None, que: str, pista: str
) -> float | None:
    """Un corte que no quita material se deshace y da exit 2. Devuelve el volumen quitado."""
    if antes is None or despues is None:
        return None
    quitado = antes - despues
    if quitado <= max(1e-15, antes * 1e-9):
        _deshacer_ultima(coleccion)
        raise ArgumentoInvalido(
            f"{que} no quitó material (Solid Edge igual crea la operación): se deshizo. {pista}",
            details={"volumen_si": antes},
        )
    return quitado


def extruir(
    doc: Any, distancia: str, perfil: str | None, direccion: str, corte: bool = False
) -> dict[str, Any]:
    """Protrusión finita (o corte con `corte`) de un perfil."""
    datos = planificar_extrusion(distancia, perfil, direccion, corte)
    tipo = exigir_modelable(doc, "extrude")
    if not corte:
        _exigir_base_de_chapa(doc, tipo, "extrude")
    dist, lado = datos["distancia_si"], _lado(datos["direccion"])
    indice, objeto = resolver_perfil(doc, datos["perfil"])
    modelo = _modelo(doc)
    if corte:
        if modelo is None:
            raise ArgumentoInvalido(
                "No hay un modelo base para cortar: hacé primero una extrusión (sin --cut)."
            )
        antes = _volumen(doc)
        cortes = leer(lambda: modelo.ExtrudedCutouts)
        leer(lambda: cortes.AddFiniteMulti(1, (objeto,), lado, dist))
        quitado = _exigir_efecto(
            cortes,
            antes,
            _volumen(doc),
            "El corte",
            "Probá con --direction reverse o revisá que el perfil toque el modelo.",
        )
        return {
            "operacion": "corte",
            "nombre": _ultimo_nombre(cortes),
            "distancia_si": dist,
            "direccion": datos["direccion"],
            "perfil": indice,
            "volumen_si": _volumen(doc),
            "volumen_quitado_si": quitado,
        }
    if modelo is None:
        modelos = leer(lambda: doc.Models)
        leer(lambda: modelos.AddFiniteExtrudedProtrusion(1, (objeto,), lado, dist))
        modelo = _modelo(doc)
        base = True
    else:
        protrusiones = leer(lambda: modelo.ExtrudedProtrusions)
        leer(lambda: protrusiones.AddFiniteMulti(1, (objeto,), lado, dist))
        base = False
    protrusiones = leer(lambda: modelo.ExtrudedProtrusions)
    return {
        "operacion": "extrusion",
        "nombre": _ultimo_nombre(protrusiones),
        "distancia_si": dist,
        "direccion": datos["direccion"],
        "perfil": indice,
        "modelo_base": base,
        "volumen_si": _volumen(doc),
    }


# --- Chapa: la base es un Tab -----------------------------------------------------------------

PISTA_TAB = (
    "Creá la base de la chapa con `se sheetmetal tab` sobre el perfil (por ejemplo, "
    "`se sketch rect` y después `se sheetmetal tab`); el espesor es el del material de la chapa. "
    "Con la base hecha, `se extrude`, `se hole` y `se extrude --cut` funcionan sobre ella."
)


def _exigir_base_de_chapa(doc: Any, tipo: str, comando: str) -> None:
    """En una chapa sin modelo, una protrusión de pieza como base da exit 6 sin tocar nada.

    Verificado en vivo (2026-11-25): `Models.AddFiniteExtrudedProtrusion` en un .psm crea una
    `ExtrudedProtrusion`, no un Tab, y esa chapa no se desarrolla (`flat-dxf --create` no puede
    crear el flat pattern con ninguna arista). Sobre un Tab, una protrusión sí se desarrolla.
    """
    if tipo != "sheetmetal" or _modelo(doc) is not None:
        return
    raise NoSoportado(
        f"`{comando}` no puede crear la base de una chapa: Solid Edge haría una operación de pieza "
        "que no se puede desarrollar.",
        details={"tipo": tipo, "modelo_base": False, "hint": PISTA_TAB},
    )


DIRECCIONES_DE_TAB = ("normal", "reverse")


def planificar_tab(perfil: str | None, direccion: str, sync: bool = False) -> dict[str, Any]:
    direccion = validar_direccion(direccion)
    if direccion not in DIRECCIONES_DE_TAB:
        raise ArgumentoInvalido(
            f"Un Tab no admite --direction {direccion}: usá normal o reverse.",
            details={"validas": list(DIRECCIONES_DE_TAB)},
        )
    plan: dict[str, Any] = {
        "accion": "sheetmetal.tab",
        "perfil": validar_perfil(perfil),
        "direccion": direccion,
    }
    if sync:
        plan["sync"] = True
    return plan


def _poner_modo(doc: Any, modo: int) -> None:
    leer(lambda: setattr(doc, "ModelingMode", modo))


def crear_tab(doc: Any, perfil: str | None, direccion: str, sync: bool = False) -> dict[str, Any]:
    """Base de una chapa: `Models.AddBaseTab(perfil, lado)` con el espesor del material.

    Verificado en vivo (2026-11-25), rectángulo de 100 x 50 mm en `top` hecho con `se sketch rect`:
    `igRight` (`normal`) da el Tab de z = 0 a +1 mm y `igLeft` (`reverse`), de -1 mm a 0; volumen
    5e-6 m3 con el espesor por defecto (1 mm). Solo crea la base: con un modelo ya hecho, exit 2.

    Con `sync`, pone `ModelingMode = seModelingModeSynchronous` antes de crear el Tab: es la única
    base sobre la que `Flanges.AddSync` resuelve (`se sheetmetal flange`); cambiar el modo después
    de un Tab ordenado da E_FAIL. Si el Tab falla, se restituye el modo previo.
    """
    datos = planificar_tab(perfil, direccion, sync)
    exigir_tipo(doc, ("sheetmetal",), "sheetmetal tab")
    exigir_modelable(doc, "sheetmetal tab", admite_sincronico=sync)
    if _modelo(doc) is not None:
        raise ArgumentoInvalido(
            "La chapa ya tiene un modelo base: `se sheetmetal tab` solo crea la base. Para "
            "agregar material usá `se extrude`.",
            details={"modelo_base": True},
        )
    indice, objeto = resolver_perfil(doc, datos["perfil"])
    modelos = leer(lambda: doc.Models)
    modo_previo = opcional(lambda: int(doc.ModelingMode))
    if sync:
        _poner_modo(doc, constante("seModelingModeSynchronous"))
    try:
        leer(lambda: modelos.AddBaseTab(objeto, _lado(datos["direccion"])))
    except Exception:
        if sync and modo_previo is not None:
            with contextlib.suppress(Exception):
                _poner_modo(doc, modo_previo)
        raise
    modelo = _modelo(doc)
    if modelo is None:
        raise ErrorCom("Solid Edge no creó el Tab (el documento sigue sin modelo).")
    tabs = opcional(lambda: modelo.Tabs)
    resultado: dict[str, Any] = {
        "operacion": "tab",
        "nombre": None if tabs is None else _ultimo_nombre(tabs),
        "direccion": datos["direccion"],
        "perfil": indice,
        "modelo_base": True,
        "volumen_si": _volumen(doc),
    }
    if sync:
        resultado["modo"] = "sincronico"
    return resultado


# --- Revolución -------------------------------------------------------------------------------


def planificar_revolucion(angulo: str, perfil: str | None, eje: str) -> dict[str, Any]:
    return {
        "accion": "revolve",
        "angulo_si": parsear_angulo(angulo),
        "perfil": validar_perfil(perfil),
        "eje": validar_eje(eje),
    }


def _poner_eje(perfil: Any, eje: str) -> Any:
    """Agregá al perfil la línea de construcción del eje y devolvé su `RefAxis`."""
    lineas = leer(lambda: perfil.Lines2d)
    largo = LARGO_DE_EJE
    extremos = (-largo, 0.0, largo, 0.0) if eje == "x" else (0.0, -largo, 0.0, largo)
    linea = leer(lambda: lineas.AddBy2Points(*extremos))
    leer(lambda: perfil.ToggleConstruction(linea))
    return leer(lambda: perfil.SetAxisOfRevolution(linea))


def revolucionar(doc: Any, angulo: str, perfil: str | None, eje: str) -> dict[str, Any]:
    """Revolución de un perfil alrededor de uno de sus ejes (`x`: y=0, `y`: x=0)."""
    datos = planificar_revolucion(angulo, perfil, eje)
    tipo = exigir_modelable(doc, "revolve")
    _exigir_base_de_chapa(doc, tipo, "revolve")
    radianes = datos["angulo_si"]
    indice, objeto = resolver_perfil(doc, datos["perfil"])
    modelo = _modelo(doc)
    eje_ref = _poner_eje(objeto, datos["eje"])
    lado = constante("igRight")
    if modelo is None:
        modelos = leer(lambda: doc.Models)
        leer(lambda: modelos.AddFiniteRevolvedProtrusion(1, (objeto,), eje_ref, lado, radianes))
        modelo = _modelo(doc)
        base = True
    else:
        revoluciones = leer(lambda: modelo.RevolvedProtrusions)
        leer(lambda: revoluciones.AddFiniteMulti(1, (objeto,), eje_ref, lado, radianes))
        base = False
    revoluciones = leer(lambda: modelo.RevolvedProtrusions)
    return {
        "operacion": "revolucion",
        "nombre": _ultimo_nombre(revoluciones),
        "angulo_si": radianes,
        "eje": datos["eje"],
        "perfil": indice,
        "modelo_base": base,
        "volumen_si": _volumen(doc),
    }


# --- Agujero ----------------------------------------------------------------------------------


def planificar_agujero(
    en: str,
    diametro: str,
    profundidad: str | None,
    pasante: bool,
    plano: str,
    direccion: str,
) -> dict[str, Any]:
    if pasante == (profundidad is not None):
        raise ArgumentoInvalido("Pasá --depth o --through (uno solo).")
    direccion = validar_direccion(direccion)
    if pasante and direccion == "symmetric":
        raise ArgumentoInvalido(
            "Un agujero pasante no admite --direction symmetric (Solid Edge no corta nada): "
            "usá normal o reverse, o --depth con symmetric."
        )
    x, y = parsear_punto(en)
    return {
        "accion": "hole",
        "x_si": x,
        "y_si": y,
        "diametro_si": parsear_longitud(diametro, "--diameter"),
        "profundidad_si": None if profundidad is None else parsear_longitud(profundidad, "--depth"),
        "pasante": pasante,
        "plano": plano,
        "plano_indice": validar_plano(plano),
        "direccion": direccion,
    }


def agujerear(
    doc: Any,
    en: str,
    diametro: str,
    profundidad: str | None,
    pasante: bool,
    plano: str,
    direccion: str,
) -> dict[str, Any]:
    """Agujero simple: un círculo en el plano y un corte (finito o pasante) sobre el modelo."""
    datos = planificar_agujero(en, diametro, profundidad, pasante, plano, direccion)
    exigir_modelable(doc, "hole")
    modelo = _modelo(doc)
    if modelo is None:
        raise ArgumentoInvalido(
            "No hay un modelo base para agujerear: hacé primero una extrusión (`se extrude`)."
        )
    lado = _lado(datos["direccion"])
    indice, perfil = _nuevo_perfil(doc, datos["plano_indice"])
    circulos = leer(lambda: perfil.Circles2d)
    leer(lambda: circulos.AddByCenterRadius(datos["x_si"], datos["y_si"], datos["diametro_si"] / 2))
    _cerrar_perfil(perfil)
    antes = _volumen(doc)
    cortes = leer(lambda: modelo.ExtrudedCutouts)
    if pasante:
        leer(lambda: cortes.AddThroughAllMulti(1, (perfil,), lado))
    else:
        profundidad_si = datos["profundidad_si"]
        leer(lambda: cortes.AddFiniteMulti(1, (perfil,), lado, profundidad_si))
    quitado = _exigir_efecto(
        cortes,
        antes,
        _volumen(doc),
        "El agujero",
        "Probá con --direction reverse o revisá que el plano y la posición toquen el modelo.",
    )
    return {
        "operacion": "agujero",
        "nombre": _ultimo_nombre(cortes),
        "diametro_si": datos["diametro_si"],
        "profundidad_si": datos["profundidad_si"],
        "pasante": pasante,
        "plano": _nombre_de_plano(datos["plano_indice"]),
        "plano_indice": datos["plano_indice"],
        "x_si": datos["x_si"],
        "y_si": datos["y_si"],
        "direccion": datos["direccion"],
        "perfil": indice,
        "volumen_si": _volumen(doc),
        "volumen_quitado_si": quitado,
    }


__all__ = [
    "DIRECCIONES",
    "PLANOS",
    "agujerear",
    "crear_circulo",
    "crear_perfil",
    "crear_rect",
    "crear_tab",
    "exigir_modelable",
    "extruir",
    "parsear_angulo",
    "parsear_longitud",
    "parsear_punto",
    "planificar_agujero",
    "planificar_circulo",
    "planificar_extrusion",
    "planificar_perfil",
    "planificar_rect",
    "planificar_revolucion",
    "planificar_tab",
    "resolver_perfil",
    "revolucionar",
    "validar_perfil",
]
