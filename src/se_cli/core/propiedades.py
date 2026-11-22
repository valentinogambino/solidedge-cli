"""Propiedades de archivo del documento (`doc.Properties`: conjuntos de propiedades).

Cada conjunto (`SummaryInformation`, `DocumentSummaryInformation`, `ProjectInformation`,
`Custom`, ...) es una colección de propiedades con `Name` y `Value`. Los nombres de conjunto
se comparan sin distinguir mayúsculas. Solo `Custom` admite crear propiedades nuevas.
"""

from __future__ import annotations

from typing import Any

from se_cli.core import documentos
from se_cli.core.acceso import items, leer, opcional
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado, SoloLectura

CONJUNTO_PERSONALIZADO = "Custom"


def _nombre(objeto: Any) -> str:
    texto = opcional(lambda: objeto.Name)
    return str(texto) if texto is not None else ""


def _conjuntos(doc: Any) -> list[Any]:
    return list(items(leer(lambda: doc.Properties)))


def _conjunto(doc: Any, nombre: str) -> Any:
    """Conjunto por nombre, o `DocNoEncontrado` (exit 5) con los que hay."""
    buscado = nombre.strip().casefold()
    conjuntos = _conjuntos(doc)
    for conjunto in conjuntos:
        if _nombre(conjunto).casefold() == buscado:
            return conjunto
    raise DocNoEncontrado(
        f"No existe el conjunto de propiedades {nombre!r}.",
        details={"nombre": nombre, "conjuntos": [_nombre(c) for c in conjuntos]},
    )


def _propiedades(conjunto: Any) -> list[tuple[str, Any]]:
    """`[(nombre, objeto propiedad)]` de un conjunto."""
    return [(_nombre(propiedad), propiedad) for propiedad in items(conjunto)]


def _valor(propiedad: Any) -> Any:
    return opcional(lambda: propiedad.Value)


def _coincidencias(
    doc: Any, nombre: str | None, conjunto: str | None
) -> list[tuple[str, str, Any]]:
    """`[(conjunto, propiedad, objeto)]` dentro de un conjunto o de todos."""
    if conjunto is not None:
        recorrer = [_conjunto(doc, conjunto)]
    else:
        recorrer = _conjuntos(doc)
    buscado = None if nombre is None else nombre.strip().casefold()
    encontradas = []
    for cj in recorrer:
        for nombre_propiedad, propiedad in _propiedades(cj):
            if buscado is None or nombre_propiedad.casefold() == buscado:
                encontradas.append((_nombre(cj), nombre_propiedad, propiedad))
    return encontradas


def obtener(doc: Any, nombre: str | None = None, conjunto: str | None = None) -> dict[str, Any]:
    """Todas las propiedades (de un conjunto o de todos) o una sola por nombre.

    Sin nombre: `{cantidad, propiedades: [{conjunto, nombre, valor}]}`. Con nombre:
    `{conjunto, nombre, valor}`; inexistente da exit 5 y repetida en varios conjuntos pide
    `--set` (exit 2).
    """
    encontradas = _coincidencias(doc, nombre, conjunto)
    if nombre is None:
        lista = [
            {"conjunto": cj, "nombre": pr, "valor": _valor(obj)} for cj, pr, obj in encontradas
        ]
        return {"cantidad": len(lista), "propiedades": lista}
    if not encontradas:
        donde = f" en el conjunto {conjunto!r}" if conjunto else ""
        raise DocNoEncontrado(
            f"No existe la propiedad {nombre!r}{donde}.", details={"nombre": nombre}
        )
    if len(encontradas) > 1:
        raise ArgumentoInvalido(
            f"La propiedad {nombre!r} está en varios conjuntos: "
            f"{', '.join(cj for cj, _, _ in encontradas)}. Indicá uno con --set.",
            details={"conjuntos": [cj for cj, _, _ in encontradas]},
        )
    cj, pr, obj = encontradas[0]
    return {"conjunto": cj, "nombre": pr, "valor": _valor(obj)}


def _validar_guardado(app: Any, selector: str | None) -> None:
    """Antes de escribir, comprobá que `--save` va a poder guardar (si no, no se toca nada)."""
    indice, doc = documentos.resolver(app, selector)
    descripcion = documentos.descripcion_de(app, doc, indice)
    if descripcion["solo_lectura"]:
        raise SoloLectura(
            f"{descripcion['nombre']} está abierto como solo lectura: no se puede usar --save."
        )
    if descripcion["ruta"] is None:
        raise ArgumentoInvalido(
            f"{descripcion['nombre']} nunca se guardó: usá `se docs save-as <destino>`."
        )


def modificar(
    app: Any,
    selector: str | None,
    nombre: str,
    valor: str,
    conjunto: str = CONJUNTO_PERSONALIZADO,
    guardar: bool = False,
) -> dict[str, Any]:
    """Escribí una propiedad; en `Custom` la crea si no existe, en los demás exit 5.

    No guarda el documento salvo `guardar` (`guardado: false` lo informa).
    """
    if not nombre.strip():
        raise ArgumentoInvalido("El nombre de la propiedad está vacío.")
    doc = documentos.resolver(app, selector)[1]
    cj = _conjunto(doc, conjunto)
    nombre_cj = _nombre(cj)
    existente = next(
        (obj for pr, obj in _propiedades(cj) if pr.casefold() == nombre.strip().casefold()), None
    )
    if existente is None and nombre_cj.casefold() != CONJUNTO_PERSONALIZADO.casefold():
        raise DocNoEncontrado(
            f"No existe la propiedad {nombre!r} en {nombre_cj}: solo {CONJUNTO_PERSONALIZADO} "
            "admite propiedades nuevas.",
            details={"nombre": nombre, "conjunto": nombre_cj},
        )
    if guardar:
        _validar_guardado(app, selector)

    if existente is None:
        antes = None
        leer(lambda: cj.Add(nombre.strip(), valor))
        creada = True
    else:
        antes = _valor(existente)
        leer(lambda: setattr(existente, "Value", valor))
        creada = False
    despues = _valor(existente) if existente is not None else valor
    if guardar:
        documentos.guardar(app, selector)
    return {
        "conjunto": nombre_cj,
        "nombre": nombre.strip(),
        "antes": antes,
        "despues": despues,
        "creada": creada,
        "guardado": guardar,
    }


__all__ = ["CONJUNTO_PERSONALIZADO", "modificar", "obtener"]
