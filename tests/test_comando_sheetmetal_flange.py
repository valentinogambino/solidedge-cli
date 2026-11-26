"""`se sheetmetal flange` y `se sheetmetal tab --sync` sobre el COM falso."""

import math

import pytest
from com_falso import (
    GEOMETRIA_CIRCULO,
    GeometriaDeCuerpoFalsa,
    VariableFalsa,
    com_error,
    con_modelado,
)

ARISTA_LARGA = 9  # recta de 50 mm sobre x, en la caja falsa de 50 x 30 x 1 mm


@pytest.fixture
def chapa(app_falsa):
    return con_modelado(app_falsa.agregar_documento("Chapa.psm", tipo=4))


@pytest.fixture
def base_sync(cli, app_falsa, chapa):
    """Chapa con la base hecha por `sheetmetal tab --sync`, sin escrituras sueltas."""
    cli("sketch", "rect", "--width", "100mm", "--height", "50mm")
    r, _ = cli("sheetmetal", "tab", "--sync")
    assert r.exit_code == 0
    app_falsa.registro.clear()
    return chapa


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


# --- tab --sync -------------------------------------------------------------------------------


def test_tab_sync_pone_el_modo_sincronico_antes_del_tab(cli, app_falsa, chapa):
    cli("sketch", "rect", "--width", "100mm", "--height", "50mm")

    r, sobre = cli("sheetmetal", "tab", "--sync")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["modo"] == "sincronico" and sobre["data"]["nombre"] == "Tab_1"
    assert chapa.modo_al_crear_base == 1 and chapa.ModelingMode == 1
    assert len(_llamadas(app_falsa, "Models.AddBaseTab")) == 1


def test_tab_sin_sync_sigue_en_modo_ordenado(cli, chapa):
    cli("sketch", "rect", "--width", "100mm", "--height", "50mm")
    r, sobre = cli("sheetmetal", "tab")
    assert r.exit_code == 0 and "modo" not in sobre["data"]
    assert chapa.modo_al_crear_base == 2 and chapa.ModelingMode == 2


def test_tab_sync_sin_perfil_da_exit_5_y_no_cambia_el_modo(cli, chapa):
    r, _ = cli("sheetmetal", "tab", "--sync")
    assert r.exit_code == 5 and chapa.ModelingMode == 2


def test_tab_sync_que_falla_restituye_el_modo(cli, chapa):
    cli("sketch", "rect", "--width", "100mm", "--height", "50mm")
    chapa.fallar("AddBaseTab", com_error(0x80004005, "Error no especificado"))

    r, _ = cli("sheetmetal", "tab", "--sync")

    assert r.exit_code == 4 and chapa.ModelingMode == 2


def test_tab_sync_dry_run(cli, app_falsa, chapa):
    r, sobre = cli.con("--dry-run", "sheetmetal", "tab", "--sync")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "sheetmetal.tab",
        "perfil": None,
        "direccion": "normal",
        "sync": True,
    }
    assert app_falsa.registro == [] and chapa.ModelingMode == 2


def test_edges_list_funciona_en_una_chapa_sincronica(cli, base_sync):
    r, sobre = cli("edges", "list")
    assert r.exit_code == 0 and sobre["data"]["cantidad"] == 12


# --- flange: camino feliz ---------------------------------------------------------------------


def test_flange_camino_feliz(cli, app_falsa, base_sync):
    r, sobre = cli(
        "sheetmetal", "flange", "--edge", str(ARISTA_LARGA), "--length", "30mm", "--units", "mm"
    )

    assert r.exit_code == 0, r.output
    datos = sobre["data"]
    assert datos["operacion"] == "brida" and datos["nombre"] == "Flange_1"
    assert datos["arista"] == ARISTA_LARGA
    assert datos["longitud_si"] == pytest.approx(0.03) and datos["longitud"] == 30.0
    assert datos["angulo"] == 90.0 and datos["direccion"] == "normal"
    assert datos["radio_si"] is None and datos["radio"] is None and datos["radio_origen"] is None
    assert datos["volumen_despues"] > datos["volumen_antes"]
    assert datos["unidades"] == {"longitud": "mm", "angulo": "deg"}
    [(_, arista, largo, lado, radio, angulo, vacios)] = _llamadas(app_falsa, "Flanges.AddSync")
    assert (arista, largo) == (ARISTA_LARGA, pytest.approx(0.03))
    # lado = seFlangeMaterialInside (4), radio vacío, DimSide = igLeft (1) y 6 vacíos
    assert lado == 4 and radio is None and angulo is None and vacios == (1, *([None] * 6))
    assert app_falsa.historial_alertas[-2:] == [False, True]


def test_flange_con_angulo_radio_y_direccion(cli, app_falsa, base_sync):
    r, sobre = cli(
        "sheetmetal",
        "flange",
        "--edge",
        "10",
        "--length",
        "1in",
        "--angle",
        "45",
        "--direction",
        "reverse",
        "--radius",
        "2mm",
        "--units",
        "in",
    )

    assert r.exit_code == 0, r.output
    datos = sobre["data"]
    assert datos["longitud"] == pytest.approx(1.0) and datos["angulo"] == 45.0
    assert datos["radio_si"] == pytest.approx(0.002) and datos["direccion"] == "reverse"
    [(_, _, largo, lado, radio, angulo, _)] = _llamadas(app_falsa, "Flanges.AddSync")
    assert largo == pytest.approx(0.0254) and lado == 5  # seFlangeMaterialOutside
    assert radio == pytest.approx(0.002) and angulo == pytest.approx(math.radians(45))


def test_flange_sin_radius_informa_el_radio_de_plegado_del_documento(cli, app_falsa, base_sync):
    base_sync.Variables.agregar(VariableFalsa("BendRadius", 0.003))

    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm", "--units", "mm")

    assert r.exit_code == 0, r.output
    datos = sobre["data"]
    assert datos["radio_si"] == pytest.approx(0.003) and datos["radio_origen"] == "documento"
    assert datos["radio"] == pytest.approx(3.0)
    [(_, _, _, _, radio, _, _)] = _llamadas(app_falsa, "Flanges.AddSync")
    assert radio is None  # Solid Edge toma ese mismo radio del documento


def test_flange_con_radius_explicito_manda_sobre_el_del_documento(cli, base_sync):
    base_sync.Variables.agregar(VariableFalsa("BendRadius", 0.003))

    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm", "--radius", "2mm")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["radio_si"] == pytest.approx(0.002)
    assert sobre["data"]["radio_origen"] == "explicito"


def test_flange_sin_units_sale_en_si(cli, base_sync):
    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "0.03")
    assert r.exit_code == 0
    assert sobre["data"]["longitud"] == pytest.approx(0.03)
    assert sobre["data"]["unidades"]["longitud"] == "m"


# --- flange: errores de uso (exit 2, sin tocar Solid Edge) ------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["--edge", "0", "--length", "30mm"],
        ["--edge", "9", "--length", "0mm"],
        ["--edge", "9", "--length", "-5mm"],
        ["--edge", "9", "--length", "treinta"],
        ["--edge", "9", "--length", "30deg"],
        ["--edge", "9"],
        ["--length", "30mm"],
        ["--edge", "9", "--length", "30mm", "--angle", "0"],
        ["--edge", "9", "--length", "30mm", "--angle", "180"],
        ["--edge", "9", "--length", "30mm", "--angle", "-10"],
        ["--edge", "9", "--length", "30mm", "--direction", "symmetric"],
        ["--edge", "9", "--length", "30mm", "--radius", "0"],
        ["--edge", "9", "--length", "30mm", "--units", "furlong"],
    ],
)
def test_flange_argumentos_invalidos_dan_exit_2(cli, app_falsa, base_sync, args):
    r, sobre = cli("sheetmetal", "flange", *args)
    assert r.exit_code == 2, sobre
    assert _llamadas(app_falsa, "Flanges.AddSync") == [] and app_falsa.escrituras == []


def test_flange_en_una_pieza_da_exit_2(cli, app_falsa):
    con_modelado(app_falsa.agregar_documento("P.par", tipo=1))
    r, sobre = cli("sheetmetal", "flange", "--edge", "1", "--length", "10mm")
    assert r.exit_code == 2 and sobre["error"]["details"]["tipo"] == "part"


def test_flange_sin_base_da_exit_2(cli, app_falsa, chapa):
    r, sobre = cli("sheetmetal", "flange", "--edge", "1", "--length", "10mm")
    assert r.exit_code == 2 and "tab --sync" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_flange_en_arista_no_recta_da_exit_2(cli, app_falsa, base_sync):
    base_sync.Models.Item(1).Body.aristas[2].Geometry = GeometriaDeCuerpoFalsa(GEOMETRIA_CIRCULO)

    r, sobre = cli("sheetmetal", "flange", "--edge", "3", "--length", "10mm")

    assert r.exit_code == 2 and "no es recta" in sobre["error"]["message"]
    assert _llamadas(app_falsa, "Flanges.AddSync") == []


def test_flange_en_arista_inexistente_da_exit_5(cli, app_falsa, base_sync):
    r, sobre = cli("sheetmetal", "flange", "--edge", "99", "--length", "10mm")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert sobre["error"]["details"]["cantidad"] == 12
    assert _llamadas(app_falsa, "Flanges.AddSync") == []


# --- flange: precondiciones y verificación ----------------------------------------------------


def test_flange_con_base_ordenada_da_exit_6(cli, app_falsa, chapa):
    cli("sketch", "rect", "--width", "100mm", "--height", "50mm")
    assert cli("sheetmetal", "tab")[0].exit_code == 0

    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm")

    assert r.exit_code == 6 and sobre["error"]["code"] == "no_soportado"
    assert sobre["error"]["details"]["causa"] == "base_ordenada"
    assert "sheetmetal tab --sync" in sobre["error"]["message"]
    assert _llamadas(app_falsa, "Flanges.AddSync") == []


def test_flange_rechazada_por_solid_edge_da_exit_4_con_causa(cli, app_falsa, base_sync):
    base_sync.brida_rechazada = True

    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm", "--angle", "179")

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
    assert "rechazó la brida" in sobre["error"]["message"]
    detalles = sobre["error"]["details"]
    assert detalles["causa"] == "brida_rechazada" and detalles["angulo"] == 179.0
    assert _llamadas(app_falsa, "Undo") == []


def test_flange_sin_efecto_se_deshace_y_da_exit_4(cli, app_falsa, base_sync):
    base_sync.brida_sin_efecto = True

    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm")

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
    detalles = sobre["error"]["details"]
    assert detalles["causa"] == "brida_sin_efecto" and detalles["deshecho"] is True
    assert len(_llamadas(app_falsa, "Undo")) == 1
    assert base_sync.Models.Item(1).Flanges.Count == 0


def test_flange_sin_efecto_y_undo_que_falla_lo_dice(cli, base_sync):
    base_sync.brida_sin_efecto = True
    base_sync.fallar("Undo", com_error(0x80004005, "Error no especificado"))

    r, sobre = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm")

    assert r.exit_code == 4 and sobre["error"]["details"]["deshecho"] is False


def test_flange_con_error_com_da_exit_4_sin_undo(cli, app_falsa, base_sync):
    base_sync.fallar("Flanges.AddSync", com_error(0x80004005, "Error no especificado"))

    r, _ = cli("sheetmetal", "flange", "--edge", "9", "--length", "30mm")

    assert r.exit_code == 4 and _llamadas(app_falsa, "Undo") == []


def test_flange_readonly_y_dry_run(cli, app_falsa, base_sync):
    r, sobre = cli.con("--readonly", "sheetmetal", "flange", "--edge", "9", "--length", "30mm")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con(
        "--dry-run", "sheetmetal", "flange", "--edge", "9", "--length", "30mm", "--angle", "60"
    )
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "sheetmetal.flange",
        "arista": 9,
        "longitud_si": pytest.approx(0.03),
        "angulo": 60.0,
        "direccion": "normal",
        "radio_si": None,
    }
    assert app_falsa.registro == []


def test_flange_dry_run_valida_los_argumentos(cli, app_falsa, base_sync):
    r, _ = cli.con(
        "--dry-run", "sheetmetal", "flange", "--edge", "9", "--length", "30mm", "--angle", "200"
    )
    assert r.exit_code == 2 and app_falsa.registro == []
