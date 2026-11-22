"""Helpers comunes de acceso COM para los módulos de datos del modelo.

Sin pywin32: trabajan con late binding sobre objetos que ya entregó `Sesion.llamar`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from se_cli.core import documentos
from se_cli.core.errors import ArgumentoInvalido, NoConectado, Ocupado
from se_cli.core.retry import reintentar

T = TypeVar("T")


def leer(fn: Callable[[], T]) -> T:
    """Leé o llamá algo de COM reintentando si Solid Edge está ocupado."""
    return reintentar(fn)


def opcional(fn: Callable[[], T], por_defecto: T | None = None) -> T | None:
    """Como `leer`, pero un miembro que no existe o falla da `por_defecto`.

    Sirve para campos que la API no ofrece en todos los objetos. "Ocupado" y "desconectado"
    no se tragan: esos errores son del comando entero, no del campo.
    """
    try:
        return leer(fn)
    except (Ocupado, NoConectado):
        raise
    except Exception:
        return por_defecto


def items(coleccion: Any) -> Iterator[Any]:
    """Recorré una colección COM (`Count` + `Item(i)`, 1-based)."""
    cantidad = int(leer(lambda: coleccion.Count))
    for i in range(1, cantidad + 1):
        yield leer(lambda i=i: coleccion.Item(i))


def documento(app: Any, selector: str | None) -> Any:
    """Documento según el selector de `se docs` (índice, nombre, ruta o activo)."""
    return documentos.resolver(app, selector)[1]


def tipo_de(doc: Any) -> str:
    """Nombre legible del tipo del documento (`part`, `assembly`, ...)."""
    return documentos.nombre_de_tipo(leer(lambda: doc.Type))


def exigir_tipo(doc: Any, permitidos: tuple[str, ...], comando: str) -> str:
    """Devolvé el tipo del documento o `ArgumentoInvalido` (exit 2) si `comando` no lo admite."""
    tipo = tipo_de(doc)
    if tipo not in permitidos:
        raise ArgumentoInvalido(
            f"`{comando}` no se puede usar con un documento de tipo {tipo}: "
            f"solo {', '.join(permitidos)}.",
            details={"tipo": tipo, "permitidos": list(permitidos)},
        )
    return tipo


__all__ = ["documento", "exigir_tipo", "items", "leer", "opcional", "tipo_de"]
