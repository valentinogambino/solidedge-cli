"""Prueba de F5 (`flat-dxf --create`) contra Solid Edge abierto. No corre por defecto (`-m live`).

Arma una chapa nueva (tab de 100x50x1 mm y una brida de 30 mm, en modo sincrónico) con un script
que corre por `se run --allow-scripts`, la guarda en `tmp_path` y exporta el desarrollo. Solo toca
documentos que crea ella.
"""

import json

import pytest
from typer.testing import CliRunner

from se_cli.cli import app

SCRIPT = """
import pythoncom
from win32com.client import VARIANT


def main(app, args):
    destino = args[0]
    doc = app.Documents.Add("SolidEdge.SheetMetalDocument")
    doc.ModelingMode = 1
    perfil = doc.ProfileSets.Add().Profiles.Add(doc.RefPlanes.Item(1))
    puntos = [(0, 0), (0.1, 0), (0.1, 0.05), (0, 0.05)]
    for a, b in zip(puntos, puntos[1:] + puntos[:1]):
        perfil.Lines2d.AddBy2Points(*a, *b)
    perfil.End(1)
    doc.Models.AddBaseTab(perfil, 2)
    modelo = doc.Models.Item(1)
    caras = modelo.Body.Faces(1)
    arriba = max(range(1, caras.Count + 1), key=lambda i: caras.Item(i).Area)
    vacio = VARIANT(pythoncom.VT_EMPTY, None)
    modelo.Flanges.AddSync(
        caras.Item(arriba).Edges.Item(1), 0.03, vacio, 0.001, *([vacio] * 7), vacio
    )
    volumen = doc.Models.Item(1).Body.Volume
    doc.SaveAs(destino)
    return {"volumen": volumen}
"""


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


def _caja_del_dxf(ruta) -> tuple[float, float]:
    lineas = [x.strip() for x in ruta.read_text(errors="ignore").splitlines()]
    pares = list(zip(lineas[0::2], lineas[1::2], strict=False))
    xs = [float(v) for c, v in pares if c in ("10", "11")]
    ys = [float(v) for c, v in pares if c in ("20", "21")]
    return max(xs) - min(xs), max(ys) - min(ys)


@pytest.mark.live
def test_flat_dxf_create_de_una_chapa_con_un_doblez(tmp_path):
    script = tmp_path / "armar.py"
    script.write_text(SCRIPT, encoding="utf-8")
    chapa = tmp_path / "doblada.psm"
    r, sobre = _correr("run", str(script), "--allow-scripts", "--", str(chapa))
    assert r.exit_code == 0, sobre
    volumen = sobre["data"]["resultado"]["volumen"]
    try:
        r, sobre = _correr("sheetmetal", "flat-dxf", "--doc", str(chapa))
        assert r.exit_code == 5  # sin --create no cambia nada
        assert "--create" in sobre["error"]["details"]["hint"]
        assert sobre["error"]["details"]["cambios_pendientes"] is False

        salida = tmp_path / "doblada.dxf"
        r, sobre = _correr("sheetmetal", "flat-dxf", "--doc", str(chapa), "--create")
        assert r.exit_code == 0, sobre
        data = sobre["data"]
        assert data["desarrollo_creado"] is True and data["documento_guardado"] is True
        assert data["entidades_dxf"] > 0 and data["cara"]["indice"] >= 1

        ancho, largo = _caja_del_dxf(salida)
        ancho, largo = sorted((ancho, largo), reverse=True)  # mm: 100 x ~79
        assert ancho == pytest.approx(100.0, abs=0.01)
        assert 76.0 < largo < 80.0
        # El área del desarrollo por el espesor (1 mm) es el volumen de la chapa (1 %).
        assert ancho * largo * 1e-9 == pytest.approx(volumen, rel=0.01)

        r, sobre = _correr("sheetmetal", "flat-dxf", "--doc", str(chapa), "--create", "--overwrite")
        assert r.exit_code == 0 and sobre["data"]["desarrollo_creado"] is False

        r, sobre = _correr("docs", "list")
        activo = [d for d in sobre["data"]["documentos"] if d["ruta"] == str(chapa)]
        assert len(activo) == 1 and activo[0]["activo"] is True
    finally:
        _correr("docs", "close", str(chapa), "--discard")


SCRIPT_TAB_ORDENADA = """
def main(app, args):
    doc = app.Documents.Add("SolidEdge.SheetMetalDocument")
    perfil = doc.ProfileSets.Add().Profiles.Add(doc.RefPlanes.Item(1))
    puntos = [(0, 0), (0.1, 0), (0.1, 0.05), (0, 0.05)]
    for a, b in zip(puntos, puntos[1:] + puntos[:1]):
        perfil.Lines2d.AddBy2Points(*a, *b)
    perfil.End(1)
    doc.Models.AddBaseTab(perfil, 2)
    doc.SaveAs(args[0])
    return {"modo": doc.ModelingMode}
"""


def _cerrar(nombre: str) -> None:
    _correr("docs", "close", nombre, "--discard")


@pytest.mark.live
def test_suppress_en_chapa_ordenada_funciona_y_en_sincronica_da_exit_6(tmp_path):
    ordenada, sincronica = tmp_path / "ordenada.psm", tmp_path / "sincronica.psm"
    for nombre, codigo, destino in (
        ("ordenada.py", SCRIPT_TAB_ORDENADA, ordenada),
        ("sincronica.py", SCRIPT, sincronica),
    ):
        (tmp_path / nombre).write_text(codigo, encoding="utf-8")
        r, sobre = _correr("run", str(tmp_path / nombre), "--allow-scripts", "--", str(destino))
        assert r.exit_code == 0, sobre
    try:
        # Modo ordenado: se suprime el Tab y la masa pasa a 0; se reactiva y vuelve.
        d = ["--doc", ordenada.name]
        r, sobre = _correr("features", "suppress", "Tab_1", *d)
        assert r.exit_code == 0 and sobre["data"]["suprimida"] is True, sobre
        assert _correr("mass", "--density", "7850", *d)[1]["data"]["volumen"] == 0
        r, sobre = _correr("features", "unsuppress", "Tab_1", *d)
        assert r.exit_code == 0 and sobre["data"]["suprimida"] is False, sobre
        volumen = _correr("mass", "--density", "7850", *d)[1]["data"]["volumen"]
        assert volumen == pytest.approx(100e-3 * 50e-3 * 1e-3, rel=1e-6)

        # Modo sincrónico: Solid Edge rechaza `Suppress` con un error genérico.
        r, sobre = _correr("features", "suppress", "Flange_1", "--doc", sincronica.name)
        assert r.exit_code == 6 and sobre["error"]["code"] == "no_soportado", sobre
        assert sobre["error"]["details"]["modo"] == "sincronico"
    finally:
        _cerrar(ordenada.name)
        _cerrar(sincronica.name)


SCRIPT_BASE_DE_PIEZA = """
def main(app, args):
    doc = app.Documents.Add("SolidEdge.SheetMetalDocument")
    perfil = doc.ProfileSets.Add().Profiles.Add(doc.RefPlanes.Item(1))
    puntos = [(0, 0), (0.1, 0), (0.1, 0.05), (0, 0.05)]
    for a, b in zip(puntos, puntos[1:] + puntos[:1]):
        perfil.Lines2d.AddBy2Points(*a, *b)
    perfil.End(1)
    doc.Models.AddFiniteExtrudedProtrusion(1, (perfil,), 2, 0.001)
    doc.SaveAs(args[0])
    return {"modo": doc.ModelingMode}
"""


def _entidades_dxf(ruta) -> dict[str, int]:
    lineas = [x.strip() for x in ruta.read_text(errors="ignore").splitlines()]
    pares = list(zip(lineas[0::2], lineas[1::2], strict=False))
    tipos: dict[str, int] = {}
    en_entidades = False
    for i, (codigo, valor) in enumerate(pares):
        if codigo == "2" and i and pares[i - 1] == ("0", "SECTION"):
            en_entidades = valor == "ENTITIES"
        elif en_entidades and codigo == "0" and valor not in ("SECTION", "ENDSEC"):
            tipos[valor] = tipos.get(valor, 0) + 1
    return tipos


@pytest.mark.live
def test_flat_dxf_create_de_un_tab_con_agujero_de_se_hole(tmp_path):
    chapa = tmp_path / "agujereada.psm"
    (tmp_path / "tab.py").write_text(SCRIPT_TAB_ORDENADA, encoding="utf-8")
    r, sobre = _correr("run", str(tmp_path / "tab.py"), "--allow-scripts", "--", str(chapa))
    assert r.exit_code == 0, sobre
    d = ["--doc", chapa.name]
    try:
        r, sobre = _correr("hole", "--at", "50mm,25mm", "--diameter", "8mm", "--through", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("sheetmetal", "flat-dxf", "--create", *d)
        assert r.exit_code == 0, sobre
        # La arista 1 de la cara grande es el círculo del agujero: se usa la siguiente.
        assert sobre["data"]["cara"]["arista"] > 1
        assert _entidades_dxf(tmp_path / "agujereada.dxf") == {"LINE": 4, "CIRCLE": 1}
    finally:
        _cerrar(chapa.name)


@pytest.mark.live
def test_flat_dxf_create_de_una_base_de_pieza_da_exit_6_clasificado(tmp_path):
    chapa = tmp_path / "maciza.psm"
    (tmp_path / "base.py").write_text(SCRIPT_BASE_DE_PIEZA, encoding="utf-8")
    r, sobre = _correr("run", str(tmp_path / "base.py"), "--allow-scripts", "--", str(chapa))
    assert r.exit_code == 0, sobre
    d = ["--doc", chapa.name]
    try:
        for intento in (1, 2):  # el segundo reutiliza el desarrollo vacío y falla igual de claro
            r, sobre = _correr("sheetmetal", "flat-dxf", "--create", *d)
            assert r.exit_code == 6, (intento, sobre)
            error = sobre["error"]
            assert error["code"] == "no_soportado" and error["hresult"] == "0x80020009"
            assert error["details"]["base"]["tipo"] == "ExtrudedProtrusion"
            assert error["details"]["desarrollo_vacio_en_sesion"] is True
        r, sobre = _correr("sheetmetal", "flat-dxf", *d)
        assert r.exit_code == 5, sobre  # el desarrollo vacío no se exporta
        assert not (tmp_path / "maciza.dxf").exists()
    finally:
        _cerrar(chapa.name)


@pytest.mark.live
def test_chapa_entera_por_la_cli_tab_agujero_y_desarrollo(tmp_path):
    r, sobre = _correr("docs", "new", "sheetmetal")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    chapa = tmp_path / "por_cli.psm"
    try:
        d = ["--doc", nombre]
        r, sobre = _correr("sketch", "rect", "--width", "100mm", "--height", "50mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("extrude", "1mm", *d)  # la base de una chapa no es una protrusión
        assert r.exit_code == 6 and "sheetmetal tab" in sobre["error"]["details"]["hint"], sobre

        r, sobre = _correr("sheetmetal", "tab", *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["nombre"] == "Tab_1"
        assert sobre["data"]["volumen_si"] == pytest.approx(0.1 * 0.05 * 0.001, rel=1e-6)

        r, sobre = _correr("hole", "--at", "50mm,25mm", "--diameter", "8mm", "--through", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("docs", "save-as", str(chapa), nombre)
        assert r.exit_code == 0, sobre
        nombre = chapa.name

        r, sobre = _correr("sheetmetal", "flat-dxf", "--create", "--doc", nombre)
        assert r.exit_code == 0, sobre
        assert _entidades_dxf(tmp_path / "por_cli.dxf") == {"LINE": 4, "CIRCLE": 1}
    finally:
        _cerrar(nombre)
