"""Chapa metálica: exportación del desarrollo (flat pattern) a DXF.

Las funciones reciben la `Application` ya verificada y no importan pywin32. La llamada COM y el
criterio de qué geometría usar están aislados en `_exportar_desarrollo` y `_tiene_desarrollo`.

Verificado en vivo (Solid Edge 2026 226.00.01.04, 2026-11-23): el desarrollo se crea por API con
`FlatPatternModels.Add(modelo)` y `FlatPatterns.Add(arista, cara, vértice)`; una chapa sincrónica
con un doblez (tab de 100x50x1 mm y una brida de 30 mm) da un DXF de 100 x 79.09 mm.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any

from se_cli.core import acceso, documentos, exportar
from se_cli.core.acceso import leer, opcional
from se_cli.core.constants import valor as constante
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado, ErrorCom, SoloLectura
from se_cli.core.exportar import Formato

TIPOS_CHAPA = ("sheetmetal", "syncsheetmetal")

CRITERIO_DE_CARA = "cara plana de mayor area"


# --- Llamadas COM aisladas (corregir acá si alguna falla en vivo) ---------------------------


def _tiene_desarrollo(doc: Any) -> bool:
    """Si la chapa ya tiene un flat pattern: `FlatPatternModels.Count > 0`."""
    cantidad = opcional(lambda: int(doc.FlatPatternModels.Count), 0)
    return bool(cantidad)


def _exportar_desarrollo(doc: Any, ruta: str) -> None:
    """`Models.SaveAsFlatDXFEx(FileName, Face, Edge, Vertex, UseFlatPatternModel)`.

    Criterio: se usa el flat pattern que ya existe en el documento (`UseFlatPatternModel=True`)
    y no se elige cara, arista ni vértice (`None`). Crear el desarrollo lo hace `--create`.
    """
    leer(lambda: doc.Models.SaveAsFlatDXFEx(ruta, None, None, None, True))


def _caras_planas(doc: Any) -> list[tuple[int, float, Any]]:
    """`(índice 1-based, área, cara)` de las caras planas del primer modelo."""
    modelo = leer(lambda: doc.Models.Item(1))
    caras = leer(lambda: modelo.Body.Faces(constante("igQueryAll")))
    plano = constante("igPlane")
    halladas: list[tuple[int, float, Any]] = []
    for indice in range(1, int(leer(lambda: caras.Count)) + 1):
        cara = leer(lambda i=indice: caras.Item(i))
        tipo = opcional(lambda cara=cara: int(cara.Geometry.Type))
        if tipo is not None and tipo != plano:
            continue
        area = float(opcional(lambda cara=cara: cara.Area, 0.0) or 0.0)
        halladas.append((indice, area, cara))
    return halladas


def elegir_cara(doc: Any) -> tuple[int, float, Any]:
    """Cara plana de mayor área (en un empate, la de menor índice): criterio determinista.

    En una chapa esa cara es una de las dos caras grandes de la pieza, así que el desarrollo
    sale del lado correcto sin importar cuántos dobleces haya.
    """
    caras = _caras_planas(doc)
    if not caras:
        raise ErrorCom("La chapa no tiene ninguna cara plana de la que sacar el desarrollo.")
    return max(caras, key=lambda c: (c[1], -c[0]))


def _crear_desarrollo(doc: Any) -> dict[str, Any]:
    """`FlatPatternModels.Add(modelo)` + `FlatPatterns.Add(arista, cara, vértice)`.

    La arista es la primera de la cara elegida y el vértice es su vértice inicial.
    """
    indice, area, cara = elegir_cara(doc)
    modelo = leer(lambda: doc.Models.Item(1))
    arista = leer(lambda: cara.Edges.Item(1))
    vertice = leer(lambda: arista.StartVertex)
    desarrollos = leer(lambda: doc.FlatPatternModels)
    nuevo = leer(lambda: desarrollos.Add(modelo))
    leer(lambda: nuevo.FlatPatterns.Add(arista, cara, vertice))
    return {"indice": indice, "area_si": area, "criterio": CRITERIO_DE_CARA}


def contar_entidades_dxf(ruta: str) -> int:
    """Entidades de la sección ENTITIES de un DXF de texto (0 si está vacío o no se lee)."""
    try:
        with open(ruta, encoding="utf-8", errors="ignore") as archivo:
            lineas = [linea.strip() for linea in archivo]
    except OSError:
        return 0
    cantidad = 0
    en_entidades = False
    previo_es_seccion = False
    for codigo, valor in zip(lineas[0::2], lineas[1::2], strict=False):
        if codigo == "2" and previo_es_seccion:
            en_entidades = valor == "ENTITIES"
        previo_es_seccion = codigo == "0" and valor == "SECTION"
        if codigo == "0" and valor == "ENDSEC":
            en_entidades = False
        elif codigo == "0" and en_entidades and valor != "SECTION":
            cantidad += 1
    return cantidad


def _exigir_entidades(ruta: str) -> None:
    if contar_entidades_dxf(ruta) == 0:
        raise ErrorCom(
            "Solid Edge escribió un DXF sin entidades: el desarrollo no se exportó.",
            details={"ruta": ruta},
        )


def _reabrir(app: Any, doc: Any, ruta: str) -> Any:
    """Guardá, cerrá y volvé a abrir la chapa (en la misma sesión el DXF puede salir vacío)."""
    leer(lambda: doc.Save())
    leer(lambda: doc.Close(False))
    return leer(lambda: app.Documents.Open(ruta))


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
    archivo: str | None,
    doc: str | None,
    out: str | None,
    sobrescribir: bool,
    crear: bool = False,
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
    descripcion: dict[str, Any] = {
        "accion": "sheetmetal.flat-dxf",
        "entrada": ruta or doc or "activo",
        "salida": salida,
        "overwrite": sobrescribir,
    }
    if crear:
        descripcion["create"] = True
    return descripcion


def _crear_y_reabrir(app: Any, doc: Any, nombre: str, out: str | None, sobrescribir: bool):
    """Precondiciones, desarrollo, guardado y reapertura. Devuelve `(doc_reabierto, cara)`."""
    origen = documentos.ruta_de(doc)
    if origen is None:
        raise ArgumentoInvalido(
            f"{nombre} nunca se guardó: --create guarda la chapa para poder exportar. "
            "Usá `se docs save-as <destino>` antes.",
            details={"documento": nombre},
        )
    if bool(leer(lambda: doc.ReadOnly)):
        raise SoloLectura(
            f"{nombre} está abierto como solo lectura: --create tiene que guardarlo.",
            details={"documento": nombre},
        )
    documentos.validar_destino(
        exportar.salida_individual(FORMATO_DESARROLLO, origen, out), sobrescribir
    )
    era_activo = documentos.es_activo(app, doc)
    previo = None if era_activo else documentos.documento_activo(app)
    cara = _crear_desarrollo(doc)
    reabierto = _reabrir(app, doc, origen)
    if era_activo:
        leer(lambda: reabierto.Activate())
    elif previo is not None:
        with contextlib.suppress(Exception):
            leer(lambda: previo.Activate())
    if not _tiene_desarrollo(reabierto):
        raise ErrorCom(
            "El desarrollo no quedó en el archivo guardado al reabrir la chapa.",
            details={"documento": nombre},
        )
    return reabierto, cara


PISTA_CREATE = (
    "Repetí el comando con --create: crea el desarrollo por API (cara plana de mayor área), "
    "guarda la chapa con cualquier cambio pendiente, la cierra, la reabre y exporta. Exige una "
    "chapa guardada en disco y no de solo lectura. Si no querés que se guarde, creá el desarrollo "
    "en Solid Edge (Herramientas > Desarrollo)."
)


def _sin_desarrollo(doc: Any, nombre: str) -> DocNoEncontrado:
    """Exit 5 con la pista de `--create` y si la chapa tiene cambios que `--create` guardaría.

    No se crea el desarrollo solo: `FlatPatternModels.Add` marca el documento como modificado
    (verificado en vivo, 2026-11-25), así que hacerlo sin pedirlo cambiaría la chapa del usuario.
    """
    return DocNoEncontrado(
        f"{nombre} no tiene desarrollo (flat pattern). Creálo en Solid Edge "
        "(Herramientas > Desarrollo) o repetí el comando con --create.",
        details={
            "documento": nombre,
            "hint": PISTA_CREATE,
            "cambios_pendientes": opcional(lambda: bool(doc.Dirty)),
        },
    )


def exportar_dxf(
    app: Any,
    archivo: str | None,
    selector: str | None,
    out: str | None,
    sobrescribir: bool,
    crear: bool = False,
) -> dict[str, Any]:
    """Exportá el desarrollo de una chapa a DXF. Sin flat pattern: exit 5 con la explicación.

    Con `crear`, una chapa sin desarrollo se lo crea por API (cara plana de mayor área), se guarda,
    se cierra y se reabre, y recién ahí se exporta. Exige una chapa guardada en disco y no de solo
    lectura (si no, exit 2 o 6 sin tocar nada). Una chapa que ya tiene desarrollo se exporta sin
    cambios (`desarrollo_creado: false`). Guardar incluye cualquier cambio pendiente de la chapa.
    """
    inicio = time.perf_counter()
    doc: Any = None
    abri_yo = False
    try:
        if archivo is not None:
            ruta_archivo = documentos.validar_ruta_existente(archivo)
            doc = documentos.buscar_abierto(app, ruta_archivo)
            if doc is None:
                doc = leer(lambda: app.Documents.Open(ruta_archivo))
                abri_yo = True
        else:
            _, doc = documentos.resolver(app, selector)

        nombre = str(leer(lambda: doc.Name))
        tipo = acceso.exigir_tipo(doc, TIPOS_CHAPA, "sheetmetal flat-dxf")
        extras: dict[str, Any] = {}
        if crear:
            extras = {"desarrollo_creado": False, "documento_guardado": False, "cara": None}
            if not _tiene_desarrollo(doc):
                doc, cara = _crear_y_reabrir(app, doc, nombre, out, sobrescribir)
                extras = {"desarrollo_creado": True, "documento_guardado": True, "cara": cara}
        if not _tiene_desarrollo(doc):
            raise _sin_desarrollo(doc, nombre)
        origen = documentos.ruta_de(doc)
        salida = documentos.validar_destino(
            exportar.salida_individual(FORMATO_DESARROLLO, origen, out), sobrescribir
        )
        tamano = exportar.escribir(
            doc, FORMATO_DESARROLLO, salida, sobrescribir, _exigir_entidades if crear else None
        )
        if crear:
            extras["entidades_dxf"] = contar_entidades_dxf(salida)
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
            **extras,
        }
    finally:
        if abri_yo and doc is not None:
            with contextlib.suppress(Exception):
                leer(lambda: doc.Close(False))


__all__ = [
    "CRITERIO_DE_CARA",
    "FORMATO_DESARROLLO",
    "contar_entidades_dxf",
    "elegir_cara",
    "exportar_dxf",
    "planificar",
]
