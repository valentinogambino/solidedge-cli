"""Vistas de un Draft: nombres, escala y distribución en la hoja. Python puro, sin COM.

Todo en metros, con el origen de la hoja en su esquina inferior izquierda (como la API). Una
vista se coloca por su centro. La hoja se reparte en una grilla de celdas iguales y cada vista
ocupa una; así dos vistas nunca se superponen mientras la escala haga entrar cada una en su
celda (`elegir_escala` lo garantiza con `--scale auto`).

El área útil excluye el marco de la hoja y toda la franja inferior del cuadro de rotulación, con
la altura real de cada tamaño (`MEDIDAS_DE_HOJA`), más una holgura (`HOLGURA`).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from se_cli.core.constants import ViewOrientationConstants
from se_cli.core.errors import ArgumentoInvalido

# Tamaños ISO apaisados (ancho, alto) en metros.
HOJAS: dict[str, tuple[float, float]] = {
    "A5": (0.210, 0.148),
    "A4": (0.297, 0.210),
    "A3": (0.420, 0.297),
    "A2": (0.594, 0.420),
    "A1": (0.841, 0.594),
    "A0": (1.189, 0.841),
}

# Hoja por defecto cuando no se pide ninguna ni se puede leer la de la plantilla.
HOJA_POR_DEFECTO = "A3"

# Vista pedida → constante de `ViewOrientationConstants`. `iso` es la isométrica de Solid Edge
# (mirando desde la esquina superior, frontal y derecha).
ORIENTACIONES: dict[str, str] = {
    "front": "igFrontView",
    "top": "igTopView",
    "right": "igRightView",
    "left": "igLeftView",
    "bottom": "igBottomView",
    "back": "igBackView",
    "iso": "igTopFrontRightView",
}
ALIAS_DE_VISTA = {"isometric": "iso", "isometrica": "iso"}
VISTAS_POR_DEFECTO = ("front", "top", "right", "iso")
MAXIMO_DE_VISTAS = 6

# Escalas normalizadas de la serie ISO 5455 (factor de la vista respecto del modelo), de mayor a
# menor: `elegir_escala` toma la primera con la que entran todas las vistas.
ESCALAS_NORMALIZADAS: tuple[tuple[str, float], ...] = (
    ("50:1", 50.0),
    ("20:1", 20.0),
    ("10:1", 10.0),
    ("5:1", 5.0),
    ("2:1", 2.0),
    ("1:1", 1.0),
    ("1:2", 1 / 2),
    ("1:5", 1 / 5),
    ("1:10", 1 / 10),
    ("1:20", 1 / 20),
    ("1:50", 1 / 50),
    ("1:100", 1 / 100),
    ("1:200", 1 / 200),
    ("1:500", 1 / 500),
    ("1:1000", 1 / 1000),
)

# Medidas de la plantilla ISO de Solid Edge 2026: `(distancia del marco al borde, altura desde el
# borde inferior hasta el tope del cuadro de rotulación)`, en metros. Medidas en vivo el
# 2026-11-26 sobre los fondos A5-Sheet a A0-Sheet (ver README, "Vistas sobre el rótulo"): A5 a A2
# tienen el marco a 10 mm y el rótulo de 50,8 mm sobre él (tope a 60,8 mm del borde); A1 y A0, el
# marco a 20 mm y el rótulo de 57,1 mm (tope a 77,1 mm).
MEDIDAS_DE_HOJA: dict[str, tuple[float, float]] = {
    "A5": (0.010, 0.0608),
    "A4": (0.010, 0.0608),
    "A3": (0.010, 0.0608),
    "A2": (0.010, 0.0608),
    "A1": (0.020, 0.0771),
    "A0": (0.020, 0.0771),
}
# Aire entre el marco o el rótulo y las vistas.
HOLGURA = 0.005
# Un tamaño de hoja se reconoce por su ancho con esta tolerancia (m); una hoja desconocida usa las
# medidas de A1 si es tan grande como A1 y las de A2 si no.
TOLERANCIA_DE_HOJA = 0.002
# Una vista puede ocupar a lo sumo esta fracción de su celda: deja aire entre vistas.
RELLENO = 0.85

# Celda preferida (columna, fila; fila 0 = abajo) de cada vista, como en la proyección del
# tercer ángulo: arriba de la frontal la superior, a su derecha la derecha.
_PREFERIDAS = {
    "front": (0, 0),
    "top": (0, 1),
    "right": (1, 0),
    "iso": (1, 1),
    "left": (1, 0),
    "bottom": (0, 1),
    "back": (2, 0),
}


def parsear_vistas(texto: str | None) -> list[str]:
    """Lista de vistas de `--views` ("front,top"); inválida o repetida da exit 2."""
    if texto is None:
        return list(VISTAS_POR_DEFECTO)
    nombres: list[str] = []
    for crudo in texto.split(","):
        nombre = crudo.strip().lower()
        if not nombre:
            continue
        nombre = ALIAS_DE_VISTA.get(nombre, nombre)
        if nombre not in ORIENTACIONES:
            raise ArgumentoInvalido(
                f"Vista inválida: {crudo.strip()!r}. Usá {', '.join(ORIENTACIONES)}.",
                details={"validas": list(ORIENTACIONES)},
            )
        if nombre in nombres:
            raise ArgumentoInvalido(f"La vista {nombre!r} está repetida en --views.")
        nombres.append(nombre)
    if not nombres:
        raise ArgumentoInvalido("--views no tiene ninguna vista.")
    if len(nombres) > MAXIMO_DE_VISTAS:
        raise ArgumentoInvalido(f"Se admiten hasta {MAXIMO_DE_VISTAS} vistas por hoja.")
    return nombres


def orientacion_de(nombre: str) -> int:
    """Valor de `ViewOrientationConstants` de una vista ya validada."""
    return int(getattr(ViewOrientationConstants, ORIENTACIONES[nombre]))


def parsear_hoja(texto: str | None) -> str | None:
    """Nombre de hoja normalizado (`a3` → `A3`); desconocida da exit 2. None si no se pidió."""
    if texto is None:
        return None
    clave = texto.strip().upper()
    if clave not in HOJAS:
        raise ArgumentoInvalido(
            f"Hoja inválida: {texto!r}. Usá {', '.join(HOJAS)}.", details={"validas": list(HOJAS)}
        )
    return clave


_RAZON = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*$")


def parsear_escala(texto: str) -> float | None:
    """Factor de escala de `--scale`: `1:2` → 0.5, `2:1` → 2.0, `0.5` → 0.5, `auto` → None.

    Un texto mal formado, cero o negativo da exit 2.
    """
    limpio = texto.strip().lower()
    if limpio == "auto":
        return None
    razon = _RAZON.match(limpio)
    try:
        if razon:
            factor = float(razon.group(1)) / float(razon.group(2))
        else:
            factor = float(limpio)
    except (ValueError, ZeroDivisionError):
        factor = math.nan
    if not math.isfinite(factor) or factor <= 0:
        raise ArgumentoInvalido(
            f"Escala inválida: {texto!r}. Usá 1:2, 2:1, 0.5 o auto.", details={"escala": texto}
        )
    return factor


def nombre_de_escala(factor: float) -> str:
    """Texto legible de un factor: `1:2`, `2:1`, `1:1`; sin razón entera exacta, el decimal."""
    if math.isclose(factor, 1.0):
        return "1:1"
    if factor < 1 and math.isclose(1 / factor, round(1 / factor), rel_tol=1e-9):
        return f"1:{round(1 / factor)}"
    if factor > 1 and math.isclose(factor, round(factor), rel_tol=1e-9):
        return f"{round(factor)}:1"
    return f"{factor:g}"


@dataclass(frozen=True)
class PosicionVista:
    nombre: str
    x: float
    y: float


@dataclass(frozen=True)
class Distribucion:
    """Celda que le toca a cada vista y su centro (metros, origen abajo a la izquierda).

    `area_util` es `(x_min, y_min, x_max, y_max)`: sin marco y por encima del rótulo.
    """

    celda: tuple[float, float]
    posiciones: tuple[PosicionVista, ...]
    area_util: tuple[float, float, float, float]


def medidas_de_hoja(hoja: tuple[float, float]) -> tuple[float, float]:
    """`(marco, tope del rótulo)` de una hoja `(ancho, alto)` según `MEDIDAS_DE_HOJA`."""
    for nombre, (ancho, _) in HOJAS.items():
        if abs(hoja[0] - ancho) <= TOLERANCIA_DE_HOJA:
            return MEDIDAS_DE_HOJA[nombre]
    return MEDIDAS_DE_HOJA["A1" if hoja[0] >= HOJAS["A1"][0] else "A2"]


def area_util(hoja: tuple[float, float]) -> tuple[float, float, float, float]:
    """`(x_min, y_min, x_max, y_max)` donde pueden ir vistas: dentro del marco y sobre el rótulo."""
    marco, rotulo = medidas_de_hoja(hoja)
    ancho, alto = hoja
    return marco + HOLGURA, rotulo + HOLGURA, ancho - marco - HOLGURA, alto - marco - HOLGURA


def _grilla(cantidad: int) -> tuple[int, int]:
    """(columnas, filas) para `cantidad` vistas."""
    if cantidad == 1:
        return 1, 1
    if cantidad == 2:
        return 2, 1
    if cantidad <= 4:
        return 2, 2
    return 3, 2


def distribuir(hoja: tuple[float, float], vistas: list[str]) -> Distribucion:
    """Centros de las vistas en una hoja `(ancho, alto)`, sin superposición y dentro de la hoja.

    Las vistas conocidas van a su celda de proyección (frontal abajo a la izquierda, superior
    arriba de ella, derecha a su lado, isométrica en la esquina libre); las demás ocupan las
    celdas que sobran. Las posiciones salen en el orden de `vistas`.
    """
    if not vistas:
        raise ArgumentoInvalido("Hace falta al menos una vista.")
    ancho, alto = hoja
    columnas, filas = _grilla(len(vistas))
    zona = area_util(hoja)
    util_ancho = zona[2] - zona[0]
    util_alto = zona[3] - zona[1]
    if util_ancho <= 0 or util_alto <= 0:
        raise ArgumentoInvalido(f"La hoja {ancho:g} x {alto:g} m es demasiado chica.")
    celda = (util_ancho / columnas, util_alto / filas)

    libres = [(c, f) for f in range(filas - 1, -1, -1) for c in range(columnas)]
    asignadas: dict[str, tuple[int, int]] = {}
    for nombre in vistas:
        preferida = _PREFERIDAS.get(nombre)
        if preferida in libres:
            asignadas[nombre] = preferida
            libres.remove(preferida)
    for nombre in vistas:
        if nombre not in asignadas:
            asignadas[nombre] = libres.pop(0)

    posiciones = tuple(
        PosicionVista(
            nombre,
            zona[0] + (asignadas[nombre][0] + 0.5) * celda[0],
            zona[1] + (asignadas[nombre][1] + 0.5) * celda[1],
        )
        for nombre in vistas
    )
    return Distribucion(celda, posiciones, zona)


def extension_de_vista(nombre: str, caja: tuple[float, float, float]) -> tuple[float, float]:
    """Ancho y alto (a escala 1:1) que ocupa una vista de un modelo de caja `(dx, dy, dz)`.

    Supone los ejes de Solid Edge: la frontal mira en Y (ancho X, alto Z), la superior en Z
    (X por Y) y la derecha en X (Y por Z). La isométrica se acota por exceso.
    """
    dx, dy, dz = caja
    if nombre in ("front", "back"):
        return dx, dz
    if nombre in ("top", "bottom"):
        return dx, dy
    if nombre in ("right", "left"):
        return dy, dz
    return 0.866 * (dx + dy), dz + 0.5 * (dx + dy)


def entran(
    caja: tuple[float, float, float],
    celda: tuple[float, float],
    nombres: list[str],
    factor: float,
    relleno: float = 1.0,
) -> bool:
    """Si todas las vistas, a esa escala, caben en su celda (con la fracción `relleno` de ella)."""
    limite_x, limite_y = celda[0] * relleno, celda[1] * relleno
    return all(
        w * factor <= limite_x and h * factor <= limite_y
        for w, h in (extension_de_vista(v, caja) for v in nombres)
    )


def elegir_escala(
    caja: tuple[float, float, float] | None, celda: tuple[float, float], vistas: list[str]
) -> tuple[float, bool]:
    """Escala de la serie ISO 5455 más grande con la que entran todas las vistas en su celda.

    Devuelve `(factor, auto)`. Sin caja del modelo (la API no la dio), 1:1 y `auto=False`.
    Si ni la más chica de la serie alcanza, devuelve esa igual.
    """
    if caja is None or any(d < 0 or not math.isfinite(d) for d in caja):
        return 1.0, False
    for _, factor in ESCALAS_NORMALIZADAS:
        if entran(caja, celda, vistas, factor, RELLENO):
            return factor, True
    return ESCALAS_NORMALIZADAS[-1][1], True


__all__ = [
    "ALIAS_DE_VISTA",
    "ESCALAS_NORMALIZADAS",
    "HOJAS",
    "HOJA_POR_DEFECTO",
    "HOLGURA",
    "MEDIDAS_DE_HOJA",
    "ORIENTACIONES",
    "RELLENO",
    "VISTAS_POR_DEFECTO",
    "Distribucion",
    "PosicionVista",
    "area_util",
    "distribuir",
    "elegir_escala",
    "entran",
    "extension_de_vista",
    "medidas_de_hoja",
    "nombre_de_escala",
    "orientacion_de",
    "parsear_escala",
    "parsear_hoja",
    "parsear_vistas",
]
