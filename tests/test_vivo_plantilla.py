"""`--template` contra Solid Edge abierto. No corre por defecto.

Usa las plantillas ISO que instala Solid Edge 2026 (si no están, se saltea) y cierra sin guardar
solo los documentos que crea.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from se_cli.cli import app

ISO = Path(r"C:\Program Files\Siemens\Solid Edge 2026\Template\ISO Metric")


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@pytest.mark.live
@pytest.mark.parametrize(
    ("tipo", "plantilla"), [("part", "iso metric part.par"), ("draft", "iso metric draft.dft")]
)
def test_docs_new_con_plantilla(tipo, plantilla):
    ruta = ISO / plantilla
    if not ruta.exists():
        pytest.skip(f"No está la plantilla {ruta}")
    r, sobre = _correr("docs", "new", tipo, "--template", str(ruta))
    assert r.exit_code == 0, sobre
    try:
        assert sobre["data"]["tipo"] == tipo and sobre["data"]["ruta"] is None
    finally:
        _correr("docs", "close", sobre["data"]["nombre"], "--discard")
