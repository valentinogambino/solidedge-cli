"""Prueba de F5 (`flat-dxf --create`) contra Solid Edge abierto. No corre por defecto (`-m live`).

Arma una chapa nueva (tab de 100x50x1 mm y una brida de 30 mm, en modo sincrónico) con un script
que corre por `se run --allow-scripts`, la guarda en `tmp_path` y exporta el desarrollo. Solo toca
documentos que crea ella.
"""

import json
import math

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
        assert any("SuppressVariable" in p for p in sobre["error"]["details"]["probado"])
        for operacion in ("Tab_1", "Flange_1"):
            r, sobre = _correr("features", "unsuppress", operacion, "--doc", sincronica.name)
            # `Status` dice ok, así que ya está activa: no se escribe nada.
            assert r.exit_code == 0 and sobre["data"]["changed"] is False, sobre
            r, sobre = _correr("features", "suppress", operacion, "--doc", sincronica.name)
            assert r.exit_code == 6 and sobre["error"]["details"]["operacion"] == operacion, sobre
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
        for intento in (1, 2):  # el Undo limpia cada vez: el segundo falla igual de claro
            r, sobre = _correr("sheetmetal", "flat-dxf", "--create", *d)
            assert r.exit_code == 6, (intento, sobre)
            error = sobre["error"]
            assert error["code"] == "no_soportado" and error["hresult"] == "0x80020009"
            assert error["details"]["base"]["tipo"] == "ExtrudedProtrusion"
            assert error["details"]["desarrollo_vacio_limpiado"] is True
            assert error["details"]["desarrollo_vacio_en_sesion"] is False
            r, sobre = _correr("com", "get", "ActiveDocument.FlatPatternModels.Count")
            assert sobre["data"]["valor"] == 0, (intento, sobre)  # el Undo dejó la chapa limpia
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


@pytest.mark.live
def test_chapa_con_brida_por_la_cli(tmp_path):
    """Chapa 100x50x1 mm con base sincrónica y una brida de 30 mm sobre una arista recta larga."""
    r, sobre = _correr("docs", "new", "sheetmetal")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    chapa = tmp_path / "con_brida.psm"
    try:
        d = ["--doc", nombre]
        r, sobre = _correr("sketch", "rect", "--width", "100mm", "--height", "50mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("sheetmetal", "tab", "--sync", *d)
        assert r.exit_code == 0 and sobre["data"]["modo"] == "sincronico", sobre

        r, sobre = _correr("edges", "list", "--units", "mm", *d)
        assert r.exit_code == 0, sobre
        rectas = [a for a in sobre["data"]["aristas"] if a["tipo"] == "linea"]
        larga = max(rectas, key=lambda a: a["longitud"])
        assert larga["longitud"] == pytest.approx(100.0, abs=0.01)

        r, sobre = _correr(
            "sheetmetal",
            "flange",
            "--edge",
            str(larga["indice"]),
            "--length",
            "30mm",
            "--units",
            "mm",
            *d,
        )
        assert r.exit_code == 0, sobre
        datos = sobre["data"]
        assert datos["volumen_despues"] > datos["volumen_antes"]

        r, sobre = _correr("docs", "save-as", str(chapa), nombre)
        assert r.exit_code == 0, sobre
        nombre = chapa.name
        r, sobre = _correr("sheetmetal", "flat-dxf", "--create", "--doc", nombre)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["entidades_dxf"] > 0
        assert sum(_entidades_dxf(tmp_path / "con_brida.dxf").values()) > 0
    finally:
        _cerrar(nombre)


@pytest.mark.live
@pytest.mark.parametrize(
    ("medida", "direccion", "volumen_mm3"),
    [
        ("face", "normal", 7935.6194),
        ("opposite", "normal", 7835.6194),
        ("opposite", "reverse", 7935.6194),
    ],
)
def test_brida_con_measure_por_la_cli(medida, direccion, volumen_mm3):
    """Chapa 100x50x1 mm, brida de 30 mm a 90° con radio 1 mm: el volumen sale de la fórmula.

    `opposite` mide desde la cara opuesta: la pared recta es `L - (r+t)*cot(ángulo/2)` (a 90°, un
    espesor más corta que con `face`). V = a*t*(b+s) + a*(pi-theta)/2*((r+t)^2-r^2), con a = 100,
    t = 1, r = 1, b = 50 - r*cot(theta/2) (- t/sen(theta) con `normal`).
    """
    r, sobre = _correr("docs", "new", "sheetmetal")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    try:
        d = ["--doc", nombre]
        assert (
            _correr("sketch", "rect", "--width", "100mm", "--height", "50mm", *d)[0].exit_code == 0
        )
        r, sobre = _correr("sheetmetal", "tab", "--sync", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("edges", "list", "--units", "mm", *d)
        rectas = [a for a in sobre["data"]["aristas"] if a["tipo"] == "linea"]
        larga = max(rectas, key=lambda a: a["longitud"])

        r, sobre = _correr(
            "sheetmetal",
            "flange",
            "--edge",
            str(larga["indice"]),
            "--length",
            "30mm",
            "--radius",
            "1mm",
            "--direction",
            direccion,
            "--measure",
            medida,
            "--units",
            "mm",
            *d,
        )
        assert r.exit_code == 0, sobre
        assert sobre["data"]["medida"] == medida
        assert sobre["data"]["volumen_despues"] * 1e9 == pytest.approx(volumen_mm3, abs=0.01)
    finally:
        _cerrar(nombre)


def _volumen_de_brida_mm3(t, r, theta, largo, ancho, arista, direccion, medida):
    """Regla medida en vivo: V = a*t*(b + s) + a*(pi - theta)/2*((r+t)^2 - r^2), en mm3."""
    th = math.radians(theta)
    cot = 1 / math.tan(th / 2)
    s = largo - (r if medida == "face" else r + t) * cot
    b = ancho - r * cot - (t / math.sin(th) if direccion == "normal" else 0)
    return arista * t * (b + s) + arista * (math.pi - th) / 2 * ((r + t) ** 2 - r**2)


def _base_sincronica(t_mm, largo=100, ancho=50, arista="larga"):
    """Chapa nueva `largo x ancho x t_mm` con base sincrónica: (nombre, índice de la arista)."""
    r, sobre = _correr("docs", "new", "sheetmetal")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    d = ["--doc", nombre]
    assert _correr("vars", "set", "MaterialThickness", f"{t_mm}mm", *d)[0].exit_code == 0
    r, sobre = _correr("sketch", "rect", "--width", f"{largo}mm", "--height", f"{ancho}mm", *d)
    assert r.exit_code == 0, sobre
    r, sobre = _correr("sheetmetal", "tab", "--sync", *d)
    assert r.exit_code == 0, sobre
    r, sobre = _correr("edges", "list", "--units", "mm", *d)
    rectas = [a for a in sobre["data"]["aristas"] if a["tipo"] == "linea" and a["longitud"] > 10]
    elegir = max if arista == "larga" else min
    return nombre, elegir(rectas, key=lambda a: a["longitud"])["indice"]


def _brida(nombre, arista, largo_mm, angulo, direccion, medida, radio_mm=1):
    return _correr(
        "sheetmetal",
        "flange",
        "--edge",
        str(arista),
        "--length",
        f"{largo_mm}mm",
        "--angle",
        str(angulo),
        "--direction",
        direccion,
        "--measure",
        medida,
        "--radius",
        f"{radio_mm}mm",
        "--units",
        "mm",
        "--doc",
        nombre,
    )


@pytest.mark.live
@pytest.mark.parametrize(
    ("espesor", "angulo", "direccion", "medida"),
    [
        (2, 90, "normal", "face"),
        (2, 60, "reverse", "opposite"),
        (0.5, 60, "normal", "face"),
        (0.5, 90, "reverse", "opposite"),
        (1, 120, "normal", "face"),
        (1, 135, "reverse", "opposite"),
    ],
)
def test_brida_con_otro_espesor_y_mas_de_90_grados(espesor, angulo, direccion, medida):
    """Espesor 2 y 0,5 mm y ángulos de 120 y 135°: el volumen medido es el de la fórmula."""
    nombre, arista = _base_sincronica(espesor)
    try:
        r, sobre = _brida(nombre, arista, 30, angulo, direccion, medida)
        assert r.exit_code == 0, sobre
        esperado = _volumen_de_brida_mm3(espesor, 1, angulo, 30, 50, 100, direccion, medida)
        assert sobre["data"]["volumen_despues"] * 1e9 == pytest.approx(esperado, abs=0.01)
    finally:
        _cerrar(nombre)


@pytest.mark.live
@pytest.mark.parametrize(
    ("largo", "ancho", "arista", "angulo", "direccion"),
    [(100, 80, "larga", 60, "reverse"), (100, 50, "corta", 90, "normal")],
)
def test_brida_sobre_otro_ancho_de_base_y_sobre_el_borde_corto(
    largo, ancho, arista, angulo, direccion
):
    nombre, indice = _base_sincronica(1, largo, ancho, arista)
    try:
        r, sobre = _brida(nombre, indice, 30, angulo, direccion, "face")
        assert r.exit_code == 0, sobre
        a, w = (largo, ancho) if arista == "larga" else (ancho, largo)
        esperado = _volumen_de_brida_mm3(1, 1, angulo, 30, w, a, direccion, "face")
        assert sobre["data"]["volumen_despues"] * 1e9 == pytest.approx(esperado, abs=0.01)
    finally:
        _cerrar(nombre)


@pytest.mark.live
@pytest.mark.parametrize(("angulo", "medida"), [(45, "face"), (60, "opposite"), (120, "face")])
def test_brida_largo_minimo_fuera_de_90_grados(angulo, medida):
    """El límite es radio*cot(ángulo/2) con `face` y (radio+espesor)*cot(ángulo/2) con `opposite`.

    Un largo 1 % por debajo se rechaza sin cambiar el modelo; uno 1 % por encima se acepta, aunque
    la pared sea casi nula y el volumen baje (45 y 120°: la base recortada pesa más que la pared).
    """
    nombre, arista = _base_sincronica(1)
    try:
        minimo = (1 if medida == "face" else 2) / math.tan(math.radians(angulo) / 2)
        volumen = _correr("mass", "--density", "7850", "--doc", nombre)[1]["data"]["volumen"]
        r, sobre = _brida(nombre, arista, round(minimo * 0.99, 4), angulo, "normal", medida)
        assert r.exit_code == 4 and sobre["error"]["details"]["causa"] == "brida_rechazada", sobre
        assert _correr("mass", "--density", "7850", "--doc", nombre)[1]["data"][
            "volumen"
        ] == pytest.approx(volumen, rel=1e-9)
        largo = round(minimo * 1.01, 4)
        r, sobre = _brida(nombre, arista, largo, angulo, "normal", medida)
        assert r.exit_code == 0, sobre
        esperado = _volumen_de_brida_mm3(1, 1, angulo, largo, 50, 100, "normal", medida)
        assert sobre["data"]["volumen_despues"] * 1e9 == pytest.approx(esperado, abs=0.01)
    finally:
        _cerrar(nombre)


def _desarrollo_del_dxf(ruta) -> tuple[float, float, dict[str, int]]:
    """Caja (x, y) en mm y entidades de la sección ENTITIES (sin el encabezado del DXF)."""
    lineas = [x.strip() for x in ruta.read_text(errors="ignore").splitlines()]
    pares = list(zip(lineas[0::2], lineas[1::2], strict=False))
    xs: list[float] = []
    ys: list[float] = []
    tipos: dict[str, int] = {}
    en_entidades = False
    for i, (codigo, valor) in enumerate(pares):
        if codigo == "2" and i and pares[i - 1] == ("0", "SECTION"):
            en_entidades = valor == "ENTITIES"
        elif en_entidades and codigo == "0" and valor not in ("SECTION", "ENDSEC"):
            tipos[valor] = tipos.get(valor, 0) + 1
        elif en_entidades and codigo in ("10", "11"):
            xs.append(float(valor))
        elif en_entidades and codigo in ("20", "21"):
            ys.append(float(valor))
    return max(xs) - min(xs), max(ys) - min(ys), tipos


@pytest.mark.live
@pytest.mark.parametrize(
    ("espesor", "angulo", "direccion"), [(2, 60, "reverse"), (1, 120, "normal")]
)
def test_desarrollo_de_una_brida_es_base_mas_pared_mas_arco_neutro(
    tmp_path, espesor, angulo, direccion
):
    """DXF = 100 mm x (b + s + (pi - theta)*(r + K*t)), con K = `NeutralFactor` del documento."""
    nombre, arista = _base_sincronica(espesor)
    chapa = tmp_path / "desarrollada.psm"
    try:
        r, sobre = _brida(nombre, arista, 30, angulo, direccion, "face")
        assert r.exit_code == 0, sobre
        k = _correr("vars", "get", "NeutralFactor", "--doc", nombre)[1]["data"]["valor"]
        assert _correr("docs", "save-as", str(chapa), nombre)[0].exit_code == 0
        nombre = chapa.name
        r, sobre = _correr("sheetmetal", "flat-dxf", "--create", "--doc", nombre)
        assert r.exit_code == 0, sobre
        th = math.radians(angulo)
        cot = 1 / math.tan(th / 2)
        b = 50 - cot - (espesor / math.sin(th) if direccion == "normal" else 0)
        esperado = b + (30 - cot) + (math.pi - th) * (1 + k * espesor)
        x, y, tipos = _desarrollo_del_dxf(tmp_path / "desarrollada.dxf")
        assert tipos == {"LINE": 5}  # el contorno y la línea del doblez
        assert sorted((x, y)) == pytest.approx([esperado, 100.0], abs=0.01)
    finally:
        _cerrar(nombre)
