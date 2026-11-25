"""Perfil de croquis declarativo (JSON, esquema v1): validación y geometría sin COM.

`se sketch profile` crea un croquis cerrado de líneas, arcos y círculos con restricciones. Este
módulo solo parsea y valida (exit 2, antes de tocar Solid Edge); crear el perfil es de
`core/modelado.py`. Todo sale en SI (metros).

Esquema v1 (campos desconocidos = exit 2):

- Raíz: `version` (1, obligatorio), `plane` (como `sketch rect`, por defecto `top`), `units`
  (unidad de longitud de los números sin unidad; obligatorio si hay alguno), `tolerance`
  (por defecto 1e-6 m), `auto_connect` (por defecto true), `close` (solo true),
  `entities` (obligatorio, con al menos una), `constraints` (opcional).
- Coordenadas: número (en `units`) o string con unidad (`"50mm"`).
- Entidades (todas con `id` único, sin puntos): `line` (`from`, `to`), `arc` (`center`, `start`,
  `end`, `dir` ccw|cw, por defecto ccw), `circle` (`center`, `radius`), `polyline` (`points`, al
  menos 2; azúcar: se expande a las líneas `p1.1`, `p1.2`...).
- Restricciones: `connect` (`a`, `b`: `<id>.<punto>`, con punto start|end|center),
  `horizontal` y `vertical` (`on`: una línea), `parallel` y `perpendicular` (`a`, `b`: líneas),
  `equal` (`a`, `b`: dos líneas, o arcos/círculos entre sí), `concentric` (`a`, `b`: arcos o
  círculos), `tangent` (`a`, `b`: línea con arco/círculo, o arco/círculo entre sí). Solo fijan
  intención: la geometría ya tiene que cumplirlas dentro de `tolerance`.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from se_cli.core import unidades
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado

VERSION = 1
MAX_BYTES_PERFIL = 8 * 1024 * 1024
TOLERANCIA_POR_DEFECTO = 1e-6  # metros

RAIZ_PERMITIDA = {
    "version",
    "plane",
    "units",
    "tolerance",
    "auto_connect",
    "close",
    "entities",
    "constraints",
}
CAMPOS_DE_ENTIDAD: dict[str, set[str]] = {
    "line": {"id", "type", "from", "to"},
    "arc": {"id", "type", "center", "start", "end", "dir"},
    "circle": {"id", "type", "center", "radius"},
    "polyline": {"id", "type", "points"},
}
CAMPOS_DE_RESTRICCION: dict[str, set[str]] = {
    "connect": {"type", "a", "b"},
    "horizontal": {"type", "on"},
    "vertical": {"type", "on"},
    "parallel": {"type", "a", "b"},
    "perpendicular": {"type", "a", "b"},
    "equal": {"type", "a", "b"},
    "concentric": {"type", "a", "b"},
    "tangent": {"type", "a", "b"},
}
FUERA_DE_V1 = {
    "dimension": "las cotas",
    "dim": "las cotas",
    "collinear": "`collinear`",
    "symmetric": "`symmetric`",
}
PUNTOS_DE = {"line": ("start", "end"), "arc": ("start", "end", "center"), "circle": ("center",)}

Punto = tuple[float, float]


@dataclass
class Perfil:
    """Perfil validado, en SI y con las polilíneas ya expandidas."""

    plano: str
    plano_indice: int | str
    tolerancia_si: float
    auto_connect: bool
    entidades: list[dict[str, Any]] = field(default_factory=list)
    restricciones: list[dict[str, Any]] = field(default_factory=list)

    def conteos(self) -> dict[str, int]:
        por_tipo = {"line": 0, "arc": 0, "circle": 0}
        for entidad in self.entidades:
            por_tipo[entidad["tipo"]] += 1
        return {
            "lineas": por_tipo["line"],
            "arcos": por_tipo["arc"],
            "circulos": por_tipo["circle"],
        }

    def por_tipo_de_restriccion(self) -> dict[str, int]:
        cuenta: dict[str, int] = {}
        for restriccion in self.restricciones:
            cuenta[restriccion["tipo"]] = cuenta.get(restriccion["tipo"], 0) + 1
        return cuenta

    def plan(self) -> dict[str, Any]:
        """Descripción en SI (entidades expandidas y restricciones): el `data` de `--dry-run`."""
        return {
            "accion": "sketch.profile",
            "plano": self.plano,
            "plano_indice": self.plano_indice,
            "tolerancia_si": self.tolerancia_si,
            "entidades": [_plano_de_entidad(e) for e in self.entidades],
            "restricciones": [_plano_de_restriccion(r) for r in self.restricciones],
            "conteos": {**self.conteos(), "restricciones": len(self.restricciones)},
        }


def _plano_de_entidad(entidad: dict[str, Any]) -> dict[str, Any]:
    salida = {k: list(v) if isinstance(v, tuple) else v for k, v in entidad.items()}
    if salida.get("origen") is None:
        salida.pop("origen", None)
    return salida


def _plano_de_restriccion(restriccion: dict[str, Any]) -> dict[str, Any]:
    salida: dict[str, Any] = {"tipo": restriccion["tipo"]}
    if restriccion["tipo"] == "connect":
        salida["a"] = ".".join(restriccion["a"])
        salida["b"] = ".".join(restriccion["b"])
        salida["origen"] = "auto" if restriccion["auto"] else "explicita"
    else:
        salida["entidades"] = list(restriccion["entidades"])
    return salida


# --- Lectura de la fuente ---------------------------------------------------------------------


def leer_fuente(fuente: str) -> str:
    """Texto del JSON: archivo, o la entrada estándar con `-`. Archivo inexistente = exit 5."""
    if fuente == "-":
        data = sys.stdin.buffer.read(MAX_BYTES_PERFIL + 1)
    else:
        ruta = Path(fuente)
        if not ruta.exists():
            raise DocNoEncontrado(f"No existe el archivo de perfil: {fuente}.")
        if not ruta.is_file():
            raise ArgumentoInvalido(f"{fuente} no es un archivo.")
        with ruta.open("rb") as archivo:
            data = archivo.read(MAX_BYTES_PERFIL + 1)
    if len(data) > MAX_BYTES_PERFIL:
        raise ArgumentoInvalido("El perfil supera el límite de 8 MiB.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ArgumentoInvalido(f"El perfil no es UTF-8 válido: {error}.") from None


def _sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ArgumentoInvalido(f"JSON inválido: la clave {clave!r} está repetida.")
        resultado[clave] = valor
    return resultado


def parsear_json(texto: str) -> dict[str, Any]:
    try:
        datos = json.loads(texto, object_pairs_hook=_sin_duplicados)
    except json.JSONDecodeError as error:
        raise ArgumentoInvalido(
            f"JSON inválido (línea {error.lineno}, columna {error.colno}): {error.msg}."
        ) from None
    except RecursionError:
        raise ArgumentoInvalido("JSON inválido: demasiado anidado.") from None
    except ValueError:
        raise ArgumentoInvalido("JSON inválido: número fuera de rango.") from None
    if not isinstance(datos, dict):
        raise ArgumentoInvalido("El perfil tiene que ser un objeto JSON.")
    return datos


# --- Validación del esquema -------------------------------------------------------------------


def _extra(objeto: dict[str, Any], permitidos: set[str], donde: str) -> None:
    sobran = sorted(set(objeto) - permitidos)
    if sobran:
        raise ArgumentoInvalido(
            f"{donde}: campos desconocidos {', '.join(sobran)}. Permitidos: "
            f"{', '.join(sorted(permitidos))}.",
            details={"desconocidos": sobran},
        )


def _falta(objeto: dict[str, Any], campos: tuple[str, ...], donde: str) -> None:
    faltan = [c for c in campos if c not in objeto]
    if faltan:
        raise ArgumentoInvalido(f"{donde}: faltan los campos {', '.join(faltan)}.")


class _Longitudes:
    """Convierte coordenadas y largos a SI según `units` de la raíz."""

    def __init__(self, unidad: str | None) -> None:
        self.unidad = unidad

    def valor(self, dato: Any, donde: str, *, positivo: bool = False) -> float:
        if isinstance(dato, bool) or not isinstance(dato, (int, float, str)):
            raise ArgumentoInvalido(f"{donde}: tiene que ser un número o un string con unidad.")
        if isinstance(dato, str):
            cantidad = unidades.parsear_valor(dato) if dato.strip() else None
            if cantidad is None or cantidad.unidad is None:
                raise ArgumentoInvalido(
                    f'{donde}: el string {dato!r} necesita una unidad (ej. "50mm"); '
                    "un número sin unidad va como número JSON."
                )
            if cantidad.dimension != unidades.LONGITUD:
                raise ArgumentoInvalido(f"{donde}: {dato!r} no es una longitud.")
            si = cantidad.valor_si
        else:
            if self.unidad is None:
                raise ArgumentoInvalido(
                    f'{donde}: hay números sin unidad y falta `units` (ej. "units": "mm").'
                )
            try:
                si = float(dato) * unidades.FACTORES[unidades.LONGITUD][self.unidad]
            except OverflowError:
                raise ArgumentoInvalido(f"{donde}: número fuera de rango.") from None
        if not math.isfinite(si):
            raise ArgumentoInvalido(f"{donde}: no es un número finito.")
        if positivo and si <= 0:
            raise ArgumentoInvalido(f"{donde}: tiene que ser mayor que 0.")
        return si

    def punto(self, dato: Any, donde: str) -> Punto:
        if not isinstance(dato, list) or len(dato) != 2:
            raise ArgumentoInvalido(f"{donde}: tiene que ser un punto [x, y].")
        return (
            self.valor(dato[0], f"{donde}[0]"),
            self.valor(dato[1], f"{donde}[1]"),
        )


def _unidad_de_raiz(datos: dict[str, Any]) -> str | None:
    if "units" not in datos:
        return None
    unidad = datos["units"]
    if not isinstance(unidad, str) or unidad.strip() not in unidades.FACTORES[unidades.LONGITUD]:
        raise ArgumentoInvalido(
            f"`units` inválido: {unidad!r}. Usá una longitud: "
            f"{', '.join(unidades.FACTORES[unidades.LONGITUD])}.",
            details={"validas": list(unidades.FACTORES[unidades.LONGITUD])},
        )
    return unidad.strip()


def _booleano(datos: dict[str, Any], clave: str, por_defecto: bool) -> bool:
    valor = datos.get(clave, por_defecto)
    if not isinstance(valor, bool):
        raise ArgumentoInvalido(f"`{clave}` tiene que ser true o false.")
    return valor


def _id(dato: Any, donde: str, vistos: set[str]) -> str:
    if not isinstance(dato, str) or not dato.strip():
        raise ArgumentoInvalido(f"{donde}: `id` tiene que ser un string no vacío.")
    if "." in dato or dato != dato.strip():
        raise ArgumentoInvalido(
            f"{donde}: el id {dato!r} no puede tener puntos ni espacios en los bordes "
            "(el punto separa id y punto de la entidad)."
        )
    if dato in vistos:
        raise ArgumentoInvalido(f"{donde}: el id {dato!r} está repetido.", details={"id": dato})
    vistos.add(dato)
    return dato


def _entidades(datos: dict[str, Any], largos: _Longitudes, tol: float) -> list[dict[str, Any]]:
    crudas = datos.get("entities")
    if not isinstance(crudas, list) or not crudas:
        raise ArgumentoInvalido("`entities` tiene que ser una lista con al menos una entidad.")
    vistos: set[str] = set()
    entidades: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas):
        donde = f"entities[{i}]"
        if not isinstance(cruda, dict):
            raise ArgumentoInvalido(f"{donde}: tiene que ser un objeto.")
        tipo = cruda.get("type")
        if tipo not in CAMPOS_DE_ENTIDAD:
            raise ArgumentoInvalido(
                f"{donde}: tipo desconocido {tipo!r}. Usá line, arc, circle o polyline.",
                details={"validos": list(CAMPOS_DE_ENTIDAD)},
            )
        _extra(cruda, CAMPOS_DE_ENTIDAD[tipo], donde)
        _falta(cruda, ("id",), donde)
        ident = _id(cruda["id"], donde, vistos)
        donde = f"{donde} ({ident})"
        if tipo == "line":
            _falta(cruda, ("from", "to"), donde)
            desde = largos.punto(cruda["from"], f"{donde}.from")
            hasta = largos.punto(cruda["to"], f"{donde}.to")
            entidades.append(_linea(ident, desde, hasta, tol, None))
        elif tipo == "arc":
            entidades.append(_arco(ident, cruda, largos, tol, donde))
        elif tipo == "circle":
            _falta(cruda, ("center", "radius"), donde)
            entidades.append(
                {
                    "id": ident,
                    "tipo": "circle",
                    "centro": largos.punto(cruda["center"], f"{donde}.center"),
                    "radio": largos.valor(cruda["radius"], f"{donde}.radius", positivo=True),
                }
            )
        else:
            entidades.extend(_polilinea(ident, cruda, largos, tol, donde))
    return entidades


def _linea(
    ident: str, desde: Punto, hasta: Punto, tol: float, origen: str | None
) -> dict[str, Any]:
    if math.dist(desde, hasta) <= tol:
        raise ArgumentoInvalido(f"La línea {ident!r} tiene largo cero (dentro de la tolerancia).")
    return {"id": ident, "tipo": "line", "desde": desde, "hasta": hasta, "origen": origen}


def _arco(
    ident: str, cruda: dict[str, Any], largos: _Longitudes, tol: float, donde: str
) -> dict[str, Any]:
    _falta(cruda, ("center", "start", "end"), donde)
    direccion = cruda.get("dir", "ccw")
    if direccion not in ("ccw", "cw"):
        raise ArgumentoInvalido(f"{donde}.dir: usá ccw o cw, no {direccion!r}.")
    centro = largos.punto(cruda["center"], f"{donde}.center")
    inicio = largos.punto(cruda["start"], f"{donde}.start")
    fin = largos.punto(cruda["end"], f"{donde}.end")
    r_inicio, r_fin = math.dist(centro, inicio), math.dist(centro, fin)
    if r_inicio <= tol:
        raise ArgumentoInvalido(f"El arco {ident!r} tiene radio cero (start coincide con center).")
    if abs(r_inicio - r_fin) > tol:
        raise ArgumentoInvalido(
            f"El arco {ident!r} tiene radios distintos: start a {r_inicio:.9g} m y end a "
            f"{r_fin:.9g} m del centro (tolerancia {tol:g} m).",
            details={"radio_start_si": r_inicio, "radio_end_si": r_fin},
        )
    if math.dist(inicio, fin) <= tol:
        raise ArgumentoInvalido(
            f"El arco {ident!r} empieza y termina en el mismo punto: para una vuelta completa "
            "usá `circle`."
        )
    return {
        "id": ident,
        "tipo": "arc",
        "centro": centro,
        "inicio": inicio,
        "fin": fin,
        "radio": r_inicio,
        "dir": direccion,
    }


def _polilinea(
    ident: str, cruda: dict[str, Any], largos: _Longitudes, tol: float, donde: str
) -> list[dict[str, Any]]:
    _falta(cruda, ("points",), donde)
    puntos = cruda["points"]
    if not isinstance(puntos, list) or len(puntos) < 2:
        raise ArgumentoInvalido(f"{donde}.points: tiene que ser una lista de al menos 2 puntos.")
    vertices = [largos.punto(p, f"{donde}.points[{k}]") for k, p in enumerate(puntos)]
    return [
        _linea(f"{ident}.{k}", a, b, tol, ident)
        for k, (a, b) in enumerate(zip(vertices, vertices[1:], strict=False), start=1)
    ]


# --- Restricciones ----------------------------------------------------------------------------


def _referencia(texto: Any, entidades: dict[str, dict[str, Any]], donde: str) -> str:
    """Id de una entidad existente (un segmento de polilínea se nombra `p1.2`)."""
    if not isinstance(texto, str) or texto not in entidades:
        pista = ""
        if isinstance(texto, str) and any(e.get("origen") == texto for e in entidades.values()):
            pista = f" {texto!r} es una polilínea: nombrá un segmento ({texto}.1, {texto}.2...)."
        raise ArgumentoInvalido(
            f"{donde}: no existe la entidad {texto!r}.{pista}",
            details={"referencia": texto if isinstance(texto, str) else None},
        )
    return texto


def _punto_de(texto: Any, entidades: dict[str, dict[str, Any]], donde: str) -> tuple[str, str]:
    if not isinstance(texto, str) or "." not in texto:
        raise ArgumentoInvalido(
            f"{donde}: tiene que ser `<id>.<punto>` (start, end o center), no {texto!r}."
        )
    ident, _, punto = texto.rpartition(".")
    ident = _referencia(ident, entidades, donde)
    tipo = entidades[ident]["tipo"]
    if punto not in PUNTOS_DE[tipo]:
        raise ArgumentoInvalido(
            f"{donde}: {texto!r} no existe; un {tipo} tiene {', '.join(PUNTOS_DE[tipo])}.",
            details={"validos": list(PUNTOS_DE[tipo])},
        )
    return ident, punto


TIPOS_VALIDOS = {
    "horizontal": ({"line"},),
    "vertical": ({"line"},),
    "parallel": ({"line"}, {"line"}),
    "perpendicular": ({"line"}, {"line"}),
    "concentric": ({"arc", "circle"}, {"arc", "circle"}),
}


def _restricciones(
    datos: dict[str, Any], entidades: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    crudas = datos.get("constraints", [])
    if not isinstance(crudas, list):
        raise ArgumentoInvalido("`constraints` tiene que ser una lista.")
    resultado: list[dict[str, Any]] = []
    for i, cruda in enumerate(crudas):
        donde = f"constraints[{i}]"
        if not isinstance(cruda, dict):
            raise ArgumentoInvalido(f"{donde}: tiene que ser un objeto.")
        tipo = cruda.get("type")
        if isinstance(tipo, str) and tipo in FUERA_DE_V1:
            raise ArgumentoInvalido(
                f"{donde}: {FUERA_DE_V1[tipo]} no están en el esquema v1.",
                details={"fuera_de_v1": tipo},
            )
        if tipo not in CAMPOS_DE_RESTRICCION:
            raise ArgumentoInvalido(
                f"{donde}: tipo desconocido {tipo!r}. Usá {', '.join(CAMPOS_DE_RESTRICCION)}.",
                details={"validos": list(CAMPOS_DE_RESTRICCION)},
            )
        _extra(cruda, CAMPOS_DE_RESTRICCION[tipo], donde)
        if tipo == "connect":
            _falta(cruda, ("a", "b"), donde)
            a = _punto_de(cruda["a"], entidades, f"{donde}.a")
            b = _punto_de(cruda["b"], entidades, f"{donde}.b")
            if a == b:
                raise ArgumentoInvalido(f"{donde}: conecta un punto consigo mismo.")
            resultado.append({"tipo": "connect", "a": a, "b": b, "auto": False})
            continue
        campos = ("on",) if tipo in ("horizontal", "vertical") else ("a", "b")
        _falta(cruda, campos, donde)
        ids = [_referencia(cruda[c], entidades, f"{donde}.{c}") for c in campos]
        if len(ids) == 2 and ids[0] == ids[1]:
            raise ArgumentoInvalido(f"{donde}: las dos referencias son la misma entidad.")
        _tipos_compatibles(tipo, [entidades[x]["tipo"] for x in ids], ids, donde)
        resultado.append({"tipo": tipo, "entidades": ids})
    return resultado


def _tipos_compatibles(tipo: str, tipos: list[str], ids: list[str], donde: str) -> None:
    if tipo in TIPOS_VALIDOS:
        for real, permitidos, ident in zip(tipos, TIPOS_VALIDOS[tipo], ids, strict=True):
            if real not in permitidos:
                raise ArgumentoInvalido(
                    f"{donde}: `{tipo}` no se aplica a {ident!r} (es {real}); "
                    f"admite {' o '.join(sorted(permitidos))}."
                )
        return
    curvas = {"arc", "circle"}
    if tipo == "equal":
        valido = tipos == ["line", "line"] or set(tipos) <= curvas
    else:  # tangent
        valido = set(tipos) <= curvas or (set(tipos) & curvas and "line" in tipos)
    if not valido:
        raise ArgumentoInvalido(
            f"{donde}: `{tipo}` no admite {tipos[0]} con {tipos[1]} ({ids[0]!r}, {ids[1]!r})."
        )


# --- Geometría --------------------------------------------------------------------------------


def _punto(entidad: dict[str, Any], clave: str) -> Punto:
    return {
        "start": entidad.get("inicio", entidad.get("desde")),
        "end": entidad.get("fin", entidad.get("hasta")),
        "center": entidad.get("centro"),
    }[clave]


def _direccion(linea: dict[str, Any]) -> tuple[float, float, float]:
    dx = linea["hasta"][0] - linea["desde"][0]
    dy = linea["hasta"][1] - linea["desde"][1]
    return dx, dy, math.hypot(dx, dy)


def _incumple(restriccion: dict[str, Any], motivo: str) -> ArgumentoInvalido:
    texto = _plano_de_restriccion(restriccion)
    return ArgumentoInvalido(
        f"La restricción {texto['tipo']} {restriccion.get('entidades') or (texto['a'], texto['b'])}"
        f" no se cumple con las coordenadas: {motivo}. Las restricciones solo fijan intención; "
        "corregí las coordenadas.",
        details={"restriccion": texto},
    )


def _verificar(restriccion: dict[str, Any], ents: dict[str, dict[str, Any]], tol: float) -> None:
    tipo = restriccion["tipo"]
    if tipo == "connect":
        pa = _punto(ents[restriccion["a"][0]], restriccion["a"][1])
        pb = _punto(ents[restriccion["b"][0]], restriccion["b"][1])
        d = math.dist(pa, pb)
        if d > tol:
            raise _incumple(restriccion, f"los puntos están a {d:.9g} m")
        return
    objetos = [ents[x] for x in restriccion["entidades"]]
    if tipo in ("horizontal", "vertical"):
        dx, dy, _ = _direccion(objetos[0])
        desvio = abs(dy) if tipo == "horizontal" else abs(dx)
        if desvio > tol:
            raise _incumple(restriccion, f"la línea se desvía {desvio:.9g} m")
    elif tipo in ("parallel", "perpendicular"):
        (ax, ay, la), (bx, by, lb) = _direccion(objetos[0]), _direccion(objetos[1])
        medida = abs(ax * by - ay * bx) if tipo == "parallel" else abs(ax * bx + ay * by)
        desvio = medida / max(la, lb)  # desvío (m) en el extremo de la línea más corta
        if desvio > tol:
            raise _incumple(restriccion, f"el desvío angular equivale a {desvio:.9g} m")
    elif tipo == "equal":
        _verificar_igual(restriccion, objetos, tol)
    elif tipo == "concentric":
        d = math.dist(objetos[0]["centro"], objetos[1]["centro"])
        if d > tol:
            raise _incumple(restriccion, f"los centros están a {d:.9g} m")
    else:
        _verificar_tangente(restriccion, objetos, tol)


def _verificar_igual(restriccion: dict[str, Any], objetos: list[dict[str, Any]], tol: float):
    if objetos[0]["tipo"] == "line":
        medidas = [_direccion(o)[2] for o in objetos]
        que = "largos"
    else:
        medidas = [o["radio"] for o in objetos]
        que = "radios"
    if abs(medidas[0] - medidas[1]) > tol:
        raise _incumple(restriccion, f"los {que} son {medidas[0]:.9g} m y {medidas[1]:.9g} m")


def _verificar_tangente(restriccion: dict[str, Any], objetos: list[dict[str, Any]], tol: float):
    if "line" in (objetos[0]["tipo"], objetos[1]["tipo"]):
        linea = objetos[0] if objetos[0]["tipo"] == "line" else objetos[1]
        curva = objetos[1] if linea is objetos[0] else objetos[0]
        dx, dy, largo = _direccion(linea)
        cx, cy = curva["centro"]
        ox, oy = linea["desde"]
        distancia = abs(dx * (cy - oy) - dy * (cx - ox)) / largo
        if abs(distancia - curva["radio"]) > tol:
            raise _incumple(
                restriccion,
                f"el centro está a {distancia:.9g} m de la línea y el radio es "
                f"{curva['radio']:.9g} m",
            )
        t = ((cx - ox) * dx + (cy - oy) * dy) / largo  # pie de la perpendicular sobre la línea
        if t < -tol or t > largo + tol:
            raise _incumple(restriccion, "el punto de tangencia cae fuera del segmento")
        return
    r1, r2 = objetos[0]["radio"], objetos[1]["radio"]
    d = math.dist(objetos[0]["centro"], objetos[1]["centro"])
    if d <= tol or min(abs(d - (r1 + r2)), abs(d - abs(r1 - r2))) > tol:
        raise _incumple(
            restriccion,
            f"los centros están a {d:.9g} m y los radios son {r1:.9g} m y {r2:.9g} m",
        )


# --- Cierre del contorno ----------------------------------------------------------------------


def _extremos(entidades: list[dict[str, Any]]) -> list[tuple[str, str, Punto]]:
    salida: list[tuple[str, str, Punto]] = []
    for entidad in entidades:
        if entidad["tipo"] in ("line", "arc"):
            salida.append((entidad["id"], "start", _punto(entidad, "start")))
            salida.append((entidad["id"], "end", _punto(entidad, "end")))
    return salida


def _grupos(extremos: list[tuple[str, str, Punto]], tol: float) -> list[list[int]]:
    padre = list(range(len(extremos)))

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i in range(len(extremos)):
        for j in range(i + 1, len(extremos)):
            if math.dist(extremos[i][2], extremos[j][2]) <= tol:
                padre[raiz(i)] = raiz(j)
    grupos: dict[int, list[int]] = {}
    for i in range(len(extremos)):
        grupos.setdefault(raiz(i), []).append(i)
    return list(grupos.values())


def _cerrar(perfil: Perfil) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Verifica que líneas y arcos formen lazos cerrados; devuelve los pares que coinciden."""
    extremos = _extremos(perfil.entidades)
    pares = []
    for grupo in _grupos(extremos, perfil.tolerancia_si):
        nombres = [f"{extremos[i][0]}.{extremos[i][1]}" for i in grupo]
        x, y = extremos[grupo[0]][2]
        if len(grupo) == 1:
            raise ArgumentoInvalido(
                f"El contorno no está cerrado: {nombres[0]} en ({x:.9g}, {y:.9g}) m no coincide "
                "con ningún otro extremo (`close` es true).",
                details={"extremo_suelto": nombres[0]},
            )
        if len(grupo) > 2:
            raise ArgumentoInvalido(
                f"El contorno se ramifica: {', '.join(nombres)} coinciden en ({x:.9g}, {y:.9g}) m "
                "y un perfil cerrado admite solo dos extremos por vértice.",
                details={"extremos": nombres},
            )
        a, b = extremos[grupo[0]], extremos[grupo[1]]
        pares.append(((a[0], a[1]), (b[0], b[1])))
    return pares


# --- Entrada principal ------------------------------------------------------------------------


def _validar_plano(datos: dict[str, Any]) -> tuple[str, int | str]:
    from se_cli.core.modelado import validar_plano  # evita el ciclo: modelado importa croquis

    plano = datos.get("plane", "top")
    if not isinstance(plano, str):
        raise ArgumentoInvalido("`plane` tiene que ser un string (top, front, right o un índice).")
    return plano, validar_plano(plano)


def validar_perfil(datos: dict[str, Any]) -> Perfil:
    """Valida el esquema v1 y la geometría; levanta `ArgumentoInvalido` (exit 2) si algo falla."""
    _extra(datos, RAIZ_PERMITIDA, "El perfil")
    version = datos.get("version")
    if isinstance(version, bool) or version != VERSION:
        raise ArgumentoInvalido(
            f"`version` tiene que ser {VERSION} (se leyó {version!r}).",
            details={"version": version},
        )
    if not _booleano(datos, "close", True):
        raise ArgumentoInvalido(
            "Los perfiles abiertos no están en el esquema v1: `close` solo puede ser true."
        )
    largos = _Longitudes(_unidad_de_raiz(datos))
    tolerancia = TOLERANCIA_POR_DEFECTO
    if "tolerance" in datos:
        tolerancia = largos.valor(datos["tolerance"], "`tolerance`", positivo=True)
    plano, indice = _validar_plano(datos)
    perfil = Perfil(plano, indice, tolerancia, _booleano(datos, "auto_connect", True))
    perfil.entidades = _entidades(datos, largos, tolerancia)
    por_id = {e["id"]: e for e in perfil.entidades}
    explicitas = _restricciones(datos, por_id)
    for restriccion in explicitas:
        _verificar(restriccion, por_id, tolerancia)
    coincidentes = _cerrar(perfil)
    conectadas = {frozenset((r["a"], r["b"])) for r in explicitas if r["tipo"] == "connect"}
    automaticas = []
    if perfil.auto_connect:
        automaticas = [
            {"tipo": "connect", "a": a, "b": b, "auto": True}
            for a, b in coincidentes
            if frozenset((a, b)) not in conectadas
        ]
    # Primero las uniones (las pide el solver antes que las demás) y después lo declarado.
    uniones = automaticas + [r for r in explicitas if r["tipo"] == "connect"]
    perfil.restricciones = uniones + [r for r in explicitas if r["tipo"] != "connect"]
    return perfil


def cargar_perfil(fuente: str) -> Perfil:
    """Lee `fuente` (archivo o `-`), valida y devuelve el perfil."""
    return validar_perfil(parsear_json(leer_fuente(fuente)))


def caja_de(perfil: Perfil) -> dict[str, float]:
    """Caja envolvente en SI (los arcos aportan sus puntos extremos en x e y si los barren)."""
    xs: list[float] = []
    ys: list[float] = []
    for e in perfil.entidades:
        if e["tipo"] == "line":
            xs += [e["desde"][0], e["hasta"][0]]
            ys += [e["desde"][1], e["hasta"][1]]
        elif e["tipo"] == "circle":
            (cx, cy), r = e["centro"], e["radio"]
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        else:
            xs += [e["inicio"][0], e["fin"][0]]
            ys += [e["inicio"][1], e["fin"][1]]
            (cx, cy), r = e["centro"], e["radio"]
            for k, (ux, uy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
                if _barre(e, k * math.pi / 2):
                    xs.append(cx + r * ux)
                    ys.append(cy + r * uy)
    return {"x_min": min(xs), "y_min": min(ys), "x_max": max(xs), "y_max": max(ys)}


def _barre(arco: dict[str, Any], angulo: float) -> bool:
    """¿El arco pasa por `angulo` (rad)? El barrido es antihorario de start a end (cw: al revés)."""
    cx, cy = arco["centro"]
    ini = math.atan2(arco["inicio"][1] - cy, arco["inicio"][0] - cx)
    fin = math.atan2(arco["fin"][1] - cy, arco["fin"][0] - cx)
    if arco["dir"] == "cw":
        ini, fin = fin, ini
    barrido = (fin - ini) % (2 * math.pi)
    return (angulo - ini) % (2 * math.pi) <= barrido


__all__ = [
    "Perfil",
    "caja_de",
    "cargar_perfil",
    "leer_fuente",
    "parsear_json",
    "validar_perfil",
]
