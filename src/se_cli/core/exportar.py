"""Exportación de documentos a formatos de intercambio (STEP, STL, Parasolid, IGES...).

Todos los formatos salen por `SaveCopyAs` del documento abierto: a diferencia de `SaveAs`, no
reapunta el documento vivo a la copia. La llamada COM concreta de cada formato vive en su propia
función `_exportar_<formato>` para poder corregirla por separado cuando se pruebe en vivo.

Solid Edge abre un diálogo modal ("el archivo existe, ¿reemplazar?") si la ruta de salida ya
existe, y `DisplayAlerts` no lo suprime. Por eso el destino se valida antes y, con `--overwrite`,
el archivo anterior se aparta, y se restaura si la exportación falla.

Las funciones reciben la `Application` (ya verificada por `Sesion.llamar`) y no importan pywin32.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from se_cli.core import acceso, documentos
from se_cli.core.acceso import leer, opcional
from se_cli.core.errors import (
    ArgumentoInvalido,
    ErrorCom,
    NoSoportado,
    SeError,
    formatear_hresult,
    scode_de,
    traducir,
)

TIPOS_SOLIDOS = ("part", "sheetmetal", "assembly")
TIPOS_DRAFT = ("draft",)
TIPOS_CON_VENTANA = (*TIPOS_SOLIDOS, "draft")

# Tamaño en píxeles de `View.SaveAsImage` (16:9). En un Draft se conserva la proporción de la
# hoja: con un tamaño fijo 16:9 la hoja (A3/A4 son 1,414:1) sale recortada.
ANCHO_PNG = 1920
ALTO_PNG = 1080

# Verificado en vivo (Solid Edge 2026 Community Edition 226.00.01.04, 2026-11-23): el PDF lleva la
# leyenda "Solid Edge Community Edition" dibujada con contornos (no es texto: no se encuentra
# buscando cadenas); el DXF, ni de un Draft ni de un desarrollo, trae esa leyenda.
MARCA_DE_AGUA = {
    "pdf": (
        "presente",
        "Community Edition agrega la leyenda 'Solid Edge Community Edition' en gris claro, abajo "
        "a la izquierda de cada hoja. Va dibujada con trazos, no como texto.",
    ),
    "dxf": ("ausente", "El DXF no trae la leyenda de Community Edition."),
}

# Un documento síncrono se exporta igual que su versión ordenada.
_TIPO_BASE = {"syncpart": "part", "syncsheetmetal": "sheetmetal", "syncassembly": "assembly"}


# --- Llamadas COM por formato (corregir acá si alguna falla en vivo) -----------------------


def _exportar_step(doc: Any, ruta: str) -> None:
    """STEP: `SaveCopyAs` con extensión `.stp`. Sin opciones (se usan las del usuario)."""
    leer(lambda: doc.SaveCopyAs(ruta))


def _exportar_stl(doc: Any, ruta: str) -> None:
    """STL: `SaveCopyAs` con extensión `.stl`. Sin opciones de calidad de malla."""
    leer(lambda: doc.SaveCopyAs(ruta))


def _exportar_x_t(doc: Any, ruta: str) -> None:
    """Parasolid: `SaveCopyAs` con extensión `.x_t`."""
    leer(lambda: doc.SaveCopyAs(ruta))


def _exportar_igs(doc: Any, ruta: str) -> None:
    """IGES: `SaveCopyAs` con extensión `.igs`."""
    leer(lambda: doc.SaveCopyAs(ruta))


def _exportar_pdf(doc: Any, ruta: str) -> None:
    """PDF de un Draft: `SaveCopyAs` con extensión `.pdf` (hojas y calidad por defecto)."""
    leer(lambda: doc.SaveCopyAs(ruta))


E_ACCESSDENIED = 0x80070005


def _acceso_denegado(error: Exception) -> bool:
    """Si es un `com_error` cuyo scode (el error real tras `DISP_E_EXCEPTION`) es E_ACCESSDENIED."""
    return scode_de(error) == E_ACCESSDENIED or getattr(error, "hresult", 0) & 0xFFFFFFFF == (
        E_ACCESSDENIED
    )


def _exportar_dxf(doc: Any, ruta: str) -> dict[str, Any] | None:
    """DXF de un Draft: `SaveCopyAs` con extensión `.dxf`.

    Verificado en vivo (2026-11-26): funciona, pero la primera exportación DXF de una sesión de
    Solid Edge falló una vez con un modal "This is a read-only file. Choose another name." y
    `0x80020009` con scode E_ACCESSDENIED, sin causa determinada y sin repetirse. Con ese error se
    reintenta una vez; si persiste, exit 6 (`causa: acceso_denegado`). Devuelve `{"reintento":
    True}` si hizo falta reintentar.
    """
    try:
        leer(lambda: doc.SaveCopyAs(ruta))
        return None
    except Exception as error:
        if not _acceso_denegado(error):
            raise
        primero = error
    # Un intento a medias no puede quedar: Solid Edge no debe encontrar un archivo en la ruta.
    with contextlib.suppress(OSError):
        os.remove(ruta)
    try:
        leer(lambda: doc.SaveCopyAs(ruta))
    except Exception as error:
        if not _acceso_denegado(error):
            raise
        with contextlib.suppress(OSError):
            os.remove(ruta)
        traducido = traducir(error)
        raise NoSoportado(
            "Solid Edge rechazó la escritura del DXF (acceso denegado, E_ACCESSDENIED) también "
            "al reintentar. Es un fallo intermitente de Solid Edge: reintentar el comando suele "
            "funcionar.",
            hresult=traducido.hresult,
            details={
                **(traducido.details or {}),
                "causa": "acceso_denegado",
                "scode": formatear_hresult(E_ACCESSDENIED),
                "ruta": ruta,
                "formato": "dxf",
                "reintentos": 1,
            },
        ) from primero
    return {"reintento": True}


def _tamano_png(doc: Any) -> tuple[int, int]:
    """`(ancho, alto)` en píxeles: 16:9 salvo en un Draft, donde sigue la proporción de la hoja."""

    def medir() -> tuple[float, float]:
        setup = doc.ActiveSheet.SheetSetup
        return float(setup.SheetWidth), float(setup.SheetHeight)

    hoja = acceso.opcional(medir)
    if hoja is None or hoja[0] <= 0 or hoja[1] <= 0:
        return ANCHO_PNG, ALTO_PNG
    ancho_hoja, alto_hoja = hoja
    lado = max(ANCHO_PNG, ALTO_PNG)
    if ancho_hoja >= alto_hoja:
        return lado, max(1, round(lado * alto_hoja / ancho_hoja))
    return max(1, round(lado * ancho_hoja / alto_hoja)), lado


def _exportar_png(doc: Any, ruta: str) -> None:
    """PNG de la ventana del documento.

    Pieza, chapa y ensamble: `Windows.Item(1).View.SaveAsImage`. El `SheetWindow` de un Draft no
    tiene `View`: ahí `SaveAsImage` y `Fit` son de la ventana (verificado en vivo).
    """
    ventana = leer(lambda: doc.Windows.Item(1))
    destino = acceso.opcional(lambda: ventana.View) or ventana
    # Un documento recién abierto no está encuadrado: sin `Fit` el modelo sale chico y corrido.
    acceso.opcional(destino.Fit)
    ancho, alto = _tamano_png(doc)
    leer(lambda: destino.SaveAsImage(ruta, ancho, alto))


# --- Formatos --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Formato:
    """Un formato de salida: extensiones, tipos de documento que lo admiten y su exportador."""

    clave: str
    extension: str
    extensiones: tuple[str, ...]
    tipos: tuple[str, ...]
    exportar: Callable[[Any, str], dict[str, Any] | None]
    # La exportación sale de la vista de la ventana: el documento tiene que estar activo.
    requiere_ventana: bool = False
    marca_de_agua: bool = False


FORMATOS: dict[str, Formato] = {
    "step": Formato("step", ".stp", (".stp", ".step"), TIPOS_SOLIDOS, _exportar_step),
    "stl": Formato("stl", ".stl", (".stl",), TIPOS_SOLIDOS, _exportar_stl),
    "x_t": Formato("x_t", ".x_t", (".x_t",), TIPOS_SOLIDOS, _exportar_x_t),
    "igs": Formato("igs", ".igs", (".igs", ".iges"), TIPOS_SOLIDOS, _exportar_igs),
    # El PDF y el DXF de un Draft también salen de la ventana: con otro documento activo,
    # `SaveCopyAs` exporta el contenido del activo en la hoja del pedido (verificado en vivo,
    # 2026-11-26: el PDF de un A3 trajo el rótulo y las vistas del A4 activo).
    "pdf": Formato(
        "pdf",
        ".pdf",
        (".pdf",),
        TIPOS_DRAFT,
        _exportar_pdf,
        requiere_ventana=True,
        marca_de_agua=True,
    ),
    "dxf": Formato(
        "dxf",
        ".dxf",
        (".dxf",),
        TIPOS_DRAFT,
        _exportar_dxf,
        requiere_ventana=True,
        marca_de_agua=True,
    ),
    "png": Formato(
        "png", ".png", (".png",), TIPOS_CON_VENTANA, _exportar_png, requiere_ventana=True
    ),
}

ALIAS_DE_FORMATO = {"stp": "step", "iges": "igs", "parasolid": "x_t"}


def formato_de(texto: str) -> Formato:
    """Formato por nombre o alias, sin distinguir mayúsculas; inválido da exit 2."""
    clave = texto.strip().lower().lstrip(".")
    clave = ALIAS_DE_FORMATO.get(clave, clave)
    if clave not in FORMATOS:
        raise ArgumentoInvalido(
            f"Formato inválido: {texto!r}. Usá {', '.join(FORMATOS)} "
            f"(alias: {', '.join(ALIAS_DE_FORMATO)}).",
            details={"validos": list(FORMATOS), "alias": dict(ALIAS_DE_FORMATO)},
        )
    return FORMATOS[clave]


def tipo_base(tipo: str) -> str:
    """Tipo de documento sin la variante síncrona (`syncpart` se trata como `part`)."""
    return _TIPO_BASE.get(tipo, tipo)


def exigir_compatible(formato: Formato, tipo: str, que: str | None = None) -> None:
    """Exit 2 si el tipo de documento no se puede exportar a `formato`."""
    base = tipo_base(tipo)
    if base not in formato.tipos:
        quien = f"{que} (tipo {tipo})" if que else f"un documento de tipo {tipo}"
        raise ArgumentoInvalido(
            f"No se puede exportar {quien} a {formato.clave}: "
            f"ese formato admite solo {', '.join(formato.tipos)}.",
            details={"tipo": tipo, "formato": formato.clave, "permitidos": list(formato.tipos)},
        )


# --- Rutas de salida (sin COM) ---------------------------------------------------------------


def nombre_de_salida(formato: Formato, origen: str) -> str:
    """Nombre de archivo de salida: el del origen con la extensión del formato."""
    return os.path.splitext(os.path.basename(origen))[0] + formato.extension


def salida_individual(formato: Formato, origen: str | None, out: str | None) -> str:
    """Ruta de salida de la exportación de un documento.

    Sin `out`: al lado del documento. Con `out` carpeta (existente o terminada en separador):
    dentro de ella con el nombre del documento. Con `out` archivo: esa ruta, sin extensión se le
    pone la del formato y con otra extensión da exit 2. Un documento nunca guardado exige `out`
    con ruta de archivo.
    """
    if out is None:
        if origen is None:
            raise ArgumentoInvalido(
                "El documento nunca se guardó: pasá --out <archivo> para elegir la salida."
            )
        return documentos.ruta_absoluta(os.path.splitext(origen)[0] + formato.extension)
    if out.endswith(("/", "\\")) or os.path.isdir(out):
        if origen is None:
            raise ArgumentoInvalido(
                "El documento nunca se guardó: --out tiene que ser una ruta de archivo."
            )
        return documentos.ruta_absoluta(os.path.join(out, nombre_de_salida(formato, origen)))
    absoluta = documentos.ruta_absoluta(out)
    sufijo = os.path.splitext(absoluta)[1].lower()
    if not sufijo:
        return absoluta + formato.extension
    if sufijo not in formato.extensiones:
        raise ArgumentoInvalido(
            f"La extensión {sufijo} no corresponde a {formato.clave}: "
            f"usá {', '.join(formato.extensiones)}.",
            details={"formato": formato.clave, "extensiones": list(formato.extensiones)},
        )
    return absoluta


# --- Escritura -------------------------------------------------------------------------------


def verificar_archivo(ruta: str) -> int:
    """Tamaño del archivo escrito; sin archivo o vacío es un error."""
    if not os.path.isfile(ruta):
        raise ErrorCom(f"Solid Edge no escribió el archivo: {ruta}", details={"ruta": ruta})
    tamano = os.path.getsize(ruta)
    if tamano <= 0:
        raise ErrorCom(
            f"Solid Edge dejó el archivo vacío (0 bytes): {ruta}", details={"ruta": ruta}
        )
    return tamano


# Verificado en vivo (Solid Edge 226.00.01.04, 2026-11-25): sin geometría, STL, Parasolid e IGES de
# una pieza o chapa fallan con `0x80020009` (scode `E_FAIL`, `E_ABORT` o `E_POINTER`); STEP sí se
# escribe. En un ensamble vacío fallan STL e IGES, y Parasolid sale.
FORMATOS_QUE_EXIGEN_CUERPO = frozenset({"stl", "x_t", "igs"})


def documento_vacio(doc: Any) -> bool | None:
    """True si la pieza, chapa o ensamble no tiene geometría; None si no se pudo saber."""
    base = tipo_base(acceso.tipo_de(doc))
    if base in ("part", "sheetmetal"):
        coleccion = opcional(lambda: doc.Models)
    elif base == "assembly":
        coleccion = opcional(lambda: doc.Occurrences)
    else:
        return None
    if coleccion is None:
        return None
    cantidad = opcional(lambda: coleccion.Count)
    return None if cantidad is None else int(cantidad) == 0


def explicar_fallo(doc: Any, formato: Formato, ruta: str, error: Exception) -> SeError | None:
    """Mensaje claro para un error COM de `SaveCopyAs`, o None si no hay nada que agregar.

    Un documento sin geometría exportado a STL, Parasolid o IGES da `NoSoportado` (exit 6). Un
    error sin descripción de Solid Edge (solo `0x80020009`) conserva el HRESULT y dice qué revisar.
    Lo demás (ocupado, desconectado, errores con texto propio) sigue como estaba.
    """
    traducido = traducir(error)
    if type(traducido) is not ErrorCom:
        return None
    detalles = {**(traducido.details or {}), "ruta": ruta, "formato": formato.clave}
    if formato.clave in FORMATOS_QUE_EXIGEN_CUERPO and documento_vacio(doc):
        detalles["causa"] = "documento_vacio"
        return NoSoportado(
            f"No se puede exportar a {formato.clave}: el documento no tiene geometría. Creá al "
            "menos una operación antes (STEP sí admite un documento vacío).",
            hresult=traducido.hresult,
            details=detalles,
        )
    if "excepinfo" not in detalles:
        return ErrorCom(
            f"Solid Edge no pudo exportar a {formato.clave} y no dio detalles. Revisá que la "
            f"ruta tenga menos de {documentos.MAX_RUTA + 1} caracteres, que la carpeta permita "
            "escribir, que el documento tenga contenido para ese formato y que Solid Edge no "
            "tenga un diálogo abierto.",
            hresult=traducido.hresult,
            details=detalles,
        )
    return None


def escribir(
    doc: Any,
    formato: Formato,
    ruta: str,
    sobrescribir: bool,
    verificar: Callable[[str], None] | None = None,
    extras: dict[str, Any] | None = None,
) -> int:
    """Exportá `doc` a `ruta` y devolvé los bytes escritos.

    Nunca le pasa a Solid Edge una ruta que existe: con `sobrescribir` aparta el archivo previo y
    lo restaura si la exportación falla o no deja un archivo con contenido. Sin `sobrescribir` y
    con el destino ocupado da exit 6. `verificar(ruta)` corre sobre el archivo escrito (si
    levanta, se lo deshace igual que a un archivo vacío). Si el exportador informa algo más (por
    ejemplo `reintento`), se vuelca en `extras`.
    """
    documentos.exigir_ruta_corta(ruta)
    with documentos.respaldo(ruta, sobrescribir, limpiar_destino=True):
        try:
            adicional = formato.exportar(doc, ruta)
            if adicional and extras is not None:
                extras.update(adicional)
        except Exception as error:
            explicado = explicar_fallo(doc, formato, ruta, error)
            if explicado is None:
                raise
            raise explicado from error
        tamano = verificar_archivo(ruta)
        if verificar is not None:
            verificar(ruta)
    return tamano


def extras_de(formato: Formato) -> dict[str, Any]:
    """Campos adicionales del resultado según el formato (aviso de marca de agua)."""
    if formato.marca_de_agua:
        estado, nota = MARCA_DE_AGUA[formato.clave]
        return {"marca_de_agua": estado, "nota": nota}
    return {}


@contextlib.contextmanager
def ventana_activa(app: Any, doc: Any, formato: Formato) -> Iterator[None]:
    """Si el formato sale de la ventana, activá `doc` y devolvé la activación al terminar."""
    if not formato.requiere_ventana:
        yield
        return
    previo = documentos.documento_activo(app)
    leer(doc.Activate)
    try:
        yield
    finally:
        if previo is not None and previo is not doc:
            with contextlib.suppress(Exception):
                leer(previo.Activate)


def exportar_individual(
    app: Any, selector: str | None, formato: Formato, out: str | None, sobrescribir: bool
) -> dict[str, Any]:
    """Exportá el documento activo (o el del selector) sin cerrarlo ni cambiarlo."""
    _, doc = documentos.resolver(app, selector)
    inicio = time.perf_counter()
    nombre = str(leer(lambda: doc.Name))
    tipo = acceso.tipo_de(doc)
    exigir_compatible(formato, tipo, nombre)
    origen = documentos.ruta_de(doc)
    salida = documentos.validar_destino(salida_individual(formato, origen, out), sobrescribir)
    extras: dict[str, Any] = {}
    with ventana_activa(app, doc, formato):
        tamano = escribir(doc, formato, salida, sobrescribir, extras=extras)
    return {
        "entrada": origen or nombre,
        "documento": nombre,
        "tipo": tipo,
        "formato": formato.clave,
        "salida": salida,
        "ok": True,
        "bytes": tamano,
        "duracion_s": round(time.perf_counter() - inicio, 3),
        **extras_de(formato),
        **extras,
    }


__all__ = [
    "ALIAS_DE_FORMATO",
    "FORMATOS",
    "Formato",
    "documento_vacio",
    "escribir",
    "exigir_compatible",
    "explicar_fallo",
    "exportar_individual",
    "formato_de",
    "nombre_de_salida",
    "salida_individual",
    "tipo_base",
    "verificar_archivo",
    "ventana_activa",
]
