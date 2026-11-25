"""Fondo (marco y cuadro de rotulación) de una hoja de Draft que la plantilla no trae.

La plantilla ISO de Solid Edge 2026 trae los fondos `A4-Sheet` a `A1-Sheet`; para A5 y A0 se
genera uno copiando el fondo de tamaño más cercano y reubicando cada objeto en su esquina:

1. `Sheets.AddSheet("A5-Sheet", igBackgroundSection)` crea una hoja de fondo vacía, del tamaño
   pedido.
2. `Sheet.ReplaceBackground(archivo, "A4-Sheet")` copia en ella todo lo del fondo fuente (líneas,
   textos y los globos con propiedades). Lee de un archivo: se usa una copia temporal del propio
   Draft (`SaveCopyAs`), así sirve también con `--template`, y se borra al terminar.
3. Cada coordenada se ancla al borde izquierdo/inferior (no se mueve) o al derecho/superior (se
   corre lo que crece la hoja). El anclaje sale de comparar el fondo fuente con otro del mismo
   diseño (A4 contra A3: el rótulo y la tabla de revisiones solo se trasladan); si no hay otro
   igual (A1 tiene márgenes de 20 mm y un rótulo más alto que A2), por la mitad de la hoja en la
   que cae. Las líneas se mueven por extremo (el marco se estira); el resto, entero (`Move`).

Verificado en vivo el 2026-11-25 contra Solid Edge 2026 226.00.01.04 (PDF de A5 y A0 con el marco
a 10 y 20 mm del borde y el rótulo abajo a la derecha, dentro de la hoja). Si algo falla se borra
la hoja nueva y la hoja queda sin fondo, como antes.
"""

from __future__ import annotations

import contextlib
import math
import os
import tempfile
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from se_cli.core.acceso import leer
from se_cli.core.constants import valor as constante

SECCION_DE_FONDO = constante("igBackgroundSection")
TIPO_LINEA = constante("igLine2d")
TIPO_TEXTO = constante("igTextBox")

# Diferencia admitida al comparar dos fondos (metros) y al validar que todo entra en la hoja.
TOLERANCIA = 1e-4
MARGEN_DE_VALIDACION = 1e-3


# --- Lógica pura (sin COM) -------------------------------------------------------------------


@dataclass(frozen=True)
class Objeto:
    """Lo que hace falta de un objeto del fondo: tipo y coordenadas en metros.

    `puntos` son los extremos `(x1, y1, x2, y2)` de una línea o la caja `(xmin, ymin, xmax,
    ymax)` de cualquier otro objeto. `texto` solo en las cajas de texto.
    """

    tipo: int
    puntos: tuple[float, float, float, float]
    texto: str | None = None

    @property
    def es_linea(self) -> bool:
        return self.tipo == TIPO_LINEA


def _coeficiente(va: float, vb: float, da: float, db: float) -> float | None:
    """0 si la coordenada no se movió entre los dos fondos, 1 si se corrió lo que creció la hoja."""
    if abs(db - da) < TOLERANCIA:
        return None
    if abs(vb - va) < TOLERANCIA:
        return 0.0
    if abs((vb - va) - (db - da)) < TOLERANCIA:
        return 1.0
    return None


def anclajes_por_pareja(
    fuente: Sequence[Objeto],
    pareja: Sequence[Objeto],
    tam_fuente: tuple[float, float],
    tam_pareja: tuple[float, float],
) -> list[tuple[float, float, float, float]] | None:
    """Anclaje de cada coordenada comparando dos fondos del mismo diseño, o None si no lo son.

    Mismo diseño = misma cantidad y tipo de objetos en el mismo orden, y cada coordenada igual o
    corrida exactamente lo que cambia la hoja.
    """
    if len(fuente) != len(pareja) or not fuente:
        return None
    resultado: list[tuple[float, float, float, float]] = []
    for a, b in zip(fuente, pareja, strict=True):
        if a.tipo != b.tipo:
            return None
        dims = (0, 1, 0, 1)
        coefs = []
        for i in range(4):
            eje = dims[i]
            c = _coeficiente(a.puntos[i], b.puntos[i], tam_fuente[eje], tam_pareja[eje])
            if c is None:
                return None
            coefs.append(c)
        resultado.append((coefs[0], coefs[1], coefs[2], coefs[3]))
    return resultado


def _cruza(a: float, b: float, mitad: float) -> bool:
    return min(a, b) < mitad - TOLERANCIA and max(a, b) > mitad + TOLERANCIA


def anclajes_por_mitades(
    fuente: Sequence[Objeto], tam_fuente: tuple[float, float]
) -> list[tuple[float, float, float, float]] | None:
    """Anclaje por la mitad de la hoja: lo de la derecha (o arriba) se corre con ese borde.

    Una línea larga (más de media hoja: el marco), por extremo; el resto, entero. Si un objeto
    corto cruza la mitad de la hoja no se sabe a qué borde pertenece (en A4 el rótulo empieza a la
    izquierda del centro) y devuelve None en vez de partirlo.
    """
    ancho, alto = tam_fuente
    resultado = []
    for objeto in fuente:
        x1, y1, x2, y2 = objeto.puntos
        larga_x = objeto.es_linea and abs(x2 - x1) > ancho / 2
        larga_y = objeto.es_linea and abs(y2 - y1) > alto / 2
        if (not larga_x and _cruza(x1, x2, ancho / 2)) or (
            not larga_y and _cruza(y1, y2, alto / 2)
        ):
            return None
        if objeto.es_linea:
            cx1, cy1 = float(x1 > ancho / 2), float(y1 > alto / 2)
            cx2, cy2 = float(x2 > ancho / 2), float(y2 > alto / 2)
        else:
            cx1 = cx2 = float((x1 + x2) / 2 > ancho / 2)
            cy1 = cy2 = float((y1 + y2) / 2 > alto / 2)
        resultado.append((cx1, cy1, cx2, cy2))
    return resultado


def reubicar(
    objeto: Objeto,
    anclaje: tuple[float, float, float, float],
    tam_fuente: tuple[float, float],
    tam_nuevo: tuple[float, float],
) -> tuple[float, float, float, float]:
    """Coordenadas del objeto en la hoja nueva."""
    dx = tam_nuevo[0] - tam_fuente[0]
    dy = tam_nuevo[1] - tam_fuente[1]
    x1, y1, x2, y2 = objeto.puntos
    cx1, cy1, cx2, cy2 = anclaje
    if objeto.es_linea:
        return (x1 + cx1 * dx, y1 + cy1 * dy, x2 + cx2 * dx, y2 + cy2 * dy)
    # Un objeto que no es línea se traslada entero (su caja no se estira).
    return (x1 + cx1 * dx, y1 + cy1 * dy, x2 + cx1 * dx, y2 + cy1 * dy)


def dentro_de_la_hoja(puntos: tuple[float, float, float, float], tam: tuple[float, float]) -> bool:
    x1, y1, x2, y2 = puntos
    m = MARGEN_DE_VALIDACION
    return all(-m <= x <= tam[0] + m for x in (x1, x2)) and all(
        -m <= y <= tam[1] + m for y in (y1, y2)
    )


def elegir_fuentes(
    disponibles: dict[str, tuple[float, float]], tam: tuple[float, float]
) -> list[str]:
    """Fondos ordenados por cercanía de área al tamaño pedido (el primero es la fuente)."""
    area = tam[0] * tam[1]
    validos = {n: t for n, t in disponibles.items() if t[0] > 0 and t[1] > 0}
    return sorted(validos, key=lambda n: (abs(math.log(validos[n][0] * validos[n][1] / area)), n))


def nombre_de_tamano(fondo: str) -> str:
    """`A4-Sheet` → `A4` (el texto del rótulo que dice el tamaño)."""
    return fondo.removesuffix("-Sheet")


# --- Llamadas COM aisladas -------------------------------------------------------------------


def _tamano(hoja: Any) -> tuple[float, float]:
    setup = leer(lambda: hoja.SheetSetup)
    return float(leer(lambda: setup.SheetWidth)), float(leer(lambda: setup.SheetHeight))


def _caja(objeto: Any) -> tuple[float, float, float, float]:
    """`Range` de un objeto 2D: pywin32 devuelve los cuatro `[out]` planos o en dos pares."""
    rango = leer(lambda: objeto.Range(0.0, 0.0, 0.0, 0.0))
    planos = [v for par in rango for v in (par if isinstance(par, (tuple, list)) else (par,))]
    x1, y1, x2, y2 = (float(v) for v in planos[:4])
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _leer_objeto(objeto: Any) -> Objeto:
    tipo = int(leer(lambda: objeto.Type))
    if tipo == TIPO_LINEA:
        inicio = leer(objeto.GetStartPoint)
        fin = leer(objeto.GetEndPoint)
        puntos = (float(inicio[0]), float(inicio[1]), float(fin[0]), float(fin[1]))
        return Objeto(tipo, puntos)
    texto = str(leer(lambda: objeto.Text)) if tipo == TIPO_TEXTO else None
    return Objeto(tipo, _caja(objeto), texto)


def _objetos(hoja: Any) -> list[tuple[Any, Objeto]]:
    coleccion = leer(lambda: hoja.DrawingObjects)
    cantidad = int(leer(lambda: coleccion.Count))
    salida = []
    for i in range(1, cantidad + 1):
        com = leer(lambda i=i: coleccion.Item(i))
        salida.append((com, _leer_objeto(com)))
    return salida


def _mover(com: Any, objeto: Objeto, nuevo: tuple[float, float, float, float]) -> None:
    if objeto.es_linea:
        leer(lambda: com.SetStartPoint(nuevo[0], nuevo[1]))
        leer(lambda: com.SetEndPoint(nuevo[2], nuevo[3]))
        return
    x, y = objeto.puntos[0], objeto.puntos[1]
    if abs(nuevo[0] - x) > TOLERANCIA or abs(nuevo[1] - y) > TOLERANCIA:
        leer(lambda: com.Move(x, y, nuevo[0], nuevo[1]))


def generar(draft: Any, nombre: str, tam: tuple[float, float], opcion: int) -> dict[str, Any]:
    """Creá el fondo `<nombre>-Sheet` y devolvé cómo se hizo. Levanta si no se pudo.

    No asigna el fondo a ninguna hoja. Si algo falla, borra la hoja nueva antes de relanzar.
    """
    hojas = leer(lambda: draft.Sections.BackgroundSection.Sheets)
    existentes = {}
    for i in range(1, int(leer(lambda: hojas.Count)) + 1):
        hoja = leer(lambda i=i: hojas.Item(i))
        existentes[str(leer(lambda hoja=hoja: hoja.Name))] = (hoja, _tamano(hoja))
    orden = elegir_fuentes({n: t for n, (_, t) in existentes.items()}, tam)
    if not orden:
        raise ValueError("la plantilla no tiene fondos de los que partir")
    fuente_nombre = orden[0]
    fuente_hoja, tam_fuente = existentes[fuente_nombre]
    fuente = _objetos(fuente_hoja)

    anclajes = None
    referencia = None
    metodo = "pareja"
    if len(orden) > 1:
        pareja_hoja, tam_pareja = existentes[orden[1]]
        anclajes = anclajes_por_pareja(
            [o for _, o in fuente], [o for _, o in _objetos(pareja_hoja)], tam_fuente, tam_pareja
        )
        referencia = orden[1] if anclajes is not None else None
    if anclajes is None:
        anclajes = anclajes_por_mitades([o for _, o in fuente], tam_fuente)
        metodo = "mitades"
    if anclajes is None:
        raise ValueError(f"no se puede saber a qué borde va cada objeto de {fuente_nombre}")

    copia = os.path.join(tempfile.gettempdir(), f"se-fondo-{uuid.uuid4().hex[:8]}.dft")
    nueva = None
    try:
        leer(lambda: draft.SaveCopyAs(copia))
        nueva = leer(lambda: draft.Sheets.AddSheet(f"{nombre}-Sheet", SECCION_DE_FONDO))
        setup = leer(lambda: nueva.SheetSetup)
        leer(lambda: setattr(setup, "SheetSizeOption", opcion))
        leer(lambda: nueva.ReplaceBackground(copia, fuente_nombre))
        copiados = _objetos(nueva)
        if [o.tipo for _, o in copiados] != [o.tipo for _, o in fuente]:
            raise ValueError("la copia del fondo no coincide con la fuente")
        etiqueta = nombre_de_tamano(fuente_nombre)
        for (com, objeto), anclaje in zip(copiados, anclajes, strict=True):
            destino = reubicar(objeto, anclaje, tam_fuente, tam)
            if not dentro_de_la_hoja(destino, tam):
                raise ValueError(f"un objeto del fondo queda fuera de la hoja: {destino}")
            _mover(com, objeto, destino)
            if objeto.texto is not None and objeto.texto.strip() == etiqueta:
                leer(lambda com=com: setattr(com, "Text", nombre))
    except BaseException:
        if nueva is not None:
            with contextlib.suppress(Exception):
                leer(nueva.Delete)
        raise
    finally:
        with contextlib.suppress(OSError):
            os.remove(copia)
    return {
        "desde": fuente_nombre,
        "metodo": metodo,
        "referencia": referencia,
        "objetos": len(fuente),
    }


__all__ = [
    "Objeto",
    "anclajes_por_mitades",
    "anclajes_por_pareja",
    "dentro_de_la_hoja",
    "elegir_fuentes",
    "generar",
    "nombre_de_tamano",
    "reubicar",
]
