"""Pruebas de F5 (`com` y `run`) contra Solid Edge abierto. No corren por defecto (`-m live`).

Solo leen la aplicación o trabajan sobre un documento nuevo que ellas crean y descartan.
"""

import json

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@pytest.mark.live
def test_com_get_de_la_aplicacion():
    r, sobre = _correr("--readonly", "com", "get", "Version")
    assert r.exit_code == 0 and sobre["data"]["valor"]
    r, sobre = _correr("--readonly", "com", "get", "Documents.Count")
    assert r.exit_code == 0 and isinstance(sobre["data"]["valor"], int)


@pytest.mark.live
def test_com_get_set_invoke_sobre_un_part_nuevo():
    r, sobre = _correr("docs", "new", "part")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    try:
        r, sobre = _correr("com", "get", f'Documents.Item("{nombre}").Name')
        assert r.exit_code == 0 and sobre["data"]["valor"] == nombre
        r, sobre = _correr("com", "get", f'Documents.Item("{nombre}").RefPlanes', "--list")
        assert r.exit_code == 0 and sobre["data"]["valor"]["cantidad"] == 3
        r, sobre = _correr("com", "invoke", "Documents.Item", f'"{nombre}"')
        assert r.exit_code == 0 and sobre["data"]["resultado"]["tipo"] == "objeto_com"
        r, sobre = _correr("com", "get", "Quit")
        assert r.exit_code == 6
    finally:
        _correr("docs", "close", nombre, "--discard")


@pytest.mark.live
def test_run_con_script_de_solo_lectura(tmp_path):
    script = tmp_path / "leer.py"
    script.write_text(
        "def main(app, args):\n"
        "    return {'version': app.Version, 'documentos': app.Documents.Count}\n",
        encoding="utf-8",
    )
    r, sobre = _correr("run", str(script))
    assert r.exit_code == 6
    r, sobre = _correr("run", str(script), "--allow-scripts")
    assert r.exit_code == 0, sobre
    assert sobre["data"]["resultado"]["version"]
