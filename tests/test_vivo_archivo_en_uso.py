"""`--overwrite` sobre archivos que Solid Edge tiene abiertos. No corre por defecto.

Crea dos piezas propias en `tmp_path` y al terminar cierra solo esas, sin guardar.
"""

import json

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@pytest.mark.live
def test_save_as_y_draft_sobre_archivos_abiertos_en_solid_edge(tmp_path):
    a, b = tmp_path / "a.par", tmp_path / "b.par"
    nombres: list[str] = []
    try:
        for destino in (a, b):
            r, sobre = _correr("docs", "new", "part")
            assert r.exit_code == 0, sobre
            nombres.append(sobre["data"]["nombre"])
            r, sobre = _correr("docs", "save-as", str(destino))
            assert r.exit_code == 0, sobre
            nombres.append(destino.name)
        original = a.read_bytes()

        r, sobre = _correr("docs", "save-as", str(a), "b.par", "--overwrite")
        assert r.exit_code == 6, sobre
        detalles = sobre["error"]["details"]
        assert detalles["motivo"] == "archivo_en_uso"
        assert detalles["abierto_en_solid_edge"]["nombre"] == "a.par"
        assert a.read_bytes() == original
        assert [p for p in tmp_path.iterdir() if ".bak" in p.name] == []

        # Sin el chequeo previo: Solid Edge tiene el .dft abierto y Windows no deja apartarlo.
        r, sobre = _correr("draft", "from-part", str(a), "--scale", "1:1", "--keep-open")
        assert r.exit_code == 0, sobre
        nombres.append("a.dft")
        dft = (tmp_path / "a.dft").read_bytes()
        r, sobre = _correr("draft", "from-part", str(a), "--scale", "1:1", "--overwrite")
        assert r.exit_code == 6, sobre
        assert sobre["error"]["details"]["winerror"] == 32
        assert (tmp_path / "a.dft").read_bytes() == dft
        assert [p for p in tmp_path.iterdir() if ".bak" in p.name] == []
    finally:
        _, sobre = _correr("docs", "list")
        for doc in reversed(sobre["data"]["documentos"]):
            if doc["nombre"] in nombres:
                _correr("docs", "close", doc["nombre"], "--discard")
