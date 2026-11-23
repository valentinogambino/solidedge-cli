"""Pruebas de F5 (modelado) contra Solid Edge abierto. No corren por defecto (`-m live`).

Solo crean documentos nuevos (`docs new`) y escriben en `tmp_path`; al terminar cierran con
`--discard` únicamente los que ellas crearon (se identifican por nombre). No tocan documentos del
usuario. Avisá antes de correrlas: abren y cierran documentos en la sesión viva.
"""

import json
import math
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@contextmanager
def _documento_nuevo(tipo: str):
    """Documento nuevo; se descarta al salir (solo ese, por nombre o por ruta si se guardó)."""
    r, sobre = _correr("docs", "new", tipo)
    assert r.exit_code == 0, r.output
    nombre = sobre["data"]["nombre"]
    try:
        yield nombre
    finally:
        r, sobre = _correr("docs", "list")
        for doc in sobre["data"]["documentos"]:
            if doc["nombre"] == nombre:
                _correr("docs", "close", doc["nombre"], "--discard")


@pytest.mark.live
def test_caja_con_agujero_y_masa(tmp_path):
    with _documento_nuevo("part") as nombre:
        doc = ["--doc", nombre]
        r, sobre = _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *doc)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["perfil"] == 1 and sobre["data"]["valido"] is True
        r, sobre = _correr("extrude", "10mm", *doc)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["volumen_si"] == pytest.approx(15e-6)
        r, sobre = _correr("hole", "--at", "25mm,15mm", "--diameter", "8mm", "--through", *doc)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("mass", "--density", "7850", *doc)
        assert r.exit_code == 0, sobre
        esperado = (50 * 30 * 10 - math.pi * 4**2 * 10) * 1e-9
        assert sobre["data"]["volumen"] == pytest.approx(esperado, rel=1e-6)
        assert sobre["data"]["masa"] == pytest.approx(esperado * 7850, rel=1e-6)


@pytest.mark.live
def test_corte_sin_efecto_se_deshace():
    with _documento_nuevo("part") as nombre:
        doc = ["--doc", nombre]
        _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *doc)
        _correr("extrude", "10mm", *doc)
        r, sobre = _correr(
            "hole", "--at", "10mm,10mm", "--diameter", "4mm", "--depth", "5mm",
            "--direction", "reverse", *doc,
        )  # fmt: skip
        assert r.exit_code == 2 and "no quitó material" in sobre["error"]["message"]


@pytest.mark.live
def test_revolucion_de_un_tubo():
    with _documento_nuevo("part") as nombre:
        doc = ["--doc", nombre]
        r, sobre = _correr(
            "sketch", "rect", "--plane", "front", "--width", "20mm", "--height", "40mm",
            "--at", "10mm,0", *doc,
        )  # fmt: skip
        assert r.exit_code == 0, sobre
        r, sobre = _correr("revolve", "--axis", "y", *doc)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["volumen_si"] == pytest.approx(
            math.pi * (0.03**2 - 0.01**2) * 0.04, rel=1e-9
        )


@pytest.mark.live
def test_sketch_en_un_draft_da_exit_2():
    with _documento_nuevo("draft") as nombre:
        r, _ = _correr("sketch", "rect", "--width", "1mm", "--height", "1mm", "--doc", nombre)
        assert r.exit_code == 2
