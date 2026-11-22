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
