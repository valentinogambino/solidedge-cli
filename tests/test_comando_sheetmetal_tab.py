"""`se sheetmetal tab` y la base de una chapa (`extrude`/`revolve` sin modelo), con COM falso."""

import pytest
from com_falso import con_modelado


@pytest.fixture
def chapa(app_falsa):
    return con_modelado(app_falsa.agregar_documento("Chapa.psm", tipo=4))


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


def _rect(cli):
    r, _ = cli("sketch", "rect", "--width", "100mm", "--height", "50mm")
    assert r.exit_code == 0


def test_tab_camino_feliz(cli, app_falsa, chapa):
    _rect(cli)

    r, sobre = cli("sheetmetal", "tab")

    assert r.exit_code == 0, r.output
    assert sobre["data"] == {
        "operacion": "tab",
        "nombre": "Tab_1",
        "direccion": "normal",
        "perfil": 1,
        "modelo_base": True,
        "volumen_si": pytest.approx(0.1 * 0.05 * 0.001),
    }
    assert _llamadas(app_falsa, "Models.AddBaseTab") == [("Models.AddBaseTab", 2)]  # igRight
    assert app_falsa.historial_alertas[-2:] == [False, True]  # sketch y tab apagan alertas


def test_tab_reverse_y_perfil_elegido(cli, app_falsa, chapa):
    _rect(cli)
    _rect(cli)

    r, sobre = cli("sheetmetal", "tab", "--direction", "reverse", "--profile", "1")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["perfil"] == 1 and sobre["data"]["direccion"] == "reverse"
    assert _llamadas(app_falsa, "Models.AddBaseTab") == [("Models.AddBaseTab", 1)]  # igLeft


def test_tab_symmetric_o_invalida_da_exit_2_sin_com(cli, app_falsa, chapa):
    for direccion in ("symmetric", "arriba"):
        r, sobre = cli("sheetmetal", "tab", "--direction", direccion)
        assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_tab_con_modelo_base_da_exit_2(cli, app_falsa, chapa):
    _rect(cli)
    assert cli("sheetmetal", "tab")[0].exit_code == 0
    _rect(cli)

    r, sobre = cli("sheetmetal", "tab")

    assert r.exit_code == 2 and "solo crea la base" in sobre["error"]["message"]
    assert len(_llamadas(app_falsa, "Models.AddBaseTab")) == 1


def test_tab_sin_perfil_da_exit_5(cli, app_falsa, chapa):
    r, sobre = cli("sheetmetal", "tab")
    assert r.exit_code == 5 and app_falsa.escrituras == []


def test_tab_en_una_pieza_o_en_sincronico_da_exit_2(cli, app_falsa):
    con_modelado(app_falsa.agregar_documento("P.par", tipo=1))
    r, sobre = cli("sheetmetal", "tab")
    assert r.exit_code == 2 and sobre["error"]["details"]["tipo"] == "part"

    con_modelado(app_falsa.agregar_documento("S.psm", tipo=4), modo=1)
    r, sobre = cli("sheetmetal", "tab")
    assert r.exit_code == 2 and "sincrónico" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_tab_readonly_y_dry_run(cli, app_falsa, chapa):
    r, sobre = cli.con("--readonly", "sheetmetal", "tab")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con("--dry-run", "sheetmetal", "tab", "--profile", "ProfileSet_2")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "sheetmetal.tab",
        "perfil": 2,
        "direccion": "normal",
    }
    assert app_falsa.registro == []


# --- La base de una chapa no es una protrusión de pieza ---------------------------------------


def test_extrude_como_base_de_una_chapa_da_exit_6_con_hint(cli, app_falsa, chapa):
    _rect(cli)

    r, sobre = cli("extrude", "1mm")

    assert r.exit_code == 6 and sobre["error"]["code"] == "no_soportado"
    assert "sheetmetal tab" in sobre["error"]["details"]["hint"]
    assert sobre["error"]["details"]["modelo_base"] is False
    assert _llamadas(app_falsa, "Models.AddFiniteExtrudedProtrusion") == []


def test_revolve_como_base_de_una_chapa_da_exit_6_sin_tocar_el_perfil(cli, app_falsa, chapa):
    r, _ = cli("sketch", "rect", "--width", "10mm", "--height", "10mm", "--at", "10mm,0mm")
    assert r.exit_code == 0
    escrituras = len(app_falsa.escrituras)

    r, sobre = cli("revolve", "360deg", "--axis", "y")

    assert r.exit_code == 6 and "sheetmetal tab" in sobre["error"]["details"]["hint"]
    assert len(app_falsa.escrituras) == escrituras  # ni el eje se agregó al perfil


def test_sobre_un_tab_extrude_hole_y_corte_siguen_funcionando(cli, app_falsa, chapa):
    _rect(cli)
    assert cli("sheetmetal", "tab")[0].exit_code == 0

    cli("sketch", "circle", "--diameter", "10mm", "--at", "50mm,25mm")
    r, sobre = cli("extrude", "5mm")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["modelo_base"] is False

    r, sobre = cli("hole", "--at", "20mm,20mm", "--diameter", "4mm", "--through")
    assert r.exit_code == 0, r.output

    cli("sketch", "circle", "--diameter", "4mm", "--at", "80mm,20mm")
    r, sobre = cli("extrude", "1mm", "--cut")
    assert r.exit_code == 0, r.output


def test_extrude_como_base_de_una_pieza_sigue_igual(cli, app_falsa):
    con_modelado(app_falsa.agregar_documento("P.par", tipo=1))
    _rect(cli)
    r, sobre = cli("extrude", "10mm")
    assert r.exit_code == 0 and sobre["data"]["modelo_base"] is True
