"""Pruebas de F3 contra Solid Edge abierto, solo lectura. No corren por defecto.

Usan el documento activo y `--readonly`: nada se modifica. Comandos que no aplican al tipo del
documento activo dan exit 2, y sin documento activo exit 5; ambos son respuestas válidas.
"""

import json

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", "--readonly", *args])
    return resultado, json.loads(resultado.stdout)


@pytest.mark.live
def test_vars_list_en_vivo_de_solo_lectura():
    r, sobre = _correr("vars", "list")
    assert r.exit_code in (0, 5)
    if r.exit_code == 0:
        assert sobre["data"]["cantidad"] == len(sobre["data"]["variables"])


@pytest.mark.live
def test_props_get_en_vivo_de_solo_lectura():
    r, sobre = _correr("props", "get")
    assert r.exit_code in (0, 5)
    if r.exit_code == 0:
        assert sobre["data"]["cantidad"] == len(sobre["data"]["propiedades"])


@pytest.mark.live
def test_mass_sin_density_en_vivo_de_solo_lectura():
    r, sobre = _correr("mass")
    assert r.exit_code in (0, 2, 5)
    if r.exit_code == 0:
        assert sobre["data"]["actualizado"] is False


@pytest.mark.live
def test_asm_tree_en_vivo_de_solo_lectura():
    r, sobre = _correr("asm", "tree", "--depth", "2")
    assert r.exit_code in (0, 2, 5)
    if r.exit_code == 0:
        assert isinstance(sobre["data"]["arbol"], list)


@pytest.mark.live
def test_features_list_en_vivo_de_solo_lectura():
    r, sobre = _correr("features", "list")
    assert r.exit_code in (0, 2, 5)
    if r.exit_code == 0:
        assert sobre["data"]["cantidad"] == len(sobre["data"]["operaciones"])
