"""Render de resultados: JSON puro o texto/tablas Rich en modo humano.

Los `Console` se crean en cada llamada para escribir en el `sys.stdout`/`sys.stderr` vigente
(así funcionan con `CliRunner` y con redirecciones).
"""

from __future__ import annotations

import os
import sys
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from se_cli.core.errors import SeError
from se_cli.core.result import a_json, a_serializable, fallo, ok


def forzar_utf8() -> None:
    """Salida en UTF-8 aunque la consola de Windows use otra codificación."""
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None:
            try:
                reconfigurar(encoding="utf-8", errors="replace")
            except Exception:  # pragma: no cover - flujos que no se pueden reconfigurar
                pass


def imprimir_json(sobre: dict[str, Any]) -> None:
    """Sobre `{ok, data, error}` en una sola línea por stdout, sin Rich ni colores."""
    sys.stdout.write(a_json(sobre) + "\n")
    sys.stdout.flush()


def _celda(valor: Any) -> str:
    valor = a_serializable(valor)
    if valor is None:
        return "-"
    if valor is True:
        return "sí"
    if valor is False:
        return "no"
    if isinstance(valor, (list, dict)):
        return a_json(valor)
    return str(valor)


def _tabla_de_filas(filas: list[dict[str, Any]], titulo: str | None = None) -> Table:
    columnas: list[str] = []
    for fila in filas:
        for clave in fila:
            if clave not in columnas:
                columnas.append(clave)
    tabla = Table(title=titulo, title_justify="left")
    for columna in columnas:
        tabla.add_column(columna)
    for fila in filas:
        tabla.add_row(*(_celda(fila.get(columna)) for columna in columnas))
    return tabla


def _es_lista_de_dicts(valor: Any) -> bool:
    return isinstance(valor, list) and bool(valor) and all(isinstance(x, dict) for x in valor)


def _etiqueta_de_nodo(nodo: dict[str, Any]) -> Text:
    archivo = os.path.basename(str(nodo.get("archivo") or "")) or "-"
    texto = f"{nodo.get('nombre', '')} x{nodo.get('cantidad', 1)}  ({archivo})"
    if nodo.get("visible") is False:
        texto += "  [oculto]"
    if nodo.get("ciclo"):
        texto += "  [ciclo]"
    if nodo.get("truncado"):
        texto += "  [...]"
    return Text(texto)


def _arbol_de_nodos(nodos: list[dict[str, Any]], titulo: str) -> Tree:
    """`rich.tree` de nodos `{nombre, archivo, cantidad, hijos}` (`se asm tree`)."""
    arbol = Tree(Text(titulo))

    def agregar(padre: Tree, lista: list[dict[str, Any]]) -> None:
        for nodo in lista:
            agregar(padre.add(_etiqueta_de_nodo(nodo)), nodo.get("hijos") or [])

    agregar(arbol, nodos)
    return arbol


def renderizar_humano(data: Any, consola: Console) -> None:
    """Dibujá `data` como tabla clave/valor (dict), tabla de filas (lista) o texto.

    Un dict con la clave `arbol` (lista de nodos con `hijos`) se dibuja como `rich.tree`.
    """
    if isinstance(data, dict) and isinstance(data.get("arbol"), list):
        consola.print(_arbol_de_nodos(data["arbol"], str(data.get("documento", "ensamble"))))
    elif isinstance(data, dict):
        simples = {k: v for k, v in data.items() if not _es_lista_de_dicts(v)}
        if data.get("dry_run"):
            consola.print(Text("[dry-run] No se ejecutó nada; esto es lo que se haría:"))
        if simples:
            tabla = Table(show_header=False)
            for clave, valor in simples.items():
                tabla.add_row(str(clave), _celda(valor))
            consola.print(tabla)
        for clave, valor in data.items():
            if _es_lista_de_dicts(valor):
                consola.print(_tabla_de_filas(valor, titulo=str(clave)))
    elif _es_lista_de_dicts(data):
        consola.print(_tabla_de_filas(data))
    elif data is not None:
        consola.print(Text(_celda(data)))


def emitir_ok(data: Any, *, como_json: bool) -> None:
    if como_json:
        imprimir_json(ok(data))
    else:
        renderizar_humano(data, Console())


def emitir_error(error: SeError, *, como_json: bool) -> None:
    if como_json:
        imprimir_json(fallo(error))
    else:
        mensaje = Text(f"Error [{error.codigo}]: {error.mensaje}", style="red")
        Console(stderr=True).print(mensaje)
