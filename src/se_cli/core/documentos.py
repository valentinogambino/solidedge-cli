"""Operaciones sobre documentos de Solid Edge.

Las funciones reciben la `Application` (ya verificada por `Sesion.llamar`) y devuelven datos
planos. No importan pywin32. Cada llamada COM suelta se reintenta con `reintentar` por si
Solid Edge está ocupado; ninguna operación de guardado o cierre se repite entera.

Las validaciones que no necesitan COM (`validar_*`) están separadas para que `--dry-run`
pueda correrlas sin conectarse.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from se_cli.core.constants import DocumentAccess, DocumentTypeConstants
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    NoConectado,
    Ocupado,
    SeError,
    SoloLectura,
    traducir,
)
from se_cli.core.retry import reintentar

T = TypeVar("T")

TIPOS_NUEVOS: dict[str, str] = {
    "part": "SolidEdge.PartDocument",
    "assembly": "SolidEdge.AssemblyDocument",
    "draft": "SolidEdge.DraftDocument",
    "sheetmetal": "SolidEdge.SheetMetalDocument",
    "weldment": "SolidEdge.WeldmentDocument",
}

_NOMBRES_DE_TIPO: dict[int, str] = {
    DocumentTypeConstants.igPartDocument: "part",
    DocumentTypeConstants.igAssemblyDocument: "assembly",
    DocumentTypeConstants.igDraftDocument: "draft",
    DocumentTypeConstants.igSheetMetalDocument: "sheetmetal",
    DocumentTypeConstants.igWeldmentDocument: "weldment",
    DocumentTypeConstants.igWeldmentAssemblyDocument: "weldmentassembly",
    DocumentTypeConstants.igSyncPartDocument: "syncpart",
    DocumentTypeConstants.igSyncSheetMetalDocument: "syncsheetmetal",
    DocumentTypeConstants.igSyncAssemblyDocument: "syncassembly",
    DocumentTypeConstants.igAssemblyViewerDocument: "assemblyviewer",
    DocumentTypeConstants.igPartViewerDocument: "partviewer",
    DocumentTypeConstants.igDraftViewerDocument: "draftviewer",
}


def _leer(fn: Callable[[], T]) -> T:
    """Leé o llamá una cosa de COM reintentando si Solid Edge está ocupado."""
    return reintentar(fn)


def nombre_de_tipo(valor: Any) -> str:
    """Nombre legible de `doc.Type`; lo que no se reconoce es `desconocido`."""
    try:
        return _NOMBRES_DE_TIPO.get(int(valor), "desconocido")
    except (TypeError, ValueError):
        return "desconocido"


# --- Validaciones locales (sin COM) -------------------------------------------------------


def ruta_absoluta(ruta: str | os.PathLike[str]) -> str:
    """Ruta absoluta y normalizada, que es lo único que se le pasa a COM."""
    return os.path.normpath(os.path.abspath(os.fspath(ruta)))


def validar_ruta_existente(ruta: str, que: str = "El archivo") -> str:
    """Devolvé la ruta absoluta de un archivo que existe, o `DocNoEncontrado` (exit 5)."""
    absoluta = ruta_absoluta(ruta)
    if not os.path.isfile(absoluta):
        raise DocNoEncontrado(f"{que} no existe: {absoluta}", details={"ruta": absoluta})
    return absoluta


def validar_tipo_nuevo(tipo: str, plantilla: str | None = None) -> str:
    """ProgID para `Documents.Add` según el tipo; tipo inválido da exit 2.

    Un weldment sin plantilla se rechaza: sin ella Solid Edge busca una plantilla por
    defecto que puede no estar instalada y abre un diálogo modal que cuelga la sesión.
    """
    clave = tipo.strip().lower()
    if clave not in TIPOS_NUEVOS:
        raise ArgumentoInvalido(
            f"Tipo de documento inválido: {tipo!r}. Usá {', '.join(TIPOS_NUEVOS)}.",
            details={"validos": list(TIPOS_NUEVOS)},
        )
    if clave == "weldment" and not plantilla:
        raise ArgumentoInvalido(
            "Un weldment necesita --template <ruta a una plantilla .pwd>: sin plantilla Solid "
            "Edge puede abrir un diálogo modal."
        )
    return clave


def validar_destino(destino: str, sobrescribir: bool) -> str:
    """Ruta absoluta de destino para `save-as`.

    Si ya existe y no se pasó `--overwrite` da `SoloLectura` (exit 6): Solid Edge abriría un
    diálogo modal que `DisplayAlerts` no suprime. La carpeta tiene que existir.
    """
    absoluta = ruta_absoluta(destino)
    if os.path.isdir(absoluta):
        raise ArgumentoInvalido(f"El destino es una carpeta: {absoluta}")
    if not os.path.isdir(os.path.dirname(absoluta)):
        raise ArgumentoInvalido(
            f"La carpeta de destino no existe: {os.path.dirname(absoluta)}",
            details={"ruta": absoluta},
        )
    if os.path.exists(absoluta) and not sobrescribir:
        raise SoloLectura(
            f"Ya existe {absoluta}. Usá --overwrite para reemplazarlo.",
            details={"ruta": absoluta},
        )
    return absoluta


# --- Lectura -------------------------------------------------------------------------------


def _ruta_de(doc: Any) -> str | None:
    """Ruta completa del documento, o None si nunca se guardó (`FullName` no es absoluta)."""
    texto = str(_leer(lambda: doc.FullName) or "")
    return texto if os.path.isabs(texto) else None


def documento_activo(app: Any) -> Any | None:
    """Objeto COM del documento activo, o None si no hay."""
    try:
        return _leer(lambda: app.ActiveDocument)
    except Ocupado:
        raise
    except Exception:
        return None


def ruta_de(doc: Any) -> str | None:
    """Ruta completa del documento, o None si nunca se guardó."""
    return _ruta_de(doc)


def _clave(doc: Any) -> tuple[str, str]:
    return (
        os.path.normcase(str(_leer(lambda: doc.FullName) or "")),
        str(_leer(lambda: doc.Name) or "").casefold(),
    )


def _clave_del_activo(app: Any) -> tuple[str, str] | None:
    """Clave del documento activo, o None si no hay (COM levanta o devuelve nada)."""
    try:
        doc = _leer(lambda: app.ActiveDocument)
    except Ocupado:
        raise
    except Exception:
        return None
    return None if doc is None else _clave(doc)


def _describir(doc: Any, indice: int, clave_activo: tuple[str, str] | None) -> dict[str, Any]:
    return {
        "indice": indice,
        "nombre": str(_leer(lambda: doc.Name)),
        "ruta": _ruta_de(doc),
        "tipo": nombre_de_tipo(_leer(lambda: doc.Type)),
        "modificado": bool(_leer(lambda: doc.Dirty)),
        "activo": clave_activo is not None and _clave(doc) == clave_activo,
        "solo_lectura": bool(_leer(lambda: doc.ReadOnly)),
    }


def _items(app: Any) -> list[tuple[int, Any]]:
    cantidad = int(_leer(lambda: app.Documents.Count))
    return [(i, _leer(lambda i=i: app.Documents.Item(i))) for i in range(1, cantidad + 1)]


def listar(app: Any) -> list[dict[str, Any]]:
    """Documentos abiertos con `{indice, nombre, ruta, tipo, modificado, activo, solo_lectura}`."""
    activo = _clave_del_activo(app)
    return [_describir(doc, i, activo) for i, doc in _items(app)]


def descripcion_de(app: Any, doc: Any, indice: int) -> dict[str, Any]:
    """Descripción de un documento ya resuelto."""
    return _describir(doc, indice, _clave_del_activo(app))


def activo(app: Any) -> dict[str, Any]:
    """Documento activo, o `DocNoEncontrado` (exit 5) si no hay ninguno."""
    indice, doc = resolver(app, None)
    return descripcion_de(app, doc, indice)


def estado(app: Any) -> dict[str, Any]:
    """Datos de `se status` ya conectado: versión, nombre, visibilidad y documentos."""
    clave = _clave_del_activo(app)
    nombre_activo = None
    if clave is not None:
        doc = _leer(lambda: app.ActiveDocument)
        nombre_activo = str(_leer(lambda: doc.Name))
    visible = _leer(lambda: app.Visible)
    return {
        "conectado": True,
        "version": str(_leer(lambda: app.Version)),
        "nombre": str(_leer(lambda: app.Name)),
        "visible": None if visible is None else bool(visible),
        "documentos": int(_leer(lambda: app.Documents.Count)),
        "activo": nombre_activo,
    }


def resolver(app: Any, selector: str | None) -> tuple[int, Any]:
    """Devolvé `(indice, doc)` según el selector.

    Sin selector, el documento activo. Si no, un índice (1-based, como `docs list`), un
    nombre exacto sin distinguir mayúsculas o una ruta completa. Ambiguo o inexistente da
    `DocNoEncontrado` (exit 5).
    """
    items = _items(app)
    if selector is None:
        clave = _clave_del_activo(app)
        if clave is None:
            raise DocNoEncontrado("No hay ningún documento activo.")
        for i, doc in items:
            if _clave(doc) == clave:
                return i, doc
        raise DocNoEncontrado("No se encontró el documento activo entre los abiertos.")

    texto = selector.strip()
    if texto.isdigit():
        indice = int(texto)
        if 1 <= indice <= len(items):
            return items[indice - 1]
        raise DocNoEncontrado(
            f"No hay un documento con índice {indice} (hay {len(items)}).",
            details={"selector": selector, "documentos": len(items)},
        )

    candidatos = _por_ruta(items, texto) or _por_nombre(items, texto)
    if not candidatos:
        raise DocNoEncontrado(
            f"No hay un documento abierto que coincida con {selector!r}.",
            details={"selector": selector},
        )
    if len(candidatos) > 1:
        raise DocNoEncontrado(
            f"El selector {selector!r} es ambiguo: coincide con {len(candidatos)} documentos. "
            "Usá el índice o la ruta completa.",
            details={"selector": selector, "indices": [i for i, _ in candidatos]},
        )
    return candidatos[0]


def _por_ruta(items: list[tuple[int, Any]], texto: str) -> list[tuple[int, Any]]:
    if not (os.path.isabs(texto) or os.sep in texto or "/" in texto):
        return []
    buscada = os.path.normcase(ruta_absoluta(texto))
    return [(i, d) for i, d in items if os.path.normcase(_ruta_de(d) or "") == buscada]


def _por_nombre(items: list[tuple[int, Any]], texto: str) -> list[tuple[int, Any]]:
    buscado = texto.casefold()
    return [(i, d) for i, d in items if str(_leer(lambda d=d: d.Name)).casefold() == buscado]


# --- Escritura -----------------------------------------------------------------------------

# Flag de `Documents.Open` para abrir en solo lectura: se asume `DocumentAccess.igReadOnly`.
# Validar en vivo (ver el informe de F2).
FLAG_ABRIR_SOLO_LECTURA = int(DocumentAccess.igReadOnly)


def abrir(app: Any, ruta: str, solo_lectura: bool = False) -> dict[str, Any]:
    """Abrí un documento, o activalo si ya está abierto (`ya_abierto: true`)."""
    absoluta = validar_ruta_existente(ruta)
    buscada = os.path.normcase(absoluta)
    for indice, doc in _items(app):
        if os.path.normcase(_ruta_de(doc) or "") == buscada:
            _leer(doc.Activate)
            return {**descripcion_de(app, doc, indice), "ya_abierto": True}

    if solo_lectura:
        doc = _leer(lambda: app.Documents.Open(absoluta, FLAG_ABRIR_SOLO_LECTURA))
    else:
        doc = _leer(lambda: app.Documents.Open(absoluta))
    return {**_describir_nuevo(app, doc), "ya_abierto": False}


def _describir_nuevo(app: Any, doc: Any) -> dict[str, Any]:
    """Describí un documento recién abierto o creado, buscando su índice entre los abiertos."""
    clave = _clave(doc)
    for indice, otro in _items(app):
        if _clave(otro) == clave:
            return descripcion_de(app, otro, indice)
    return {**_describir(doc, 0, _clave_del_activo(app))}


def nuevo(app: Any, tipo: str, plantilla: str | None = None) -> dict[str, Any]:
    """Creá un documento del tipo dado, con la plantilla indicada si hay."""
    clave = validar_tipo_nuevo(tipo, plantilla)
    if plantilla:
        argumento = validar_ruta_existente(plantilla, "La plantilla")
    else:
        argumento = TIPOS_NUEVOS[clave]
    doc = _leer(lambda: app.Documents.Add(argumento))
    return _describir_nuevo(app, doc)


def guardar(app: Any, selector: str | None = None) -> dict[str, Any]:
    """Guardá el documento activo o el indicado; sin ruta pide `save-as` (exit 2)."""
    indice, doc = resolver(app, selector)
    if _ruta_de(doc) is None:
        raise ArgumentoInvalido(
            f"{_leer(lambda: doc.Name)} nunca se guardó: usá `se docs save-as <destino>`.",
            details={"indice": indice},
        )
    _exigir_escribible(doc)
    _leer(doc.Save)
    return {**descripcion_de(app, doc, indice), "guardado": True}


def _exigir_escribible(doc: Any) -> None:
    if bool(_leer(lambda: doc.ReadOnly)):
        raise SoloLectura(
            f"{_leer(lambda: doc.Name)} está abierto como solo lectura: usá `save-as`."
        )


def guardar_como(
    app: Any, destino: str, selector: str | None = None, sobrescribir: bool = False
) -> dict[str, Any]:
    """Guardá el documento en `destino`. No pisa un archivo existente sin `sobrescribir`.

    Si hay que reemplazar un archivo, se aparta antes y se restaura si el guardado falla.
    """
    absoluta = validar_destino(destino, sobrescribir)
    indice, doc = resolver(app, selector)

    if os.path.normcase(_ruta_de(doc) or "") == os.path.normcase(absoluta):
        _exigir_escribible(doc)
        _leer(doc.Save)
    else:
        _guardar_en(doc, absoluta)
    return {
        **descripcion_de(app, doc, indice),
        "guardado": True,
        "destino": absoluta,
        "existe": os.path.exists(absoluta),
    }


def _guardar_en(doc: Any, absoluta: str) -> None:
    apartado: str | None = None
    if os.path.exists(absoluta):
        apartado = f"{absoluta}.se-{uuid.uuid4().hex[:8]}.bak"
        os.replace(absoluta, apartado)
    try:
        _leer(lambda: doc.SaveAs(absoluta))
    except BaseException:
        if apartado is not None:
            os.replace(apartado, absoluta)
        raise
    if apartado is not None:
        with contextlib.suppress(OSError):
            os.remove(apartado)


def _validar_cierre(guardar_: bool, descartar: bool) -> None:
    if guardar_ and descartar:
        raise ArgumentoInvalido("--save y --discard son excluyentes.")


def _cerrar_uno(doc: Any, guardar_: bool, descartar: bool) -> None:
    """Cerrá un documento ya validado. `Close` siempre lleva el argumento explícito."""
    sucio = bool(_leer(lambda: doc.Dirty))
    if sucio and guardar_:
        _leer(doc.Save)
    elif sucio and descartar:
        # Limpiar `Dirty` evita que Solid Edge pregunte; si no se puede, `Close(False)` decide.
        with contextlib.suppress(Exception):
            doc.Dirty = False
    _leer(lambda: doc.Close(False))


def cerrar(
    app: Any, selector: str | None = None, guardar_: bool = False, descartar: bool = False
) -> dict[str, Any]:
    """Cerrá el documento activo o el indicado.

    Con cambios sin guardar exige `guardar_` o `descartar`: si no, `SoloLectura` (exit 6) y
    no se cierra nada.
    """
    _validar_cierre(guardar_, descartar)
    indice, doc = resolver(app, selector)
    descripcion = descripcion_de(app, doc, indice)
    if descripcion["modificado"] and not (guardar_ or descartar):
        raise SoloLectura(
            f"{descripcion['nombre']} tiene cambios sin guardar. "
            "Usá --save para guardarlos o --discard para descartarlos.",
            details={"documento": descripcion["nombre"]},
        )
    if descripcion["modificado"] and guardar_ and descripcion["ruta"] is None:
        raise ArgumentoInvalido(
            f"{descripcion['nombre']} nunca se guardó: usá `se docs save-as <destino>` antes.",
        )
    if descripcion["modificado"] and guardar_:
        _exigir_escribible(doc)
    _cerrar_uno(doc, guardar_, descartar)
    return {
        "cerrado": True,
        "documento": descripcion["nombre"],
        "guardado": bool(guardar_ and descripcion["modificado"]),
        "descartado": bool(descartar and descripcion["modificado"]),
    }


def cerrar_todos(app: Any, guardar_: bool = False, descartar: bool = False) -> dict[str, Any]:
    """Cerrá todos los documentos. Si alguno tiene cambios y no hay `--save`/`--discard`,
    no se cierra ninguno (exit 6)."""
    _validar_cierre(guardar_, descartar)
    lista = listar(app)
    sucios = [d for d in lista if d["modificado"]]
    if sucios and not (guardar_ or descartar):
        raise SoloLectura(
            "Hay documentos con cambios sin guardar: "
            + ", ".join(d["nombre"] for d in sucios)
            + ". Usá --save o --discard.",
            details={"documentos": [d["nombre"] for d in sucios]},
        )
    if guardar_:
        sin_ruta = [d["nombre"] for d in sucios if d["ruta"] is None]
        if sin_ruta:
            raise ArgumentoInvalido(
                "Documentos que nunca se guardaron: "
                + ", ".join(sin_ruta)
                + ". Usá save-as antes.",
                details={"documentos": sin_ruta},
            )
        for _, doc in _items(app):
            if bool(_leer(lambda doc=doc: doc.Dirty)):
                _exigir_escribible(doc)
    cerrados: list[str] = []
    for _, doc in reversed(_items(app)):
        nombre = str(_leer(lambda doc=doc: doc.Name))
        _cerrar_uno(doc, guardar_, descartar)
        cerrados.append(nombre)
    return {"cerrados": cerrados, "cantidad": len(cerrados)}


def salir(app: Any, descartar: bool = False) -> dict[str, Any]:
    """Cerrá Solid Edge. Con cambios sin guardar se niega (exit 6) salvo `descartar`."""
    sucios = [d for d in listar(app) if d["modificado"]]
    if sucios and not descartar:
        raise SoloLectura(
            "Hay documentos con cambios sin guardar: "
            + ", ".join(d["nombre"] for d in sucios)
            + ". Guardalos o repetí con --discard.",
            details={"documentos": [d["nombre"] for d in sucios]},
        )
    previo = _leer(lambda: app.DisplayAlerts)
    _leer(lambda: setattr(app, "DisplayAlerts", False))
    if sucios:
        for _, doc in _items(app):
            with contextlib.suppress(Exception):
                doc.Dirty = False
    try:
        _leer(app.Quit)
    except Exception as error:
        traducido: SeError = traducir(error)
        if isinstance(traducido, NoConectado):
            # Una desconexión justo al salir es lo esperado: Solid Edge ya no está.
            return {"cerrada": True, "descartados": [d["nombre"] for d in sucios]}
        with contextlib.suppress(Exception):
            _leer(lambda: setattr(app, "DisplayAlerts", previo))
        raise
    return {"cerrada": True, "descartados": [d["nombre"] for d in sucios]}


__all__ = [
    "TIPOS_NUEVOS",
    "abrir",
    "activo",
    "cerrar",
    "cerrar_todos",
    "documento_activo",
    "estado",
    "guardar",
    "guardar_como",
    "listar",
    "nombre_de_tipo",
    "nuevo",
    "resolver",
    "ruta_absoluta",
    "ruta_de",
    "salir",
    "validar_destino",
    "validar_ruta_existente",
    "validar_tipo_nuevo",
]
