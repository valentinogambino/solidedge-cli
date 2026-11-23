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
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from se_cli.core import acceso, documentos
from se_cli.core.acceso import leer
from se_cli.core.errors import ArgumentoInvalido, ErrorCom, SoloLectura

TIPOS_SOLIDOS = ("part", "sheetmetal", "assembly")
TIPOS_DRAFT = ("draft",)
TIPOS_CON_VENTANA = (*TIPOS_SOLIDOS, "draft")

# Tamaño en píxeles de `View.SaveAsImage`.
ANCHO_PNG = 1920
ALTO_PNG = 1080

NOTA_MARCA_DE_AGUA = (
    "En Community Edition la salida puede llevar marca de agua; todavía no se validó en vivo."
)

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


def _exportar_dxf(doc: Any, ruta: str) -> None:
    """DXF de un Draft: `SaveCopyAs` con extensión `.dxf`."""
    leer(lambda: doc.SaveCopyAs(ruta))


def _exportar_png(doc: Any, ruta: str) -> None:
    """PNG de la ventana del documento.

    Pieza, chapa y ensamble: `Windows.Item(1).View.SaveAsImage`. El `SheetWindow` de un Draft no
    tiene `View`: ahí `SaveAsImage` y `Fit` son de la ventana (verificado en vivo).
    """
    ventana = leer(lambda: doc.Windows.Item(1))
    destino = acceso.opcional(lambda: ventana.View) or ventana
    # Un documento recién abierto no está encuadrado: sin `Fit` el modelo sale chico y corrido.
    acceso.opcional(destino.Fit)
    leer(lambda: destino.SaveAsImage(ruta, ANCHO_PNG, ALTO_PNG))


# --- Formatos --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Formato:
    """Un formato de salida: extensiones, tipos de documento que lo admiten y su exportador."""

    clave: str
    extension: str
    extensiones: tuple[str, ...]
    tipos: tuple[str, ...]
    exportar: Callable[[Any, str], None]
    # La exportación sale de la vista de la ventana: el documento tiene que estar activo.
    requiere_ventana: bool = False
    marca_de_agua: bool = False


FORMATOS: dict[str, Formato] = {
    "step": Formato("step", ".stp", (".stp", ".step"), TIPOS_SOLIDOS, _exportar_step),
    "stl": Formato("stl", ".stl", (".stl",), TIPOS_SOLIDOS, _exportar_stl),
    "x_t": Formato("x_t", ".x_t", (".x_t",), TIPOS_SOLIDOS, _exportar_x_t),
    "igs": Formato("igs", ".igs", (".igs", ".iges"), TIPOS_SOLIDOS, _exportar_igs),
    "pdf": Formato("pdf", ".pdf", (".pdf",), TIPOS_DRAFT, _exportar_pdf, marca_de_agua=True),
    "dxf": Formato("dxf", ".dxf", (".dxf",), TIPOS_DRAFT, _exportar_dxf, marca_de_agua=True),
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


def escribir(doc: Any, formato: Formato, ruta: str, sobrescribir: bool) -> int:
    """Exportá `doc` a `ruta` y devolvé los bytes escritos.

    Nunca le pasa a Solid Edge una ruta que existe: con `sobrescribir` aparta el archivo previo y
    lo restaura si la exportación falla o no deja un archivo con contenido. Sin `sobrescribir` y
    con el destino ocupado da exit 6.
    """
    if os.path.exists(ruta) and not sobrescribir:
        raise SoloLectura(
            f"Ya existe {ruta}. Usá --overwrite para reemplazarlo.", details={"ruta": ruta}
        )
    apartado: str | None = None
    if os.path.exists(ruta):
        apartado = f"{ruta}.se-{uuid.uuid4().hex[:8]}.bak"
        os.replace(ruta, apartado)
    try:
        formato.exportar(doc, ruta)
        tamano = verificar_archivo(ruta)
    except BaseException:
        with contextlib.suppress(OSError):
            if os.path.exists(ruta):
                os.remove(ruta)
        if apartado is not None:
            os.replace(apartado, ruta)
        raise
    if apartado is not None:
        with contextlib.suppress(OSError):
            os.remove(apartado)
    return tamano


def extras_de(formato: Formato) -> dict[str, Any]:
    """Campos adicionales del resultado según el formato (aviso de marca de agua)."""
    if formato.marca_de_agua:
        return {"marca_de_agua": "sin verificar", "nota": NOTA_MARCA_DE_AGUA}
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
    with ventana_activa(app, doc, formato):
        tamano = escribir(doc, formato, salida, sobrescribir)
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
    }


__all__ = [
    "ALIAS_DE_FORMATO",
    "FORMATOS",
    "Formato",
    "escribir",
    "exigir_compatible",
    "exportar_individual",
    "formato_de",
    "nombre_de_salida",
    "salida_individual",
    "tipo_base",
    "verificar_archivo",
    "ventana_activa",
]
