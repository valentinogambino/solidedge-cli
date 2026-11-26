"""`se material` contra Solid Edge abierto. No corre por defecto.

Crea una pieza nueva propia (sin guardar, sin diálogos), le asigna acero y la cierra descartando.
"""

import json

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@pytest.mark.live
def test_material_set_destraba_mass_sin_density():
    r, sobre = _correr("docs", "new", "part")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    try:
        assert (
            _correr("sketch", "rect", "--width", "100mm", "--height", "50mm", "--doc", nombre)[
                0
            ].exit_code
            == 0
        )
        assert _correr("extrude", "10mm", "--doc", nombre)[0].exit_code == 0

        r, sobre = _correr("mass", "--doc", nombre)
        assert r.exit_code == 2 and sobre["error"]["details"]["causa"] == "sin_material"

        r, sobre = _correr("material", "set", "steel", "--doc", nombre)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["material"] == "Steel"

        r, sobre = _correr("mass", "--doc", nombre)
        assert r.exit_code == 0, sobre
        # 100 x 50 x 10 mm de acero (7833 kg/m3, el de la biblioteca Materials).
        assert sobre["data"]["masa"] == pytest.approx(5e-5 * 7833, rel=1e-6)
    finally:
        _correr("docs", "close", nombre, "--discard")
