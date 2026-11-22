"""`se connect`, `se status` y `se quit` sobre el COM falso."""

import pytest
from com_falso import AplicacionFalsa, FabricaApp
from conftest import Cli

from se_cli import ejecucion
from se_cli.core.session import Sesion


def assert_sobre(sobre, *, ok):
    assert set(sobre) == {"ok", "data", "error"}
    assert sobre["ok"] is ok
    assert (sobre["error"] is None) is ok
    assert (sobre["data"] is not None) is ok


def test_connect_camino_feliz(cli):
    r, sobre = cli("connect")

    assert r.exit_code == 0
    assert_sobre(sobre, ok=True)
    assert sobre["data"] == {"version": "226.00.00.00", "nombre": "Solid Edge", "lanzada": False}


def test_connect_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("connect")

    assert r.exit_code == 3
    assert_sobre(sobre, ok=False)
    assert sobre["error"]["code"] == "no_conectado"
    assert cli_sin_instancia.lanzador.llamadas == 0


def test_connect_launch_lanza_solo_si_no_hay_instancia(monkeypatch, sta):
    lanzador = FabricaApp(AplicacionFalsa(version="226.99"))
    sesion = Sesion(sta=sta, proveedor=FabricaApp(), lanzador=lanzador, sleep=lambda _: None)
    monkeypatch.setattr(ejecucion, "crear_sesion", lambda: sesion)
    r, sobre = Cli()("connect", "--launch")

    assert r.exit_code == 0
    assert sobre["data"]["lanzada"] is True
    assert lanzador.llamadas == 1


def test_connect_launch_bloqueado_por_readonly_y_dry_run(cli_sin_instancia):
    r, sobre = cli_sin_instancia("--readonly", "connect", "--launch")
    assert r.exit_code == 6
    assert sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli_sin_instancia("--dry-run", "connect", "--launch")
    assert r.exit_code == 0
    assert sobre["data"]["dry_run"] is True

    assert cli_sin_instancia.lanzador.llamadas == 0
    assert cli_sin_instancia.proveedor.llamadas == 0


def test_connect_sin_launch_funciona_con_readonly(cli):
    r, _ = cli("--readonly", "connect")
    assert r.exit_code == 0


def test_status_camino_feliz(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    app_falsa.agregar_documento("B.asm", ruta="C:\\p\\B.asm", tipo=3)

    r, sobre = cli("status")

    assert r.exit_code == 0
    assert_sobre(sobre, ok=True)
    assert sobre["data"] == {
        "conectado": True,
        "version": "226.00.00.00",
        "nombre": "Solid Edge",
        "visible": True,
        "documentos": 2,
        "activo": "B.asm",
    }
    assert app_falsa.escrituras == []


def test_status_sin_documentos(cli):
    r, sobre = cli("status")
    assert r.exit_code == 0
    assert sobre["data"]["documentos"] == 0
    assert sobre["data"]["activo"] is None


def test_status_sin_instancia_no_es_error(cli_sin_instancia):
    r, sobre = cli_sin_instancia("status")

    assert r.exit_code == 0
    assert_sobre(sobre, ok=True)
    assert sobre["data"]["conectado"] is False
    assert sobre["data"]["activo"] is None
    assert cli_sin_instancia.lanzador.llamadas == 0


def test_status_con_readonly(cli):
    r, _ = cli("--readonly", "status")
    assert r.exit_code == 0


def test_status_modo_humano(cli):
    r, _ = cli("status", como_json=False)
    assert r.exit_code == 0
    assert "Solid Edge" in r.stdout


def test_quit_sin_yes_no_cierra(cli, app_falsa):
    r, sobre = cli("quit")

    assert r.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_quit_con_yes(cli, app_falsa):
    r, sobre = cli("quit", "--yes")

    assert r.exit_code == 0
    assert_sobre(sobre, ok=True)
    assert sobre["data"]["cerrada"] is True
    assert app_falsa.salio is True


def test_quit_se_niega_con_documentos_sucios(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)

    r, sobre = cli("quit", "--yes")

    assert r.exit_code == 6
    assert sobre["error"]["code"] == "solo_lectura"
    assert "A.par" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_quit_con_discard_descarta_y_sale(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)

    r, sobre = cli("quit", "--yes", "--discard")

    assert r.exit_code == 0
    assert sobre["data"]["descartados"] == ["A.par"]
    assert app_falsa.salio is True


def test_quit_bloqueado_por_readonly(cli, app_falsa):
    r, sobre = cli("--readonly", "quit", "--yes")

    assert r.exit_code == 6
    assert sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.escrituras == []
    assert app_falsa.registro == []


def test_quit_dry_run(cli, app_falsa):
    r, sobre = cli("--dry-run", "quit", "--yes")

    assert r.exit_code == 0
    assert sobre["data"] == {"dry_run": True, "accion": "quit", "discard": False}
    assert app_falsa.registro == []
    assert app_falsa.salio is False


@pytest.mark.parametrize("comando", [["status"], ["connect"]])
def test_sesion_se_suelta_al_terminar(cli, sesion, comando):
    cli(*comando)
    assert sesion._app is None
