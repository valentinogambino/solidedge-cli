"""Errores de uso de Click/Typer: con `--json` salen como sobre `{ok, data, error}`, exit 2."""

import json

import pytest
from typer.testing import CliRunner

from se_cli.cli import app

CASOS = {
    "subcomando_inexistente": ["noexiste"],
    "subgrupo_inexistente": ["docs", "noexiste"],
    "argumento_faltante": ["docs", "open"],
    "opcion_desconocida": ["docs", "list", "--no-existe"],
    "valor_invalido": ["asm", "tree", "--depth", "abc"],
}


def invocar(*args: str):
    return CliRunner().invoke(app, list(args))


@pytest.mark.parametrize("args", CASOS.values(), ids=CASOS.keys())
def test_error_de_uso_con_json_es_un_sobre(args):
    r = invocar("--json", *args)

    assert r.exit_code == 2
    lineas = r.stdout.splitlines()
    assert len(lineas) == 1
    sobre = json.loads(lineas[0])
    assert sobre["ok"] is False
    assert sobre["data"] is None
    assert sobre["error"]["code"] == "argumento_invalido"
    assert sobre["error"]["message"]
    assert "\x1b" not in r.stdout and "╭" not in r.stdout


def test_json_puede_ir_en_cualquier_posicion():
    r = invocar("docs", "noexiste", "--json")

    assert r.exit_code == 2
    assert json.loads(r.stdout)["error"]["code"] == "argumento_invalido"


def test_mensaje_es_el_de_click():
    sobre = json.loads(invocar("--json", "docs", "noexiste").stdout)

    assert "No such command" in sobre["error"]["message"]


@pytest.mark.parametrize("args", [["noexiste"], ["docs", "open"]])
def test_error_de_uso_sin_json_sigue_siendo_texto(args):
    r = invocar(*args)

    assert r.exit_code == 2
    with pytest.raises(json.JSONDecodeError):
        json.loads(r.output)


def test_help_y_version_no_cambian_con_json():
    ayuda = invocar("--json", "--help")
    version = invocar("--json", "--version")

    assert ayuda.exit_code == 0 and "Usage" in ayuda.stdout
    assert version.exit_code == 0 and version.stdout.strip()
