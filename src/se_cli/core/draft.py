"""Creación de un Draft (plano) a partir de un modelo: `se draft from-part`.

Crea un Draft nuevo, enlaza el modelo, coloca las vistas distribuidas en la hoja (`core/vistas.py`),
guarda y, si se pide, exporta el PDF. Nunca cierra ni modifica el modelo fuente: si hubo que
abrirlo (solo para medirlo con `--scale auto`), se cierra sin guardar.

Las llamadas COM que dependen de la versión de Solid Edge (hoja, vistas, caja del modelo) están
en funciones chicas y aisladas para corregirlas cuando se prueben en vivo. Las funciones reciben
la `Application` ya verificada y no importan pywin32.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from typing import Any

from se_cli.core import acceso, documentos, exportar, vistas
from se_cli.core.acceso import leer, opcional
from se_cli.core.constants import PaperSizeConstants
from se_cli.core.errors import ArgumentoInvalido
from se_cli.core.lote import TIPO_POR_EXTENSION

PROGID_DRAFT = "SolidEdge.DraftDocument"

# `DrawingViews.Add*View(From, Orientation, Scale, x, y, ViewType)` según el tipo de modelo.
METODO_DE_VISTA = {
    "part": "AddPartView",
    "sheetmetal": "AddSheetMetalView",
    "assembly": "AddAssemblyView",
}
# `ViewType` de las tres: vista de diseño (no simplificada).
VISTA_DE_DISENO = 0


# --- Llamadas COM aisladas (corregir acá si alguna falla en vivo) ---------------------------


def _fijar_hoja(draft: Any, nombre: str) -> None:
    """Hoja activa en tamaño ISO apaisado: `SheetSetup.SheetSizeOption` (`PaperSizeConstants`)."""
    setup = leer(lambda: draft.ActiveSheet.SheetSetup)
    papel = int(getattr(PaperSizeConstants, f"igIso{nombre}Wide"))
    leer(lambda: setattr(setup, "SheetSizeOption", papel))


def _fijar_fondo(draft: Any, nombre: str) -> str | None:
    """Poné como fondo de la hoja el de su tamaño (`A3-Sheet`): marco y cuadro de rotulación.

    La plantilla ISO trae fondos `A4-Sheet` a `A1-Sheet` y arranca con el de A2: cambiar solo
    `SheetSizeOption` deja el marco y el cuadro de A2 recortados en el PDF (verificado en vivo).
    Devuelve el nombre del fondo, o None si la plantilla no tiene uno para ese tamaño.
    """

    def poner() -> str:
        fondo = f"{nombre}-Sheet"
        hojas = draft.Sections.BackgroundSection.Sheets
        draft.ActiveSheet.Background = hojas.Item(fondo)
        return fondo

    return opcional(poner)


def _leer_hoja(draft: Any) -> tuple[float, float] | None:
    """`(ancho, alto)` de la hoja activa por `SheetSetup.SheetWidth/SheetHeight`, o None."""

    def medir() -> tuple[float, float]:
        setup = draft.ActiveSheet.SheetSetup
        return float(setup.SheetWidth), float(setup.SheetHeight)

    medida = opcional(medir)
    if medida is None or medida[0] <= 0 or medida[1] <= 0:
        return None
    return medida


def _nuevo_draft(app: Any, plantilla: str | None) -> Any:
    """`Documents.Add(ProgID[, plantilla])`: la plantilla va como segundo argumento.

    Verificado en vivo (2026-11-25): `Documents.Add(ruta_de_plantilla)` da 0x80020009
    (CO_E_CLASSSTRING); `Add("SolidEdge.DraftDocument", ruta)` abre la plantilla.
    """
    if plantilla:
        return leer(lambda: app.Documents.Add(PROGID_DRAFT, plantilla))
    return leer(lambda: app.Documents.Add(PROGID_DRAFT))


def _enlazar(draft: Any, ruta: str) -> Any:
    """`ModelLinks.Add(ruta)`: el enlace que reciben las vistas."""
    return leer(lambda: draft.ModelLinks.Add(ruta))


def _vistas_de_la_hoja(draft: Any) -> Any:
    """`ActiveSheet.DrawingViews` (late binding: gen_py lo enlaza mal)."""
    return leer(lambda: draft.ActiveSheet.DrawingViews)


def _agregar_vista(
    coleccion: Any, metodo: str, enlace: Any, orientacion: int, factor: float, x: float, y: float
) -> None:
    leer(lambda: getattr(coleccion, metodo)(enlace, orientacion, factor, x, y, VISTA_DE_DISENO))


def _caja_del_modelo(doc: Any, tipo: str) -> tuple[float, float, float] | None:
    """Dimensiones `(dx, dy, dz)` en metros del modelo abierto, o None si la API no las da.

    Pieza y chapa: `Models.Item(1).Body.GetRange(min, max)` (buffers `[in,out]` que se leen del
    retorno). Ensamble: unión de `GetRangeBox` de cada ocurrencia.
    """

    def de_cuerpo() -> tuple[tuple[float, ...], tuple[float, ...]]:
        cuerpo = doc.Models.Item(1).Body
        minimo, maximo = cuerpo.GetRange([0.0] * 3, [0.0] * 3)
        return tuple(minimo), tuple(maximo)

    def de_ensamble() -> tuple[tuple[float, ...], tuple[float, ...]]:
        minimos: list[tuple[float, ...]] = []
        maximos: list[tuple[float, ...]] = []
        for ocurrencia in acceso.items(doc.Occurrences):
            minimo, maximo = ocurrencia.GetRangeBox([0.0] * 3, [0.0] * 3)
            minimos.append(tuple(minimo))
            maximos.append(tuple(maximo))
        if not minimos:
            raise ValueError("ensamble sin ocurrencias")
        return (
            tuple(min(m[i] for m in minimos) for i in range(3)),
            tuple(max(m[i] for m in maximos) for i in range(3)),
        )

    rango = opcional(de_ensamble if tipo == "assembly" else de_cuerpo)
    if rango is None:
        return None
    try:
        dx, dy, dz = (float(rango[1][i]) - float(rango[0][i]) for i in range(3))
    except (TypeError, ValueError, IndexError):
        return None
    return (dx, dy, dz) if min(dx, dy, dz) >= 0 else None


# --- Planificación (sin COM) -----------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """Todo lo que `from-part` decide antes de tocar Solid Edge."""

    modelo: str
    tipo: str
    draft: str
    pdf: str | None
    vistas: list[str]
    factor: float | None  # None = auto
    hoja: str | None
    plantilla: str | None

    def a_dict(self) -> dict[str, Any]:
        return {
            "accion": "draft.from-part",
            "modelo": self.modelo,
            "draft": self.draft,
            "pdf": self.pdf,
            "vistas": list(self.vistas),
            "escala": "auto" if self.factor is None else vistas.nombre_de_escala(self.factor),
            "hoja": self.hoja,
            "plantilla": self.plantilla,
        }


def planificar(
    modelo: str,
    out: str | None,
    nombres_de_vistas: str | None,
    escala: str,
    hoja: str | None,
    plantilla: str | None,
    pdf: bool,
    sobrescribir: bool,
) -> Plan:
    """Validá los argumentos de `from-part` sin tocar COM ni disco (salvo leer rutas)."""
    lista = vistas.parsear_vistas(nombres_de_vistas)
    factor = vistas.parsear_escala(escala)
    nombre_hoja = vistas.parsear_hoja(hoja)
    ruta_modelo = documentos.validar_ruta_existente(modelo, "El modelo")
    tipo = TIPO_POR_EXTENSION.get(os.path.splitext(ruta_modelo)[1].lower())
    if tipo not in METODO_DE_VISTA:
        raise ArgumentoInvalido(
            f"El modelo tiene que ser .par, .psm o .asm: {ruta_modelo}",
            details={"modelo": ruta_modelo},
        )
    ruta_plantilla = None
    if plantilla:
        ruta_plantilla = documentos.validar_ruta_existente(plantilla, "La plantilla")

    if out is None:
        destino = os.path.splitext(ruta_modelo)[0] + ".dft"
    else:
        destino = documentos.ruta_absoluta(out)
        if os.path.isdir(destino):
            destino = os.path.join(destino, os.path.splitext(os.path.basename(ruta_modelo))[0])
        if not os.path.splitext(destino)[1]:
            destino += ".dft"
        elif os.path.splitext(destino)[1].lower() != ".dft":
            raise ArgumentoInvalido(f"--out tiene que ser un archivo .dft: {destino}")
    destino = documentos.validar_destino(destino, sobrescribir)
    ruta_pdf = None
    if pdf:
        ruta_pdf = documentos.validar_destino(os.path.splitext(destino)[0] + ".pdf", sobrescribir)
    return Plan(ruta_modelo, tipo, destino, ruta_pdf, lista, factor, nombre_hoja, ruta_plantilla)


# --- Ejecución -------------------------------------------------------------------------------


def _medida_de_hoja(draft: Any, pedida: str | None) -> tuple[dict[str, Any], tuple[float, float]]:
    """Tamaño de hoja para el layout y su descripción para el resultado."""
    if pedida is not None:
        _fijar_hoja(draft, pedida)
        fondo = _fijar_fondo(draft, pedida)
        ancho, alto = vistas.HOJAS[pedida]
        info = {"nombre": pedida, "ancho": ancho, "alto": alto, "origen": "solicitada"}
        info["fondo"] = fondo
        return info, (ancho, alto)
    leida = _leer_hoja(draft)
    if leida is not None:
        return {"nombre": None, "ancho": leida[0], "alto": leida[1], "origen": "plantilla"}, leida
    ancho, alto = vistas.HOJAS[vistas.HOJA_POR_DEFECTO]
    return {
        "nombre": None,
        "ancho": ancho,
        "alto": alto,
        "origen": f"supuesta ({vistas.HOJA_POR_DEFECTO})",
    }, (ancho, alto)


def crear(app: Any, plan: Plan, sobrescribir: bool, mantener_abierto: bool) -> dict[str, Any]:
    """Armá el Draft del plan. El modelo fuente no se cierra si ya estaba abierto ni se modifica."""
    activo_previo = documentos.documento_activo(app)
    modelo_abierto_por_mi: Any = None
    draft: Any = None
    guardado = False
    try:
        tipo = plan.tipo
        caja = None
        if plan.factor is None:
            doc_modelo = documentos.buscar_abierto(app, plan.modelo)
            if doc_modelo is None:
                doc_modelo = leer(lambda: app.Documents.Open(plan.modelo))
                modelo_abierto_por_mi = doc_modelo
            tipo = exportar.tipo_base(acceso.tipo_de(doc_modelo))
            if tipo not in METODO_DE_VISTA:
                raise ArgumentoInvalido(
                    f"No se puede hacer un plano de un documento de tipo {tipo}.",
                    details={"tipo": tipo},
                )
            caja = _caja_del_modelo(doc_modelo, tipo)

        draft = _nuevo_draft(app, plan.plantilla)
        info_hoja, tamano = _medida_de_hoja(draft, plan.hoja)
        distribucion = vistas.distribuir(tamano, plan.vistas)
        if plan.factor is None:
            factor, auto = vistas.elegir_escala(caja, distribucion.celda, plan.vistas)
        else:
            factor, auto = plan.factor, None

        enlace = _enlazar(draft, plan.modelo)
        coleccion = _vistas_de_la_hoja(draft)
        colocadas = []
        for posicion in distribucion.posiciones:
            orientacion = vistas.orientacion_de(posicion.nombre)
            _agregar_vista(
                coleccion,
                METODO_DE_VISTA[tipo],
                enlace,
                orientacion,
                factor,
                posicion.x,
                posicion.y,
            )
            colocadas.append(
                {
                    "nombre": posicion.nombre,
                    "orientacion": vistas.ORIENTACIONES[posicion.nombre],
                    "x": round(posicion.x, 6),
                    "y": round(posicion.y, 6),
                }
            )

        _guardar_draft(draft, plan.draft, sobrescribir)
        guardado = True
        resultado: dict[str, Any] = {
            "draft": plan.draft,
            "modelo": plan.modelo,
            "hoja": info_hoja,
            "escala": vistas.nombre_de_escala(factor),
            "vistas": colocadas,
            "abierto": mantener_abierto,
        }
        if auto is not None:
            resultado["escala_auto"] = auto
        if plan.pdf is not None:
            formato = exportar.FORMATOS["pdf"]
            resultado["pdf"] = plan.pdf
            resultado["pdf_bytes"] = exportar.escribir(draft, formato, plan.pdf, sobrescribir)
        resultado.update(exportar.extras_de(exportar.FORMATOS["pdf"]))
        return resultado
    except BaseException:
        if draft is not None and not guardado:
            _descartar(draft)
            draft = None
        raise
    finally:
        if draft is not None and not mantener_abierto:
            with contextlib.suppress(Exception):
                leer(lambda: draft.Close(False))
        if modelo_abierto_por_mi is not None:
            with contextlib.suppress(Exception):
                leer(lambda: modelo_abierto_por_mi.Close(False))
        if activo_previo is not None and not (mantener_abierto and draft is not None):
            with contextlib.suppress(Exception):
                actual = documentos.documento_activo(app)
                if actual is None or actual is not activo_previo:
                    leer(activo_previo.Activate)


def _guardar_draft(draft: Any, destino: str, sobrescribir: bool) -> None:
    """`SaveAs` del Draft nuevo. Si el destino existe (ya validado con `--overwrite`), se aparta."""
    documentos.guardar_en(draft, destino, sobrescribir, exportar.verificar_archivo)


def _descartar(draft: Any) -> None:
    """Cerrá un Draft a medio armar sin guardar."""
    with contextlib.suppress(Exception):
        draft.Dirty = False
    with contextlib.suppress(Exception):
        leer(lambda: draft.Close(False))


__all__ = ["METODO_DE_VISTA", "Plan", "crear", "planificar"]
