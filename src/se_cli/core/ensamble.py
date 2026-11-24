"""Estructura de un ensamble: árbol de ocurrencias y lista de materiales, y armado de ocurrencias.

`doc.Occurrences` trae las ocurrencias de primer nivel; cada una expone `Name`,
`OccurrenceFileName`, `Visible` y `Subassembly`, y un subensamble trae sus hijos en
`SubOccurrences` (si no, se prueba `OccurrenceDocument.Occurrences`). `Occurrence` no tiene un
miembro de supresión (verificado contra assembly.tlb), así que el nodo no informa `suprimido`.

Armado (`asm add|ground|move|remove`), verificado en vivo contra Solid Edge 2026 CE (226.00.01.04):

- `doc.Occurrences.AddByFilename(ruta)` pone la pieza en el origen y `AddWithTransform(ruta, x, y,
  z, rx, ry, rz)` en una posición con ángulos de Euler en radianes; los dos devuelven la ocurrencia.
- `Occurrence.GetTransform()` devuelve `(x, y, z, rx, ry, rz)` en metros y radianes, y
  `PutTransform(x, y, z, rx, ry, rz)` fija esa misma terna absoluta (ida y vuelta exacta).
  `Occurrence.Move(dx, dy, dz)` suma un desplazamiento a la posición, sin tocar los ángulos.
- Toda ocurrencia nace fija: `Relations3d` trae una relación `igGroundRelation3d` (1959028688) por
  ocurrencia, con `Relation.Occurrence` apuntando a ella. `Relations3d.AddGround(occ)` sobre una ya
  fija no duplica nada (cambia el orden de las relaciones), así que se mira antes. Soltar una
  ocurrencia es borrar su relación (`Relation.Delete()`). `Move` y `PutTransform` mueven también
  una ocurrencia fija. El MCP documenta mal el tipo de la relación ("Type = 0").
- `Occurrence.Delete()` saca la ocurrencia del ensamble y no toca el archivo de la pieza.
"""

from __future__ import annotations

import math
import os
from typing import Any

from se_cli.core import unidades
from se_cli.core.acceso import exigir_tipo, items, leer, opcional
from se_cli.core.documentos import validar_ruta_existente
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado, ErrorCom

PROFUNDIDAD_POR_DEFECTO = 10


def validar_profundidad(profundidad: int) -> int:
    """La profundidad (niveles a mostrar) es un entero >= 1; si no, exit 2."""
    if profundidad < 1:
        raise ArgumentoInvalido(f"--depth tiene que ser 1 o más: {profundidad}.")
    return profundidad


def _coleccion_de_hijos(ocurrencia: Any) -> Any:
    """Hijos de un subensamble: `SubOccurrences` o, si no está, `OccurrenceDocument.Occurrences`."""
    coleccion = opcional(lambda: ocurrencia.SubOccurrences)
    if coleccion is not None:
        return coleccion
    return opcional(lambda: ocurrencia.OccurrenceDocument.Occurrences)


def _archivo_de(ocurrencia: Any) -> str:
    """Archivo de una ocurrencia. Las de segundo nivel en adelante son `SubOccurrence`, que no
    tiene `OccurrenceFileName` sino `SubOccurrenceFileName` (verificado en vivo, 2026-11-24)."""
    for atributo in ("OccurrenceFileName", "SubOccurrenceFileName"):
        archivo = opcional(lambda a=atributo: getattr(ocurrencia, a))
        if archivo:
            return str(archivo)
    return ""


def _booleano(valor: Any) -> bool | None:
    return None if valor is None else bool(valor)


def _nivel(
    coleccion: Any, ancestros: tuple[str, ...], nivel: int, maximo: int
) -> list[dict[str, Any]]:
    """Nodos de un nivel. Las ocurrencias hermanas del mismo archivo se agrupan en `cantidad`."""
    grupos: dict[tuple[str, bool | None, bool], dict[str, Any]] = {}
    for posicion, ocurrencia in enumerate(items(coleccion), start=1):
        archivo = _archivo_de(ocurrencia)
        visible = _booleano(opcional(lambda o=ocurrencia: o.Visible))
        es_sub = bool(opcional(lambda o=ocurrencia: o.Subassembly))
        clave = (os.path.normcase(archivo), visible, es_sub)
        if clave in grupos:
            grupos[clave]["cantidad"] += 1
            if nivel == 1:
                grupos[clave].setdefault("indices", [grupos[clave]["indice"]]).append(posicion)
            continue
        nodo: dict[str, Any] = {
            "nombre": str(opcional(lambda o=ocurrencia: o.Name) or ""),
            "archivo": archivo,
            "cantidad": 1,
            "visible": visible,
            "ensamble": es_sub,
            "hijos": [],
        }
        if nivel == 1:
            # Posición en `doc.Occurrences`: sirve de `<occ>` en `asm ground|move|remove`.
            nodo["indice"] = posicion
        if es_sub:
            hijos = _coleccion_de_hijos(ocurrencia)
            if os.path.normcase(archivo) in ancestros:
                nodo["ciclo"] = True
            elif hijos is not None and nivel >= maximo:
                nodo["truncado"] = True
            elif hijos is not None:
                nodo["hijos"] = _nivel(
                    hijos, (*ancestros, os.path.normcase(archivo)), nivel + 1, maximo
                )
        grupos[clave] = nodo
    return list(grupos.values())


def _lista_de_materiales(nodos: list[dict[str, Any]], multiplicador: int = 1) -> dict[str, Any]:
    """Cantidades por archivo, multiplicando por las de los subensambles que lo contienen."""
    acumulado: dict[str, dict[str, Any]] = {}

    def recorrer(lista: list[dict[str, Any]], factor: int) -> None:
        for nodo in lista:
            total = nodo["cantidad"] * factor
            clave = os.path.normcase(nodo["archivo"])
            fila = acumulado.setdefault(
                clave,
                {"archivo": nodo["archivo"], "cantidad": 0, "ensamble": nodo["ensamble"]},
            )
            fila["cantidad"] += total
            recorrer(nodo["hijos"], total)

    recorrer(nodos, multiplicador)
    return acumulado


def arbol(
    doc: Any, profundidad: int = PROFUNDIDAD_POR_DEFECTO, plano: bool = False
) -> dict[str, Any]:
    """Árbol de ocurrencias, o con `plano` la lista de materiales agregada por archivo.

    Solo ensambles (exit 2 si no). Los ciclos se cortan (`ciclo: true`) y lo que pasa de
    `profundidad` niveles no se expande (`truncado: true`).
    """
    exigir_tipo(doc, ("assembly",), "asm tree")
    validar_profundidad(profundidad)
    nombre = str(leer(lambda: doc.Name))
    raiz = os.path.normcase(str(opcional(lambda: doc.FullName) or nombre))
    nodos = _nivel(leer(lambda: doc.Occurrences), (raiz,), 1, profundidad)
    if plano:
        materiales = list(_lista_de_materiales(nodos).values())
        return {"documento": nombre, "cantidad": len(materiales), "materiales": materiales}
    return {"documento": nombre, "profundidad": profundidad, "arbol": nodos}


# --- Armado: add, ground, move, remove --------------------------------------------------------

EXTENSIONES_INSERTABLES = (".par", ".psm", ".asm", ".pwd")
_RELACION_FIJA = 1959028688  # igGroundRelation3d


def parsear_terna(
    texto: str | None, opcion: str, dimension: str
) -> tuple[float, float, float] | None:
    """`x,y,z` en SI (metros o radianes). Sin unidad vale SI, como en el resto de la CLI.

    `dimension` es `unidades.LONGITUD` o `unidades.ANGULO`. None si no se pasó la opción.
    """
    if texto is None:
        return None
    es_longitud = dimension == unidades.LONGITUD
    partes = texto.split(",")
    if len(partes) != 3 or not all(p.strip() for p in partes):
        ejemplo = "10mm,0,5mm" if es_longitud else "0,0,90deg"
        raise ArgumentoInvalido(f"{opcion} tiene que ser X,Y,Z (ej. {ejemplo}): {texto!r}.")
    valores = []
    for parte in partes:
        cantidad = unidades.parsear_valor(parte)
        if cantidad.dimension not in (None, dimension):
            esperado = "una longitud (ej. 10mm)" if es_longitud else "un ángulo (ej. 90deg)"
            raise ArgumentoInvalido(f"{opcion} tiene que ser {esperado}: {parte.strip()!r}.")
        if not math.isfinite(cantidad.valor_si):
            raise ArgumentoInvalido(f"{opcion} no es un número finito: {parte.strip()!r}.")
        valores.append(cantidad.valor_si)
    return valores[0], valores[1], valores[2]


def _terna(valores: tuple[float, float, float] | None) -> list[float]:
    return [0.0, 0.0, 0.0] if valores is None else list(valores)


def _selector(texto: str) -> str:
    selector = texto.strip()
    if not selector:
        raise ArgumentoInvalido("Falta la ocurrencia (índice o nombre).")
    return selector


def planificar_add(archivo: str, en: str | None, rot: str | None) -> dict[str, Any]:
    """Valida `asm add` sin COM: el archivo existe, es insertable y las ternas son válidas."""
    ruta = validar_ruta_existente(archivo, "El archivo a insertar")
    if os.path.splitext(ruta)[1].lower() not in EXTENSIONES_INSERTABLES:
        raise ArgumentoInvalido(
            f"No se puede insertar {os.path.basename(ruta)!r}: "
            f"solo {', '.join(EXTENSIONES_INSERTABLES)}.",
            details={"ruta": ruta},
        )
    return {
        "accion": "asm.add",
        "archivo": ruta,
        "posicion_si": _terna(parsear_terna(en, "--at", unidades.LONGITUD)),
        "rotacion_si": _terna(parsear_terna(rot, "--rot", unidades.ANGULO)),
    }


def planificar_ground(ocurrencia: str, soltar: bool) -> dict[str, Any]:
    return {"accion": "asm.ground", "ocurrencia": _selector(ocurrencia), "fija": not soltar}


def planificar_move(
    ocurrencia: str, en: str | None, por: str | None, rot: str | None
) -> dict[str, Any]:
    """Valida `asm move`: al menos una de `--at`, `--by`, `--rot`; `--at` y `--by` no se mezclan."""
    if en is None and por is None and rot is None:
        raise ArgumentoInvalido("`asm move` necesita --at, --by o --rot.")
    if en is not None and por is not None:
        raise ArgumentoInvalido("--at (posición absoluta) y --by (desplazamiento) no se combinan.")
    plan: dict[str, Any] = {"accion": "asm.move", "ocurrencia": _selector(ocurrencia)}
    for clave, texto, opcion, dimension in (
        ("posicion_si", en, "--at", unidades.LONGITUD),
        ("desplazamiento_si", por, "--by", unidades.LONGITUD),
        ("rotacion_si", rot, "--rot", unidades.ANGULO),
    ):
        terna = parsear_terna(texto, opcion, dimension)
        if terna is not None:
            plan[clave] = list(terna)
    return plan


def planificar_remove(ocurrencia: str) -> dict[str, Any]:
    return {"accion": "asm.remove", "ocurrencia": _selector(ocurrencia)}


def _buscar(doc: Any, selector: str) -> tuple[int, Any]:
    """Ocurrencia de primer nivel por índice (1-based, como `asm tree`) o nombre sin mayúsculas."""
    texto = _selector(selector)
    ocurrencias = list(items(leer(lambda: doc.Occurrences)))
    if texto.isdigit():
        indice = int(texto)
        if 1 <= indice <= len(ocurrencias):
            return indice, ocurrencias[indice - 1]
        raise DocNoEncontrado(
            f"No existe la ocurrencia con índice {indice}: el ensamble tiene {len(ocurrencias)}.",
            details={"indice": indice, "cantidad": len(ocurrencias)},
        )
    buscado = texto.casefold()
    for indice, ocurrencia in enumerate(ocurrencias, start=1):
        if str(opcional(lambda o=ocurrencia: o.Name) or "").casefold() == buscado:
            return indice, ocurrencia
    raise DocNoEncontrado(
        f"No existe la ocurrencia {selector!r} en el ensamble.", details={"nombre": selector}
    )


def _relaciones_fijas(doc: Any, nombre: str) -> list[Any] | None:
    """Relaciones `igGroundRelation3d` de la ocurrencia `nombre`; None si no se pueden leer."""
    relaciones = opcional(lambda: doc.Relations3d)
    if relaciones is None:
        return None
    fijas = []
    for relacion in items(relaciones):
        if opcional(lambda r=relacion: r.Type) != _RELACION_FIJA:
            continue
        destino = opcional(lambda r=relacion: r.Occurrence.Name)
        if destino is not None and str(destino).casefold() == nombre.casefold():
            fijas.append(relacion)
    return fijas


def _transformacion(ocurrencia: Any) -> tuple[float, ...]:
    """`(x, y, z, rx, ry, rz)` en SI según Solid Edge."""
    crudo = leer(lambda: ocurrencia.GetTransform())
    return tuple(float(v) for v in crudo)


def _limpio(valor: float, unidad: str) -> float:
    return round(unidades.de_si(valor, unidad), 12) + 0.0


def describir(
    doc: Any, indice: int, ocurrencia: Any, elegidas: dict[str, str] | None = None
) -> dict[str, Any]:
    """`{indice, nombre, archivo, visible, ensamble, fija, posicion, rotacion, unidades}`.

    Todo sale de Solid Edge en el momento de la llamada. Posición y rotación van en las unidades
    de `--units` (por defecto metros y radianes); `fija` es None si la API no deja saberlo.
    """
    elegidas = elegidas or {}
    largo = elegidas.get(unidades.LONGITUD, unidades.UNIDAD_SI[unidades.LONGITUD])
    angulo = elegidas.get(unidades.ANGULO, unidades.UNIDAD_SI[unidades.ANGULO])
    nombre = str(opcional(lambda: ocurrencia.Name) or "")
    pose = opcional(lambda: _transformacion(ocurrencia))
    visible = opcional(lambda: ocurrencia.Visible)
    fijas = _relaciones_fijas(doc, nombre)
    return {
        "indice": indice,
        "nombre": nombre,
        "archivo": str(opcional(lambda: ocurrencia.OccurrenceFileName) or ""),
        "visible": None if visible is None else bool(visible),
        "ensamble": bool(opcional(lambda: ocurrencia.Subassembly)),
        "fija": None if fijas is None else bool(fijas),
        "posicion": None if pose is None else [_limpio(v, largo) for v in pose[:3]],
        "rotacion": None if pose is None else [_limpio(v, angulo) for v in pose[3:6]],
        "unidades": {"longitud": largo, "angulo": angulo},
    }


def _indice_de(doc: Any, nombre: str, respaldo: int) -> int:
    for indice, ocurrencia in enumerate(items(leer(lambda: doc.Occurrences)), start=1):
        if str(opcional(lambda o=ocurrencia: o.Name) or "") == nombre:
            return indice
    return respaldo


def agregar(
    doc: Any,
    archivo: str,
    en: str | None,
    rot: str | None,
    elegidas: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Insertá una pieza, chapa o subensamble como ocurrencia (`asm add`).

    Sin `--at` ni `--rot` va al origen (`AddByFilename`); con alguno, `AddWithTransform`.
    """
    exigir_tipo(doc, ("assembly",), "asm add")
    plan = planificar_add(archivo, en, rot)
    ruta = plan["archivo"]
    propio = opcional(lambda: doc.FullName)
    if propio and os.path.normcase(os.path.abspath(str(propio))) == os.path.normcase(ruta):
        raise ArgumentoInvalido("No se puede insertar un ensamble dentro de sí mismo.")
    coleccion = leer(lambda: doc.Occurrences)
    antes = int(leer(lambda: coleccion.Count))
    if en is None and rot is None:
        ocurrencia = leer(lambda: coleccion.AddByFilename(ruta))
    else:
        x, y, z = plan["posicion_si"]
        rx, ry, rz = plan["rotacion_si"]
        ocurrencia = leer(lambda: coleccion.AddWithTransform(ruta, x, y, z, rx, ry, rz))
    despues = int(leer(lambda: coleccion.Count))
    if despues != antes + 1:
        raise ErrorCom(
            f"Solid Edge no agregó la ocurrencia de {os.path.basename(ruta)!r}.",
            details={"antes": antes, "despues": despues},
        )
    nombre = str(opcional(lambda: ocurrencia.Name) or "")
    return describir(doc, _indice_de(doc, nombre, despues), ocurrencia, elegidas)


def fijar(
    doc: Any, selector: str, soltar: bool = False, elegidas: dict[str, str] | None = None
) -> dict[str, Any]:
    """Fijá una ocurrencia (relación ground) o, con `soltar`, quitale esa relación.

    Idempotente: si ya está en el estado pedido no se escribe nada y `changed` es `false`.
    """
    exigir_tipo(doc, ("assembly",), "asm ground")
    indice, ocurrencia = _buscar(doc, selector)
    nombre = str(opcional(lambda: ocurrencia.Name) or "")
    relaciones = leer(lambda: doc.Relations3d)
    fijas = _relaciones_fijas(doc, nombre) or []
    changed = False
    if soltar and fijas:
        for relacion in fijas:
            leer(lambda r=relacion: r.Delete())
        changed = True
    elif not soltar and not fijas:
        leer(lambda: relaciones.AddGround(ocurrencia))
        changed = True
    resultado = describir(doc, indice, ocurrencia, elegidas)
    if resultado["fija"] is not (not soltar):
        raise ErrorCom(
            f"Solid Edge no dejó {nombre!r} {'suelta' if soltar else 'fija'}.", details=resultado
        )
    return {**resultado, "changed": changed}


def mover(
    doc: Any,
    selector: str,
    en: str | None,
    por: str | None,
    rot: str | None,
    elegidas: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Reubicá una ocurrencia: `--at` absoluto, `--by` relativo, `--rot` absoluto (`asm move`).

    Solo `--by`: `Occurrence.Move`. Si no, `PutTransform` con la posición (`--at`, o la actual
    más `--by`) y los ángulos (`--rot`, o los actuales). Un resultado que no coincide con lo
    pedido da exit 4.
    """
    exigir_tipo(doc, ("assembly",), "asm move")
    plan = planificar_move(selector, en, por, rot)
    indice, ocurrencia = _buscar(doc, selector)
    actual = _transformacion(ocurrencia)
    if "posicion_si" in plan:
        posicion = tuple(plan["posicion_si"])
    elif "desplazamiento_si" in plan:
        posicion = tuple(p + d for p, d in zip(actual[:3], plan["desplazamiento_si"], strict=True))
    else:
        posicion = actual[:3]
    angulos = tuple(plan["rotacion_si"]) if "rotacion_si" in plan else actual[3:6]
    if "rotacion_si" not in plan and "posicion_si" not in plan:
        dx, dy, dz = plan["desplazamiento_si"]
        leer(lambda: ocurrencia.Move(dx, dy, dz))
    else:
        x, y, z = posicion
        rx, ry, rz = angulos
        leer(lambda: ocurrencia.PutTransform(x, y, z, rx, ry, rz))
    final = _transformacion(ocurrencia)
    pedido = (*posicion, *angulos)
    if any(abs(a - b) > 1e-9 for a, b in zip(final, pedido, strict=True)):
        raise ErrorCom(
            "Solid Edge no dejó la ocurrencia donde se pidió.",
            details={"pedido": list(pedido), "actual": list(final)},
        )
    return describir(doc, indice, ocurrencia, elegidas)


def quitar(doc: Any, selector: str) -> dict[str, Any]:
    """Borrá una ocurrencia del ensamble (`asm remove`); el archivo de la pieza queda intacto."""
    exigir_tipo(doc, ("assembly",), "asm remove")
    indice, ocurrencia = _buscar(doc, selector)
    nombre = str(opcional(lambda: ocurrencia.Name) or "")
    archivo = str(opcional(lambda: ocurrencia.OccurrenceFileName) or "")
    coleccion = leer(lambda: doc.Occurrences)
    antes = int(leer(lambda: coleccion.Count))
    leer(lambda: ocurrencia.Delete())
    despues = int(leer(lambda: coleccion.Count))
    if despues != antes - 1:
        raise ErrorCom(
            f"Solid Edge no borró la ocurrencia {nombre!r}.",
            details={"antes": antes, "despues": despues},
        )
    return {
        "indice": indice,
        "nombre": nombre,
        "archivo": archivo,
        "removed": True,
        "restantes": despues,
    }


__all__ = [
    "EXTENSIONES_INSERTABLES",
    "PROFUNDIDAD_POR_DEFECTO",
    "agregar",
    "arbol",
    "describir",
    "fijar",
    "mover",
    "parsear_terna",
    "planificar_add",
    "planificar_ground",
    "planificar_move",
    "planificar_remove",
    "quitar",
    "validar_profundidad",
]
