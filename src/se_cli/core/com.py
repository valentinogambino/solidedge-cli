"""Escape genérico a la API COM: `se com get|set|invoke`.

Una ruta parte de la `Application` y se arma con segmentos separados por punto:
`ActiveDocument.Name`, `Documents.Count`, `Documents.Item(1).Name`. Cada segmento es un
identificador (letras, dígitos y guion bajo; no empieza con dígito ni con `_`) con una llamada
opcional de argumentos literales: enteros (`1`, `-2`), decimales (`0.5`), textos entre comillas
simples o dobles (`"Nombre"`), `true`, `false` y `null`.

El parser es propio y estricto: no usa `eval` ni `exec`. Cualquier otra cosa es exit 2.

Reglas de seguridad:
- `get` es de lectura: solo permite llamadas a `Item(...)`; llamar otro método es `invoke`.
- Un segmento `Quit` se rechaza siempre (exit 6): para cerrar Solid Edge está `se quit`.
- Los miembros que empiezan con `_` no existen para este comando.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import PurePath
from typing import Any

from se_cli.core.acceso import leer, opcional
from se_cli.core.errors import ArgumentoInvalido, SoloLectura
from se_cli.core.result import a_serializable, repr_corto

_IDENTIFICADOR = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_NUMERO = re.compile(r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?")
_ESCAPES = {"\\": "\\", '"': '"', "'": "'"}

LLAMADAS_DE_LECTURA = frozenset({"item"})
LIMITE_POR_DEFECTO = 50


@dataclass(frozen=True)
class Segmento:
    """Un paso de la ruta: `nombre` y, si hubo paréntesis, la tupla de argumentos."""

    nombre: str
    args: tuple[Any, ...] | None = None

    def __str__(self) -> str:
        if self.args is None:
            return self.nombre
        return f"{self.nombre}({', '.join(_literal_a_texto(a) for a in self.args)})"


def _literal_a_texto(valor: Any) -> str:
    if valor is None:
        return "null"
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    if isinstance(valor, str):
        return '"' + valor.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(valor)


# --- Parser -----------------------------------------------------------------------------------


class _Lector:
    def __init__(self, texto: str, que: str) -> None:
        self.texto = texto
        self.pos = 0
        self.que = que

    def error(self, motivo: str) -> ArgumentoInvalido:
        return ArgumentoInvalido(
            f"{self.que} inválido en la posición {self.pos + 1}: {motivo} ({self.texto!r}).",
            details={"entrada": self.texto, "posicion": self.pos + 1},
        )

    def fin(self) -> bool:
        return self.pos >= len(self.texto)

    def actual(self) -> str:
        return "" if self.fin() else self.texto[self.pos]

    def saltar_espacios(self) -> None:
        while not self.fin() and self.texto[self.pos] in " \t":
            self.pos += 1

    def identificador(self) -> str:
        if self.actual() == "_":
            raise self.error("los miembros que empiezan con _ no están permitidos")
        coincidencia = _IDENTIFICADOR.match(self.texto, self.pos)
        if coincidencia is None:
            raise self.error("se esperaba un nombre de miembro (letra y luego letras o dígitos)")
        self.pos = coincidencia.end()
        return coincidencia.group(0)

    def texto_entre_comillas(self) -> str:
        comilla = self.actual()
        self.pos += 1
        partes: list[str] = []
        while not self.fin():
            caracter = self.texto[self.pos]
            if caracter == comilla:
                self.pos += 1
                return "".join(partes)
            if caracter == "\\":
                self.pos += 1
                if self.actual() not in _ESCAPES:
                    raise self.error("escape no permitido (solo \\\\, \\\" y \\')")
                caracter = _ESCAPES[self.actual()]
            partes.append(caracter)
            self.pos += 1
        raise self.error("falta cerrar las comillas")

    def literal(self) -> Any:
        self.saltar_espacios()
        caracter = self.actual()
        if caracter in ('"', "'"):
            return self.texto_entre_comillas()
        coincidencia = _NUMERO.match(self.texto, self.pos)
        if coincidencia is not None:
            self.pos = coincidencia.end()
            numero = coincidencia.group(0)
            if re.fullmatch(r"[+-]?\d+", numero):
                return int(numero)
            return float(numero)
        for palabra, valor in (("true", True), ("false", False), ("null", None)):
            fin = self.pos + len(palabra)
            if self.texto.startswith(palabra, self.pos) and not (
                fin < len(self.texto) and self.texto[fin].isalnum()
            ):
                self.pos = fin
                return valor
        raise self.error(
            "se esperaba un literal (número, texto entre comillas, true, false o null)"
        )

    def argumentos(self) -> tuple[Any, ...]:
        """Lee `(a, b, ...)`; el `(` ya está en la posición actual."""
        self.pos += 1
        self.saltar_espacios()
        if self.actual() == ")":
            self.pos += 1
            return ()
        valores = [self.literal()]
        while True:
            self.saltar_espacios()
            if self.actual() == ",":
                self.pos += 1
                valores.append(self.literal())
            elif self.actual() == ")":
                self.pos += 1
                return tuple(valores)
            else:
                raise self.error("se esperaba , o )")


def parsear_ruta(texto: str) -> list[Segmento]:
    """Parseá una ruta `A.B(1).C` a segmentos. Exit 2 si no cumple la gramática."""
    if not texto or not texto.strip():
        raise ArgumentoInvalido("La ruta está vacía.")
    lector = _Lector(texto.strip(), "Ruta")
    segmentos: list[Segmento] = []
    while True:
        nombre = lector.identificador()
        args = lector.argumentos() if lector.actual() == "(" else None
        segmentos.append(Segmento(nombre, args))
        if lector.fin():
            return segmentos
        if lector.actual() != ".":
            raise lector.error("se esperaba . o el fin de la ruta")
        lector.pos += 1


def parsear_literal(texto: str, que: str = "El valor") -> Any:
    """Parseá un único literal (`10`, `0.5`, `"texto"`, `true`, `null`). Exit 2 si no es uno."""
    lector = _Lector(texto.strip(), que)
    valor = lector.literal()
    lector.saltar_espacios()
    if not lector.fin():
        raise lector.error("sobra texto después del literal")
    return valor


def rechazar_prohibidos(segmentos: list[Segmento]) -> None:
    """`Quit` está denegado por `com` (exit 6): se cierra con `se quit --yes`."""
    for segmento in segmentos:
        if segmento.nombre.lower() == "quit":
            raise SoloLectura(
                "`com` no cierra Solid Edge: usá `se quit --yes`.",
                details={"ruta": ".".join(str(s) for s in segmentos)},
            )


def texto_de_ruta(segmentos: list[Segmento]) -> str:
    return ".".join(str(s) for s in segmentos)


# --- Resolución -------------------------------------------------------------------------------

_PLANOS = (type(None), bool, int, float, str, bytes, datetime, date, time, Enum, PurePath, Mapping)


def _es_valor_plano(valor: Any) -> bool:
    return isinstance(valor, _PLANOS) or isinstance(valor, (tuple, list))


def _es_metodo(valor: Any) -> bool:
    """Un miembro que es una función enlazada (un método COM), no un valor ni un objeto COM."""
    return callable(valor) and not hasattr(valor, "_oleobj_") and not _es_valor_plano(valor)


def _miembro(objeto: Any, nombre: str) -> Any:
    try:
        return leer(lambda: getattr(objeto, nombre))
    except AttributeError:
        raise ArgumentoInvalido(
            f"El objeto no tiene el miembro {nombre!r}.", details={"miembro": nombre}
        ) from None


def _paso(objeto: Any, segmento: Segmento, *, lectura: bool) -> Any:
    if _es_valor_plano(objeto):
        raise ArgumentoInvalido(
            f"No se puede seguir con {segmento.nombre!r}: lo anterior ya es un valor.",
            details={"valor": a_serializable(objeto)},
        )
    if segmento.args is not None and lectura and segmento.nombre.lower() not in LLAMADAS_DE_LECTURA:
        raise ArgumentoInvalido(
            f"`get` solo admite llamadas a Item(...); {segmento.nombre}(...) es un método: "
            "usá `se com invoke`.",
            details={"miembro": segmento.nombre},
        )
    atributo = _miembro(objeto, segmento.nombre)
    if segmento.args is None:
        return atributo
    if not _es_metodo(atributo):
        raise ArgumentoInvalido(
            f"{segmento.nombre!r} no es un método: quitá los paréntesis.",
            details={"miembro": segmento.nombre},
        )
    args = segmento.args
    return leer(lambda: atributo(*args))


def recorrer(app: Any, segmentos: list[Segmento], *, lectura: bool = False) -> Any:
    """Aplicá los segmentos desde `app` y devolvé lo que queda (valor, objeto COM o método)."""
    actual = app
    for segmento in segmentos:
        actual = _paso(actual, segmento, lectura=lectura)
    return actual


# --- Serialización ----------------------------------------------------------------------------


def describir(valor: Any) -> Any:
    """Valor plano tal cual; un objeto COM como `{tipo: "objeto_com", repr, nombre?}`."""
    if isinstance(valor, (tuple, list)):
        return [describir(item) for item in valor]
    if _es_valor_plano(valor):
        return a_serializable(valor)
    descripcion: dict[str, Any] = {"tipo": "objeto_com", "repr": repr_corto(valor)}
    nombre = opcional(lambda: valor.Name)
    if isinstance(nombre, str) and nombre:
        descripcion["nombre"] = nombre
    return descripcion


def listar_coleccion(coleccion: Any, limite: int) -> dict[str, Any]:
    """Hasta `limite` ítems de una colección (`Count` + `Item(i)`, 1-based) con su `Name`."""
    if limite < 1:
        raise ArgumentoInvalido("--limit tiene que ser al menos 1.")
    if _es_valor_plano(coleccion) or _es_metodo(coleccion):
        raise ArgumentoInvalido("--list solo sirve con una colección (un objeto con Count e Item).")
    try:
        cantidad = int(leer(lambda: coleccion.Count))
        leer(lambda: coleccion.Item)
    except (AttributeError, TypeError, ValueError):
        raise ArgumentoInvalido(
            "--list solo sirve con una colección (un objeto con Count e Item)."
        ) from None
    items = []
    for indice in range(1, min(cantidad, limite) + 1):
        item = leer(lambda i=indice: coleccion.Item(i))
        items.append({"indice": indice, **_como_dict(describir(item))})
    return {
        "tipo": "coleccion",
        "cantidad": cantidad,
        "items": items,
        "truncado": cantidad > limite,
    }


def _como_dict(descripcion: Any) -> dict[str, Any]:
    return descripcion if isinstance(descripcion, dict) else {"valor": descripcion}


# --- Operaciones ------------------------------------------------------------------------------


def obtener(app: Any, segmentos: list[Segmento], *, listar: bool, limite: int) -> dict[str, Any]:
    """`get`: el valor al final de la ruta. Un método sin llamar es exit 2 (usá `invoke`)."""
    valor = recorrer(app, segmentos, lectura=True)
    if _es_metodo(valor):
        raise ArgumentoInvalido(
            f"{segmentos[-1].nombre!r} es un método: usá `se com invoke`.",
            details={"miembro": segmentos[-1].nombre},
        )
    resultado = listar_coleccion(valor, limite) if listar else describir(valor)
    return {"ruta": texto_de_ruta(segmentos), "valor": resultado}


def asignar(app: Any, segmentos: list[Segmento], valor: Any) -> dict[str, Any]:
    """`set`: asigná `valor` al miembro final (que no puede llevar paréntesis)."""
    ultimo = segmentos[-1]
    if ultimo.args is not None:
        raise ArgumentoInvalido("`set` necesita una propiedad al final, sin paréntesis.")
    padre = recorrer(app, segmentos[:-1], lectura=True)
    if _es_valor_plano(padre):
        raise ArgumentoInvalido("No se puede asignar sobre un valor: la ruta no llega a un objeto.")
    try:
        leer(lambda: setattr(padre, ultimo.nombre, valor))
    except AttributeError:
        raise ArgumentoInvalido(
            f"El objeto no tiene la propiedad {ultimo.nombre!r}.",
            details={"miembro": ultimo.nombre},
        ) from None
    actual = opcional(lambda: getattr(padre, ultimo.nombre))
    return {
        "ruta": texto_de_ruta(segmentos),
        "valor": a_serializable(valor),
        "valor_actual": describir(actual),
    }


def invocar(app: Any, segmentos: list[Segmento], args: tuple[Any, ...]) -> dict[str, Any]:
    """`invoke`: llamá al método final con `args` (o con los paréntesis de la propia ruta)."""
    ultimo = segmentos[-1]
    if ultimo.args is not None and args:
        raise ArgumentoInvalido("Pasá los argumentos entre paréntesis o sueltos, no los dos.")
    llamada = ultimo.args if ultimo.args is not None else args
    padre = recorrer(app, segmentos[:-1], lectura=False)
    if _es_valor_plano(padre):
        raise ArgumentoInvalido("La ruta no llega a un objeto con ese método.")
    metodo = _miembro(padre, ultimo.nombre)
    if not _es_metodo(metodo):
        raise ArgumentoInvalido(
            f"{ultimo.nombre!r} no es un método: usá `se com get` o `se com set`.",
            details={"miembro": ultimo.nombre},
        )
    resultado = leer(lambda: metodo(*llamada))
    return {
        "ruta": texto_de_ruta([*segmentos[:-1], Segmento(ultimo.nombre)]),
        "argumentos": a_serializable(list(llamada)),
        "resultado": describir(resultado),
    }


__all__ = [
    "LIMITE_POR_DEFECTO",
    "Segmento",
    "asignar",
    "describir",
    "invocar",
    "listar_coleccion",
    "obtener",
    "parsear_literal",
    "parsear_ruta",
    "rechazar_prohibidos",
    "recorrer",
    "texto_de_ruta",
]
