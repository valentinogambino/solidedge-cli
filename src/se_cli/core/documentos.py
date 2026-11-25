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
from pathlib import PureWindowsPath
from typing import Any, TypeVar

from se_cli.core import plazo
from se_cli.core.constants import DocumentTypeConstants
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    NoConectado,
    Ocupado,
    SeError,
    SoloLectura,
    TiempoAgotado,
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


def _sin_prefijo_largo(ruta: str) -> str:
    r"""Quitá el prefijo de ruta larga o de dispositivo (`\\?\` y `\\.\`); `UNC` vuelve a `\\`."""
    ruta = ruta.replace("/", "\\")
    if ruta.startswith(("\\\\?\\", "\\\\.\\")):
        ruta = ruta[4:]
        if ruta[:4].upper() == "UNC\\":
            ruta = "\\\\" + ruta[4:]
    return ruta


_RESERVADOS_WINDOWS = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"{base}{n}" for base in ("COM", "LPT") for n in "123456789¹²³"}
)


def es_nombre_reservado(nombre: str) -> bool:
    """Dice si `nombre` (un componente de ruta, no una ruta) es un dispositivo reservado de
    Windows. Usa `os.path.isreserved` (Python 3.13+) si existe; si no, una lista propia con el
    mismo criterio que Windows: sin distinguir mayúsculas, ignorando la extensión y los
    espacios o puntos finales (`NUL.txt`, `con .par` y `COM1.asm` son reservados)."""
    isreserved = getattr(os.path, "isreserved", None)
    if isreserved is not None:
        return bool(isreserved(nombre))
    return _reservado_por_lista(nombre)


def _reservado_por_lista(nombre: str) -> bool:
    base = nombre.partition(".")[0].rstrip(" ")
    return base.upper() in _RESERVADOS_WINDOWS


def validar_nombres_windows(ruta: str) -> None:
    r"""Rechazá (exit 2) nombres que Windows no admite: reservados (CON, NUL, COM1...), con
    caracteres prohibidos, terminados en punto o espacio, o de más de 255 caracteres.

    Se mira la ruta tal cual y ya absoluta: `abspath` convierte un `NUL` pelado en el
    dispositivo `\\.\NUL`, que ya no se vería como un nombre. La raíz (letra de unidad,
    recurso UNC) no se valida. Los dispositivos con prefijo (`\\.\NUL`) se rechazan.
    """
    for candidata in (ruta, ruta_absoluta(ruta)):
        pura = PureWindowsPath(_sin_prefijo_largo(candidata))
        for parte in pura.parts[1:] if pura.anchor else pura.parts:
            if parte in (".", ".."):
                continue  # navegación, no un nombre
            if (
                es_nombre_reservado(parte)
                or parte.endswith((".", " "))
                or len(parte.encode("utf-16-le", errors="surrogatepass")) > 510
                or any(c in '<>:"|?*' or ord(c) < 32 for c in parte)
            ):
                raise ArgumentoInvalido(
                    f"La ruta de destino contiene un nombre inválido en Windows: {parte!r}.",
                    details={"ruta": ruta_absoluta(ruta)},
                )


# Verificado en vivo (Solid Edge 226.00.01.04, 2026-11-25): `SaveCopyAs` y `SaveAs` fallan con una
# ruta de 260 caracteres o más (259 todavía se guarda), aunque la carpeta exista.
MAX_RUTA = 259


def exigir_ruta_corta(absoluta: str) -> None:
    """Exit 2 si la ruta absoluta supera lo que Solid Edge sabe guardar (`MAX_RUTA`)."""
    if len(absoluta) > MAX_RUTA:
        raise ArgumentoInvalido(
            f"La ruta de destino tiene {len(absoluta)} caracteres y Solid Edge no guarda en rutas "
            f"de {MAX_RUTA + 1} o más. Elegí una ruta más corta: {absoluta}",
            details={"ruta": absoluta, "largo": len(absoluta), "maximo": MAX_RUTA},
        )


def validar_destino(destino: str, sobrescribir: bool) -> str:
    """Ruta absoluta de destino para `save-as`.

    Si ya existe y no se pasó `--overwrite` da `SoloLectura` (exit 6): Solid Edge abriría un
    diálogo modal que `DisplayAlerts` no suprime. La carpeta tiene que existir.
    """
    validar_nombres_windows(destino)
    absoluta = ruta_absoluta(destino)
    exigir_ruta_corta(absoluta)
    if os.path.isdir(absoluta):
        raise ArgumentoInvalido(f"El destino es una carpeta: {absoluta}")
    if not os.path.isdir(os.path.dirname(absoluta)):
        raise ArgumentoInvalido(
            f"La carpeta de destino no existe: {os.path.dirname(absoluta)}",
            details={"ruta": absoluta},
        )
    exigir_destino_libre(absoluta, sobrescribir)
    return absoluta


def exigir_destino_libre(absoluta: str, sobrescribir: bool) -> bool:
    """True si el destino ya existe y se puede reemplazar; sin `sobrescribir` y ocupado, exit 6."""
    existe = os.path.lexists(absoluta)
    if existe and not sobrescribir:
        raise SoloLectura(
            f"Ya existe {absoluta}. Usá --overwrite para reemplazarlo.",
            details={"ruta": absoluta},
        )
    return existe


# Windows: ERROR_SHARING_VIOLATION y ERROR_LOCK_VIOLATION (otro proceso tiene el archivo abierto).
_WINERROR_EN_USO = frozenset({32, 33})

PISTA_EN_USO = (
    "Cerrá el archivo en el programa que lo tiene abierto (si es Solid Edge: `se docs close "
    "<nombre>`) o elegí otro destino."
)


def archivo_bloqueado(ruta: str, error: OSError) -> SoloLectura:
    """`SoloLectura` (exit 6) para un archivo que Windows no deja mover o reemplazar."""
    winerror = getattr(error, "winerror", None)
    en_uso = winerror in _WINERROR_EN_USO
    motivo = "el archivo está en uso por otro programa" if en_uso else "Windows negó el acceso"
    return SoloLectura(
        f"No se puede reemplazar {ruta}: {motivo}. El archivo original quedó como estaba.",
        details={
            "ruta": ruta,
            "motivo": "archivo_en_uso" if en_uso else "acceso_denegado",
            "winerror": winerror,
            "original_intacto": True,
            "hint": PISTA_EN_USO,
        },
    )


def apartar(ruta: str) -> str:
    """Mové un archivo existente a `<ruta>.se-<id>.bak` y devolvé esa ruta.

    Si Windows no lo deja (lo tiene abierto Solid Edge u otro programa) da `SoloLectura`
    (exit 6) sin haber tocado nada: verificado en vivo, `os.replace` da WinError 32.
    """
    apartado = f"{ruta}.se-{uuid.uuid4().hex[:8]}.bak"
    try:
        os.replace(ruta, apartado)
    except PermissionError as error:
        raise archivo_bloqueado(ruta, error) from error
    return apartado


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


def buscar_abierto(app: Any, ruta: str) -> Any | None:
    """Documento abierto con esa ruta completa, o None. No activa nada."""
    buscada = os.path.normcase(ruta_absoluta(ruta))
    for _, doc in _items(app):
        if os.path.normcase(_ruta_de(doc) or "") == buscada:
            return doc
    return None


def guardar_en(
    doc: Any, absoluta: str, sobrescribir: bool, verificar: Callable[[str], None] | None = None
) -> None:
    """`SaveAs` de `doc` a `absoluta`, apartando un archivo previo y restaurándolo si falla."""
    _guardar_en(doc, absoluta, sobrescribir, verificar)


def ruta_de(doc: Any) -> str | None:
    """Ruta completa del documento, o None si nunca se guardó."""
    return _ruta_de(doc)


def es_activo(app: Any, doc: Any) -> bool:
    """True si `doc` es el documento activo de la aplicación."""
    clave = _clave_del_activo(app)
    return clave is not None and _clave(doc) == clave


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

AVISO_SOLO_LECTURA = (
    "Solid Edge no permite abrir en solo lectura por API: `Documents.Open` no tiene ese flag "
    "(su segundo argumento es DocRelationAutoServer). El documento se abrió con acceso normal; "
    "solo queda en solo lectura si el archivo tiene el atributo de solo lectura de Windows."
)


def abrir(app: Any, ruta: str, solo_lectura: bool = False) -> dict[str, Any]:
    """Abrí un documento, o activalo si ya está abierto (`ya_abierto: true`)."""
    absoluta = validar_ruta_existente(ruta)
    buscada = os.path.normcase(absoluta)
    for indice, doc in _items(app):
        if os.path.normcase(_ruta_de(doc) or "") == buscada:
            _leer(doc.Activate)
            return {**descripcion_de(app, doc, indice), "ya_abierto": True}

    doc = _leer(lambda: app.Documents.Open(absoluta))
    datos = {**_describir_nuevo(app, doc), "ya_abierto": False}
    if solo_lectura and not datos["solo_lectura"]:
        datos["advertencia"] = AVISO_SOLO_LECTURA
    return datos


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
    progid = TIPOS_NUEVOS[clave]
    if plantilla:
        # `Documents.Add(ProgID, plantilla)`: con la ruta sola como primer argumento Solid Edge da
        # 0x80020009 (CO_E_CLASSSTRING), verificado en vivo el 2026-11-25.
        ruta = validar_ruta_existente(plantilla, "La plantilla")
        doc = _leer(lambda: app.Documents.Add(progid, ruta))
    else:
        doc = _leer(lambda: app.Documents.Add(progid))
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
    _exigir_no_abierto_en_otro(app, absoluta, doc)

    if os.path.normcase(_ruta_de(doc) or "") == os.path.normcase(absoluta):
        _exigir_escribible(doc)
        _leer(doc.Save)
    else:
        _guardar_en(doc, absoluta, sobrescribir)
    return {
        **descripcion_de(app, doc, indice),
        "guardado": True,
        "destino": absoluta,
        "existe": os.path.exists(absoluta),
    }


def _exigir_no_abierto_en_otro(app: Any, absoluta: str, doc: Any) -> None:
    """Exit 6 si el destino es otro documento abierto en Solid Edge (lo tiene bloqueado)."""
    buscada = os.path.normcase(absoluta)
    propia = _clave(doc)
    for indice, otro in _items(app):
        if os.path.normcase(_ruta_de(otro) or "") == buscada and _clave(otro) != propia:
            nombre = str(_leer(lambda otro=otro: otro.Name))
            raise SoloLectura(
                f"No se puede guardar en {absoluta}: ese archivo está abierto en Solid Edge "
                f"como {nombre}. El archivo original quedó como estaba.",
                details={
                    "ruta": absoluta,
                    "motivo": "archivo_en_uso",
                    "abierto_en_solid_edge": {"indice": indice, "nombre": nombre},
                    "original_intacto": True,
                    "hint": f"Cerralo antes (`se docs close {nombre}`) o elegí otro destino.",
                },
            )


@contextlib.contextmanager
def respaldo(ruta: str, sobrescribir: bool, *, limpiar_destino: bool = False):
    """Apartá el destino previo y conservalo si Solid Edge podría seguir escribiendo."""
    apartado = None
    with plazo.proteger_archivos():
        if exigir_destino_libre(ruta, sobrescribir):
            apartado = apartar(ruta)
            plazo.registrar_apartado(apartado)
    try:
        yield
    except TiempoAgotado as error:
        if apartado is not None:
            error.details["apartado"] = apartado
        raise
    except BaseException:
        with plazo.proteger_archivos():
            if limpiar_destino:
                with contextlib.suppress(OSError):
                    os.remove(ruta)
            if apartado is not None:
                os.replace(apartado, ruta)
            plazo.registrar_apartado(None)
        raise
    else:
        with plazo.proteger_archivos():
            if apartado is not None:
                with contextlib.suppress(OSError):
                    os.remove(apartado)
            plazo.registrar_apartado(None)


def _guardar_en(
    doc: Any, absoluta: str, sobrescribir: bool, verificar: Callable[[str], None] | None = None
) -> None:
    with respaldo(absoluta, sobrescribir):
        _leer(lambda: doc.SaveAs(absoluta))
        if verificar is not None:
            verificar(absoluta)


def _validar_cierre(guardar_: bool, descartar: bool) -> None:
    if guardar_ and descartar:
        raise ArgumentoInvalido("--save y --discard son excluyentes.")


def _cerrar_uno(doc: Any, guardar_: bool, descartar: bool) -> None:
    """Cerrá un documento ya validado. `Close` siempre lleva el argumento explícito."""
    sucio = bool(_leer(lambda: doc.Dirty))
    if sucio and guardar_:
        _leer(doc.Save)
    elif sucio and descartar:
        # `Dirty` es de solo lectura en SE 2026 (en vivo da E_FAIL): lo que evita el diálogo es
        # `DisplayAlerts = False` más `Close(False)`. Se intenta igual por si otra versión sí.
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
    "MAX_RUTA",
    "TIPOS_NUEVOS",
    "abrir",
    "activo",
    "apartar",
    "archivo_bloqueado",
    "buscar_abierto",
    "cerrar",
    "cerrar_todos",
    "documento_activo",
    "es_activo",
    "estado",
    "guardar",
    "guardar_como",
    "exigir_destino_libre",
    "exigir_ruta_corta",
    "guardar_en",
    "listar",
    "nombre_de_tipo",
    "nuevo",
    "resolver",
    "ruta_absoluta",
    "ruta_de",
    "salir",
    "validar_destino",
    "validar_nombres_windows",
    "validar_ruta_existente",
    "validar_tipo_nuevo",
]
