"""Pruebas contra Solid Edge abierto. No corren por defecto: `uv run pytest -m live`."""

import pytest

from se_cli.core.session import Sesion
from se_cli.core.sta import HiloSta


@pytest.mark.live
def test_conecta_a_la_instancia_abierta_y_lee_version():
    """Solo lectura: no crea ni toca documentos, no lanza Solid Edge."""
    with HiloSta() as sta:
        sesion = Sesion(sta=sta)
        datos = sesion.conectar()

        assert datos["lanzada"] is False
        assert datos["version"]
        assert sesion.llamar(lambda app: str(app.Version)) == datos["version"]
        sesion.cerrar()


@pytest.mark.live
def test_status_en_vivo_es_de_solo_lectura():
    import json

    from typer.testing import CliRunner

    from se_cli.cli import app

    r = CliRunner().invoke(app, ["--json", "--readonly", "status"])

    assert r.exit_code == 0
    sobre = json.loads(r.stdout)
    assert sobre["ok"] is True and sobre["data"]["conectado"] is True
    assert sobre["data"]["version"]


@pytest.mark.live
def test_docs_list_en_vivo_es_de_solo_lectura():
    import json

    from typer.testing import CliRunner

    from se_cli.cli import app

    r = CliRunner().invoke(app, ["--json", "--readonly", "docs", "list"])

    assert r.exit_code == 0
    data = json.loads(r.stdout)["data"]
    assert data["cantidad"] == len(data["documentos"])
