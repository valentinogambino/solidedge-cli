"""Materiales del documento: `se material list|get|set`.

Todo pasa por `Application.GetMaterialTable()` (verificado en vivo el 2026-11-25 contra SE 2026):

- `GetMaterialLibraryList()` devuelve `(nombres, cantidad)`; `GetMaterialListFromLibrary(lib)`
  devuelve `(cantidad, nombres)`, en el orden inverso. `GetMaterialList` da E_FAIL, no se usa.
- `GetCurrentMaterialName(doc)` es `""` si el documento no tiene material.
- `ApplyMaterialToDoc(doc, nombre, biblioteca)` asigna el material y sus propiedades (densidad
  incluida); con un nombre que no está en la biblioteca da E_INVALIDARG. Por eso el nombre se
  busca antes en las bibliotecas y se usa con la grafía exacta de Solid Edge.

Con material asignado, `se mass` sin `--density` deja de dar estado 2.
"""

from __future__ import annotations

from typing import Any

from se_cli.core.acceso import documento, exigir_tipo, leer
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado

TIPOS_CON_MATERIAL = ("part", "sheetmetal")


def _tabla(app: Any) -> Any:
    return leer(lambda: app.GetMaterialTable())


def _lista(valor: Any) -> list[str]:
    return [str(nombre) for nombre in (valor or ())]


def bibliotecas(tabla: Any) -> list[str]:
    """Nombres de las bibliotecas de materiales, en el orden de Solid Edge."""
    nombres, _cantidad = leer(lambda: tabla.GetMaterialLibraryList())
    return _lista(nombres)


def materiales_de(tabla: Any, biblioteca: str) -> list[str]:
    _cantidad, nombres = leer(lambda: tabla.GetMaterialListFromLibrary(biblioteca))
    return _lista(nombres)


def _elegir_biblioteca(tabla: Any, biblioteca: str | None) -> list[str]:
    todas = bibliotecas(tabla)
    if biblioteca is None:
        return todas
    for nombre in todas:
        if nombre.casefold() == biblioteca.strip().casefold():
            return [nombre]
    raise DocNoEncontrado(
        f"No existe la biblioteca de materiales {biblioteca!r}.",
        details={"bibliotecas": todas},
    )


def listar(app: Any, biblioteca: str | None = None) -> dict[str, Any]:
    """Materiales disponibles, agrupados por biblioteca (exit 5 si la biblioteca no existe)."""
    tabla = _tabla(app)
    return {
        "bibliotecas": [
            {"biblioteca": nombre, "materiales": materiales_de(tabla, nombre)}
            for nombre in _elegir_biblioteca(tabla, biblioteca)
        ]
    }


def _nombre_actual(tabla: Any, doc: Any) -> str | None:
    nombre = str(leer(lambda: tabla.GetCurrentMaterialName(doc)) or "").strip()
    return nombre or None


def obtener(app: Any, selector: str | None) -> dict[str, Any]:
    """Material del documento (`None` si no tiene)."""
    doc = documento(app, selector)
    exigir_tipo(doc, TIPOS_CON_MATERIAL, "material get")
    return {"material": _nombre_actual(_tabla(app), doc)}


def validar_nombre(nombre: str) -> str:
    limpio = nombre.strip()
    if not limpio:
        raise ArgumentoInvalido("El nombre del material está vacío.")
    return limpio


def _buscar(tabla: Any, nombre: str, biblioteca: str | None) -> tuple[str, str]:
    """`(biblioteca, nombre exacto)` del material; sin distinguir mayúsculas. Exit 5 si no está."""
    buscado = nombre.casefold()
    parecidos: list[str] = []
    for lib in _elegir_biblioteca(tabla, biblioteca):
        for material in materiales_de(tabla, lib):
            if material.casefold() == buscado:
                return lib, material
            if buscado in material.casefold() and len(parecidos) < 10:
                parecidos.append(material)
    raise DocNoEncontrado(
        f"No existe el material {nombre!r}"
        + (f" en la biblioteca {biblioteca!r}" if biblioteca else "")
        + ": mirá `se material list`.",
        details={"parecidos": parecidos} if parecidos else None,
    )


def asignar(
    app: Any, selector: str | None, nombre: str, biblioteca: str | None = None
) -> dict[str, Any]:
    """Asigná un material al documento (no guarda). Devuelve el anterior y el nuevo."""
    nombre = validar_nombre(nombre)
    doc = documento(app, selector)
    exigir_tipo(doc, TIPOS_CON_MATERIAL, "material set")
    tabla = _tabla(app)
    lib, exacto = _buscar(tabla, nombre, biblioteca)
    anterior = _nombre_actual(tabla, doc)
    leer(lambda: tabla.ApplyMaterialToDoc(doc, exacto, lib))
    return {
        "material": _nombre_actual(tabla, doc),
        "biblioteca": lib,
        "anterior": anterior,
        "guardado": False,
    }


__all__ = ["TIPOS_CON_MATERIAL", "asignar", "bibliotecas", "listar", "obtener", "validar_nombre"]
