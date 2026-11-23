"""Pruebas de F4 contra Solid Edge abierto. No corren por defecto (`-m live`).

Solo crean documentos nuevos (`docs new`) y escriben en `tmp_path`; al terminar cierran con
`--discard` únicamente los que ellas crearon. No tocan ni cierran documentos del usuario. Aun así,
avisá antes de correrlas: abren y cierran documentos en la sesión viva.

Validadas en vivo el 2026-11-23 (SE 226.00.01.04): los tests exigen exit 0 (o el exit documentado).
"""

import json
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@contextmanager
def _documento_nuevo(tipo: str):
    """Documento nuevo y vacío; se descarta al salir (nunca toca otros documentos).

    Se lo cierra por su ruta completa si se guardó con `save-as` (cambia el nombre).
    """
    r, sobre = _correr("docs", "new", tipo)
    assert r.exit_code == 0, r.output
    nombre = sobre["data"]["nombre"]
    try:
        yield nombre
    finally:
        r, sobre = _correr("docs", "list")
        for doc in sobre["data"]["documentos"]:
            if doc["nombre"] == nombre or doc["ruta"] == _RUTAS.get(nombre):
                _correr("docs", "close", doc["ruta"] or doc["nombre"], "--discard")


_RUTAS: dict[str, str] = {}


@pytest.mark.live
def test_export_png_de_un_part_nuevo(tmp_path):
    with _documento_nuevo("part") as nombre:
        destino = tmp_path / "vista.png"
        r, sobre = _correr("export", "--format", "png", "--doc", nombre, "--out", str(destino))
        assert r.exit_code == 0, sobre
        assert destino.stat().st_size > 0


@pytest.mark.live
def test_export_pdf_de_un_draft_nuevo(tmp_path):
    with _documento_nuevo("draft") as nombre:
        destino = tmp_path / "plano.pdf"
        r, sobre = _correr("export", "--format", "pdf", "--doc", nombre, "--out", str(destino))
        assert r.exit_code == 0, sobre
        assert sobre["data"]["marca_de_agua"] == "presente"


@pytest.mark.live
def test_export_step_de_un_draft_da_exit_2():
    with _documento_nuevo("draft") as nombre:
        r, sobre = _correr("export", "--format", "step", "--doc", nombre, "--out", "x.stp")
        assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


@pytest.mark.live
def test_flat_dxf_de_un_part_nuevo_da_exit_2(tmp_path):
    with _documento_nuevo("part") as nombre:
        r, _ = _correr("sheetmetal", "flat-dxf", "--doc", nombre, "--out", str(tmp_path / "a.dxf"))
        assert r.exit_code == 2


@pytest.mark.live
def test_flat_dxf_de_una_chapa_nueva_sin_desarrollo(tmp_path):
    with _documento_nuevo("sheetmetal") as nombre:
        r, sobre = _correr(
            "sheetmetal", "flat-dxf", "--doc", nombre, "--out", str(tmp_path / "chapa.dxf")
        )
        assert r.exit_code == 5, sobre
        assert not (tmp_path / "chapa.dxf").exists()


@pytest.mark.live
def test_draft_from_part_de_un_part_nuevo_guardado_en_tmp(tmp_path):
    with _documento_nuevo("part") as nombre:
        modelo = tmp_path / "modelo.par"
        r, _ = _correr("docs", "save-as", str(modelo), nombre)
        _RUTAS[nombre] = str(modelo)
        assert r.exit_code == 0
        destino = tmp_path / "plano.dft"
        r, sobre = _correr(
            "draft", "from-part", str(modelo), "--out", str(destino), "--scale", "1:1", "--pdf"
        )
        assert r.exit_code == 0, sobre
        assert destino.stat().st_size > 0 and sobre["data"]["marca_de_agua"] == "presente"
