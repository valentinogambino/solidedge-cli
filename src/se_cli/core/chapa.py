"""Chapa metálica: exportación del desarrollo (flat pattern) a DXF.

Las funciones reciben la `Application` ya verificada y no importan pywin32. La llamada COM y el
criterio de qué geometría usar están aislados en `_exportar_desarrollo` y `_tiene_desarrollo`.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any

from se_cli.core import acceso, documentos, exportar
from se_cli.core.acceso import leer, opcional
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado
from se_cli.core.exportar import Formato

TIPOS_CHAPA = ("sheetmetal", "syncsheetmetal")


# --- Llamadas COM aisladas (corregir acá si alguna falla en vivo) ---------------------------


def _tiene_desarrollo(doc: Any) -> bool:
    """Si la chapa ya tiene un flat pattern: `FlatPatternModels.Count > 0`."""
    cantidad = opcional(lambda: int(doc.FlatPatternModels.Count), 0)
    return bool(cantidad)


def _exportar_desarrollo(doc: Any, ruta: str) -> None:
    """`Models.SaveAsFlatDXFEx(FileName, Face, Edge, Vertex, UseFlatPatternModel)`.

    Criterio: se usa el flat pattern que ya existe en el documento (`UseFlatPatternModel=True`)
    y no se elige cara, arista ni vértice (`None`). Generar el desarrollo desde una cara de
    referencia necesita elegir geometría y no se hace desde la CLI.
    """
    leer(lambda: doc.Models.SaveAsFlatDXFEx(ruta, None, None, None, True))


FORMATO_DESARROLLO = Formato(
    "dxf",
    ".dxf",
    (".dxf",),
    TIPOS_CHAPA,
    _exportar_desarrollo,
    marca_de_agua=True,
)


# --- Planificación y ejecución ---------------------------------------------------------------


def planificar(
    archivo: str | None, doc: str | None, out: str | None, sobrescribir: bool
) -> dict[str, Any]:
    """Validá los argumentos sin COM. Devuelve la descripción de la acción para `--dry-run`."""
    if archivo is not None and doc is not None:
        raise ArgumentoInvalido("Pasá un archivo o --doc, no los dos.")
    ruta = None
    if archivo is not None:
        ruta = documentos.validar_ruta_existente(archivo)
        if os.path.splitext(ruta)[1].lower() != ".psm":
            raise ArgumentoInvalido(f"Tiene que ser una chapa (.psm): {ruta}")
    salida = None
    if out is not None and not (out.endswith(("/", "\\")) or os.path.isdir(out)):
        salida = documentos.validar_destino(
            exportar.salida_individual(FORMATO_DESARROLLO, None, out), sobrescribir
        )
    elif out is None and ruta is not None:
        salida = documentos.validar_destino(
            exportar.salida_individual(FORMATO_DESARROLLO, ruta, None), sobrescribir
        )
    return {
        "accion": "sheetmetal.flat-dxf",
        "entrada": ruta or doc or "activo",
        "salida": salida,
        "overwrite": sobrescribir,
    }


def exportar_dxf(
    app: Any, archivo: str | None, selector: str | None, out: str | None, sobrescribir: bool
) -> dict[str, Any]:
    """Exportá el desarrollo de una chapa a DXF. Sin flat pattern: exit 5 con la explicación."""
    inicio = time.perf_counter()
    abierto_por_mi: Any = None
    try:
        if archivo is not None:
            ruta_archivo = documentos.validar_ruta_existente(archivo)
            doc = documentos.buscar_abierto(app, ruta_archivo)
            if doc is None:
                doc = leer(lambda: app.Documents.Open(ruta_archivo))
                abierto_por_mi = doc
        else:
            _, doc = documentos.resolver(app, selector)

        nombre = str(leer(lambda: doc.Name))
        tipo = acceso.exigir_tipo(doc, TIPOS_CHAPA, "sheetmetal flat-dxf")
        if not _tiene_desarrollo(doc):
            raise DocNoEncontrado(
                f"{nombre} no tiene desarrollo (flat pattern). Creálo en Solid Edge "
                "(Herramientas > Desarrollo) y repetí el comando.",
                details={"documento": nombre},
            )
        origen = documentos.ruta_de(doc)
        salida = documentos.validar_destino(
            exportar.salida_individual(FORMATO_DESARROLLO, origen, out), sobrescribir
        )
        tamano = exportar.escribir(doc, FORMATO_DESARROLLO, salida, sobrescribir)
        return {
            "entrada": origen or nombre,
            "documento": nombre,
            "tipo": tipo,
            "formato": "dxf",
            "salida": salida,
            "ok": True,
            "bytes": tamano,
            "duracion_s": round(time.perf_counter() - inicio, 3),
            **exportar.extras_de(FORMATO_DESARROLLO),
        }
    finally:
        if abierto_por_mi is not None:
            with contextlib.suppress(Exception):
                leer(lambda: abierto_por_mi.Close(False))


__all__ = ["FORMATO_DESARROLLO", "exportar_dxf", "planificar"]
