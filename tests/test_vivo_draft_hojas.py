"""Hojas A5 y A0 (fondo generado) y A3 (de la plantilla) contra Solid Edge. No corre por defecto.

Arma una caja guardada en `tmp_path`, hace los planos con `--keep-open`, mide el fondo por COM y el
tamaño del PDF, y al terminar cierra con `--discard` solo esos documentos.
"""

import json
import re
import textwrap

import pytest
from typer.testing import CliRunner

from se_cli.cli import app
from se_cli.core import vistas

MEDIR = textwrap.dedent(
    """
    def main(app, args):
        hoja = app.ActiveDocument.ActiveSheet
        fondo = hoja.Background
        ancho, alto = fondo.SheetSetup.SheetWidth, fondo.SheetSetup.SheetHeight
        xs, ys, lx, ly, textos = [], [], [], [], []
        objetos = fondo.DrawingObjects
        for i in range(1, objetos.Count + 1):
            r = objetos.Item(i).Range(0.0, 0.0, 0.0, 0.0)
            planos = [v for p in r for v in (p if isinstance(p, tuple) else (p,))]
            xs += [planos[0], planos[2]]
            ys += [planos[1], planos[3]]
        lineas = fondo.Lines2d
        for i in range(1, lineas.Count + 1):
            a, b = lineas.Item(i).GetStartPoint(), lineas.Item(i).GetEndPoint()
            lx += [a[0], b[0]]
            ly += [a[1], b[1]]
        horizontales = []
        for i in range(1, lineas.Count + 1):
            a, b = lineas.Item(i).GetStartPoint(), lineas.Item(i).GetEndPoint()
            if abs(a[1] - b[1]) < 1e-6 and a[1] < alto / 2:
                horizontales.append(a[1])
        cajas = fondo.TextBoxes
        for i in range(1, cajas.Count + 1):
            textos.append(str(cajas.Item(i).Text))
        return {"fondo": fondo.Name, "ancho": ancho, "alto": alto, "objetos": objetos.Count,
                "x": [min(xs), max(xs)], "y": [min(ys), max(ys)],
                "marco_x": [min(lx), max(lx)], "marco_y": [min(ly), max(ly)], "textos": textos,
                "rotulo_tope": max(horizontales)}
    """
)

# (ancho, alto) en mm de la hoja apaisada y margen del marco.
HOJAS = {"A5": (210, 148, 10), "A3": (420, 297, 10), "A0": (1189, 841, 20)}


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@pytest.fixture(scope="module")
def caja(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("hojas")
    pieza = carpeta / "caja_hojas_live.par"
    r, sobre = _correr("docs", "new", "part")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    try:
        assert _correr("sketch", "rect", "--width", "50mm", "--height", "30mm")[0].exit_code == 0
        assert _correr("extrude", "20mm")[0].exit_code == 0
        r, sobre = _correr("docs", "save-as", str(pieza))
        assert r.exit_code == 0, sobre
        yield pieza
    finally:
        _, sobre = _correr("docs", "list")
        for doc in sobre["data"]["documentos"]:
            if doc["nombre"] in (nombre, pieza.name):
                _correr("docs", "close", doc["nombre"], "--discard")


@pytest.mark.live
@pytest.mark.parametrize("hoja", ["A5", "A0", "A3"])
def test_hoja_con_marco_y_rotulo_dentro(caja, hoja):
    ancho, alto, margen = HOJAS[hoja]
    destino = caja.with_name(f"plano_{hoja}.dft")
    r, sobre = _correr(
        "draft",
        "from-part",
        str(caja),
        "--sheet",
        hoja,
        "--pdf",
        "--out",
        str(destino),
        "--keep-open",
        "--overwrite",
    )
    assert r.exit_code == 0, sobre
    try:
        info = sobre["data"]["hoja"]
        assert info["fondo"] == f"{hoja}-Sheet"
        assert ("fondo_generado" in info) is (hoja != "A3")

        script = caja.with_name("medir_fondo.py")
        script.write_text(MEDIR, encoding="utf-8")
        r, medida = _correr("run", str(script), "--allow-scripts")
        assert r.exit_code == 0, medida
        m = medida["data"]["resultado"]
        assert m["fondo"] == f"{hoja}-Sheet" and m["objetos"] > 20
        assert (round(m["ancho"] * 1000), round(m["alto"] * 1000)) == (ancho, alto)
        # El marco queda a `margen` mm del borde y nada del fondo se sale de la hoja.
        marco = [v * 1000 for v in (*m["marco_x"], *m["marco_y"])]
        assert marco == pytest.approx([margen, ancho - margen, margen, alto - margen], abs=0.2)
        assert 0 <= m["x"][0] * 1000 and m["x"][1] * 1000 <= ancho
        assert 0 <= m["y"][0] * 1000 and m["y"][1] * 1000 <= alto
        assert hoja in [t.strip() for t in m["textos"]]
        # El tope del rótulo es la medida con la que `vistas` arma el área útil.
        marco_vistas, tope_vistas = vistas.MEDIDAS_DE_HOJA[hoja]
        assert marco_vistas * 1000 == pytest.approx(margen)
        assert m["rotulo_tope"] == pytest.approx(tope_vistas, abs=0.0002)

        pdf = destino.with_suffix(".pdf").read_bytes()
        caja_pdf = [float(v) for v in re.search(rb"/MediaBox\s*\[([^\]]*)\]", pdf).group(1).split()]
        lados = sorted((caja_pdf[2] - caja_pdf[0], caja_pdf[3] - caja_pdf[1]))
        assert [round(v * 25.4 / 72) for v in lados] == sorted((ancho, alto))
    finally:
        _correr("docs", "close", destino.name, "--discard")
