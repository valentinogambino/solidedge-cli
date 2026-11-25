"""Exportación por lotes: expande entradas, planifica salidas y exporta archivo por archivo.

Un archivo que falla no corta el lote. Los documentos que ya estaban abiertos se usan tal cual y
no se cierran; los que abre el lote se cierran sin guardar (`Close(False)`). Al terminar vuelve a
quedar activo el documento que lo estaba antes.

Sin pywin32: todo COM pasa por `core/exportar.py`, `core/documentos.py` y `core/acceso.py`.
"""

from __future__ import annotations

import contextlib
import glob
import os
import time
from dataclasses import dataclass
from typing import Any

from se_cli.core import acceso, documentos
from se_cli.core.acceso import leer
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    ErrorLote,
    NoConectado,
    SoloLectura,
    traducir,
)
from se_cli.core.exportar import (
    Formato,
    escribir,
    exigir_compatible,
    extras_de,
    nombre_de_salida,
    ventana_activa,
)

# Extensiones de documentos Solid Edge que `export` sabe recorrer en un lote y su tipo.
TIPO_POR_EXTENSION = {".par": "part", ".psm": "sheetmetal", ".asm": "assembly", ".dft": "draft"}


@dataclass(frozen=True)
class Item:
    """Una exportación planificada de un lote: archivo de entrada y su salida."""

    entrada: str
    salida: str


def _extensiones_compatibles(formato: Formato) -> set[str]:
    return {ext for ext, tipo in TIPO_POR_EXTENSION.items() if tipo in formato.tipos}


def _tiene_comodin(texto: str) -> bool:
    return any(c in texto for c in "*?[")


def _archivos_de_carpeta(carpeta: str, compatibles: set[str], recursivo: bool) -> list[str]:
    if recursivo:
        hallados = [
            os.path.join(raiz, nombre)
            for raiz, _, nombres in os.walk(carpeta)
            for nombre in nombres
        ]
    else:
        hallados = [
            os.path.join(carpeta, nombre)
            for nombre in os.listdir(carpeta)
            if os.path.isfile(os.path.join(carpeta, nombre))
        ]
    return sorted(h for h in hallados if os.path.splitext(h)[1].lower() in compatibles)


def expandir_entradas(entradas: list[str], formato: Formato, recursivo: bool) -> list[str]:
    """Archivos Solid Edge compatibles con `formato` que describen las entradas.

    Las expande Python porque el shell de Windows no expande globs. Un archivo explícito de otro
    tipo da exit 2 y uno inexistente exit 5; un glob o una carpeta se quedan con los archivos
    compatibles (sin ninguno, exit 5). Con `recursivo`, `**` en un glob y las subcarpetas cuentan.
    Sin duplicados, en el orden dado (cada glob o carpeta, alfabético).
    """
    compatibles = _extensiones_compatibles(formato)
    rutas: list[str] = []
    for entrada in entradas:
        if _tiene_comodin(entrada):
            hallados = sorted(glob.glob(entrada, recursive=recursivo))
            archivos = [
                h
                for h in hallados
                if os.path.isfile(h) and os.path.splitext(h)[1].lower() in compatibles
            ]
        elif os.path.isdir(entrada):
            archivos = _archivos_de_carpeta(entrada, compatibles, recursivo)
        elif os.path.isfile(entrada):
            if os.path.splitext(entrada)[1].lower() not in compatibles:
                raise ArgumentoInvalido(
                    f"{entrada} no se puede exportar a {formato.clave}: "
                    f"solo se aceptan {', '.join(sorted(compatibles))}.",
                    details={"entrada": entrada, "formato": formato.clave},
                )
            archivos = [entrada]
        else:
            raise DocNoEncontrado(f"No existe: {entrada}", details={"entrada": entrada})
        if not archivos:
            raise DocNoEncontrado(
                f"{entrada} no tiene archivos compatibles con {formato.clave} "
                f"({', '.join(sorted(compatibles))}).",
                details={"entrada": entrada},
            )
        rutas.extend(archivos)
    vistos: set[str] = set()
    unicas: list[str] = []
    for ruta in rutas:
        absoluta = documentos.ruta_absoluta(ruta)
        if os.path.normcase(absoluta) not in vistos:
            vistos.add(os.path.normcase(absoluta))
            unicas.append(absoluta)
    return unicas


def planificar(
    entradas: list[str], formato: Formato, out: str | None, recursivo: bool
) -> list[Item]:
    """Entradas → salidas de un lote, sin COM ni disco. `out` es una carpeta (se crea al correr).

    Dos entradas que dan la misma salida (mismo nombre en carpetas distintas con `--out`, o
    `A.par` y `A.psm` lado a lado) es exit 2: una pisaría a la otra.
    """
    carpeta = None
    if out is not None:
        documentos.validar_nombres_windows(out)
        carpeta = documentos.ruta_absoluta(out)
        if os.path.isfile(carpeta) or os.path.splitext(carpeta)[1].lower() in formato.extensiones:
            raise ArgumentoInvalido(
                f"En un lote --out tiene que ser una carpeta, no un archivo: {carpeta}"
            )
    items: list[Item] = []
    por_salida: dict[str, str] = {}
    for entrada in expandir_entradas(entradas, formato, recursivo):
        base = carpeta or os.path.dirname(entrada)
        salida = os.path.join(base, nombre_de_salida(formato, entrada))
        clave = os.path.normcase(salida)
        if clave in por_salida:
            raise ArgumentoInvalido(
                f"{por_salida[clave]} y {entrada} darían la misma salida: {salida}",
                details={"salida": salida},
            )
        por_salida[clave] = entrada
        items.append(Item(entrada, salida))
    return items


def _exportar_item(app: Any, item: Item, formato: Formato, sobrescribir: bool) -> dict[str, Any]:
    """Un archivo del lote: usa la instancia abierta o abre una y la cierra sin guardar."""
    inicio = time.perf_counter()
    resultado: dict[str, Any] = {"entrada": item.entrada, "salida": item.salida}
    doc = None
    abierto_por_el_lote = False
    try:
        if os.path.exists(item.salida) and not sobrescribir:
            raise SoloLectura(
                f"Ya existe {item.salida}. Usá --overwrite para reemplazarlo.",
                details={"ruta": item.salida},
            )
        doc = documentos.buscar_abierto(app, item.entrada)
        if doc is None:
            documentos.validar_ruta_existente(item.entrada)
            doc = leer(lambda: app.Documents.Open(item.entrada))
            abierto_por_el_lote = True
        exigir_compatible(formato, acceso.tipo_de(doc), os.path.basename(item.entrada))
        with ventana_activa(app, doc, formato):
            resultado["bytes"] = escribir(doc, formato, item.salida, sobrescribir)
        resultado["ok"] = True
    except Exception as error:  # noqa: BLE001 - un archivo que falla no corta el lote
        resultado["ok"] = False
        resultado["error"] = traducir(error).a_dict()
    finally:
        if abierto_por_el_lote and doc is not None:
            try:
                leer(lambda: doc.Close(False))
            except Exception as error:  # noqa: BLE001
                resultado["aviso"] = f"No se pudo cerrar el documento: {traducir(error).mensaje}"
        resultado["duracion_s"] = round(time.perf_counter() - inicio, 3)
    return resultado


def _no_intentado(item: Item) -> dict[str, Any]:
    error = NoConectado("No se intentó: Solid Edge dejó de estar disponible.")
    return {
        "entrada": item.entrada,
        "salida": item.salida,
        "ok": False,
        "error": error.a_dict(),
        "duracion_s": 0.0,
    }


def exportar(
    app: Any, items: list[Item], formato: Formato, out: str | None, sobrescribir: bool
) -> dict[str, Any]:
    """Exportá cada archivo del lote. Si alguno falla, levanta `ErrorLote` (exit 1).

    Los resultados completos (`resultados` y `resumen`) van en `data` si todo salió bien y en
    `error.details` si no.
    """
    carpeta = documentos.ruta_absoluta(out) if out is not None else None
    if carpeta is not None:
        documentos.validar_nombres_windows(out)
        try:
            os.makedirs(carpeta, exist_ok=True)
        except OSError as error:
            raise ArgumentoInvalido(f"No se pudo crear la carpeta {carpeta}: {error}") from error
    activo_previo = documentos.documento_activo(app)
    resultados: list[dict[str, Any]] = []
    try:
        for item in items:
            resultado = _exportar_item(app, item, formato, sobrescribir)
            resultados.append(resultado)
            if not resultado["ok"] and resultado["error"]["code"] == "no_conectado":
                resultados.extend(_no_intentado(resto) for resto in items[len(resultados) :])
                break
    finally:
        if activo_previo is not None:
            with contextlib.suppress(Exception):
                actual = documentos.documento_activo(app)
                if actual is None or actual is not activo_previo:
                    leer(activo_previo.Activate)
    cantidad_ok = sum(1 for r in resultados if r["ok"])
    data: dict[str, Any] = {
        "formato": formato.clave,
        "salida": carpeta,
        "resultados": resultados,
        "resumen": {
            "total": len(resultados),
            "ok": cantidad_ok,
            "fallidos": len(resultados) - cantidad_ok,
        },
        **extras_de(formato),
    }
    if cantidad_ok != len(resultados):
        fallidos = [r for r in resultados if not r["ok"]]
        detalle = "; ".join(
            f"{os.path.basename(r['entrada'])}: {r['error']['message']}" for r in fallidos[:3]
        )
        mas = f" (y {len(fallidos) - 3} más)" if len(fallidos) > 3 else ""
        raise ErrorLote(
            f"Fallaron {len(fallidos)} de {len(resultados)} exportaciones. {detalle}{mas}",
            details=data,
        )
    return data


__all__ = ["Item", "exportar", "expandir_entradas", "planificar"]
