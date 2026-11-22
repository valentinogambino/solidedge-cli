"""Estructura de un ensamble: árbol de ocurrencias y lista de materiales.

`doc.Occurrences` trae las ocurrencias de primer nivel; cada una expone `Name`,
`OccurrenceFileName`, `Visible` y `Subassembly`, y un subensamble trae sus hijos en
`SubOccurrences` (si no, se prueba `OccurrenceDocument.Occurrences`). `Occurrence` no tiene un
miembro de supresión (verificado contra assembly.tlb), así que el nodo no informa `suprimido`.
"""

from __future__ import annotations

import os
from typing import Any

from se_cli.core.acceso import exigir_tipo, items, leer, opcional
from se_cli.core.errors import ArgumentoInvalido

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


def _booleano(valor: Any) -> bool | None:
    return None if valor is None else bool(valor)


def _nivel(
    coleccion: Any, ancestros: tuple[str, ...], nivel: int, maximo: int
) -> list[dict[str, Any]]:
    """Nodos de un nivel. Las ocurrencias hermanas del mismo archivo se agrupan en `cantidad`."""
    grupos: dict[tuple[str, bool | None, bool], dict[str, Any]] = {}
    for ocurrencia in items(coleccion):
        archivo = str(opcional(lambda o=ocurrencia: o.OccurrenceFileName) or "")
        visible = _booleano(opcional(lambda o=ocurrencia: o.Visible))
        es_sub = bool(opcional(lambda o=ocurrencia: o.Subassembly))
        clave = (os.path.normcase(archivo), visible, es_sub)
        if clave in grupos:
            grupos[clave]["cantidad"] += 1
            continue
        nodo: dict[str, Any] = {
            "nombre": str(opcional(lambda o=ocurrencia: o.Name) or ""),
            "archivo": archivo,
            "cantidad": 1,
            "visible": visible,
            "ensamble": es_sub,
            "hijos": [],
        }
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


__all__ = ["PROFUNDIDAD_POR_DEFECTO", "arbol", "validar_profundidad"]
