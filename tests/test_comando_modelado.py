"""`se sketch`, `se extrude`, `se revolve` y `se hole` sobre el COM falso."""

import math

import pytest
from com_falso import con_modelado


@pytest.fixture
def pieza(app_falsa):
    return con_modelado(app_falsa.agregar_documento("Part1.par", tipo=1))


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


def _caja(cli):
    cli("sketch", "rect", "--width", "50mm", "--height", "30mm")
    return cli("extrude", "10mm")


# --- sketch ---------------------------------------------------------------------------------


def test_sketch_rect_camino_feliz(cli, app_falsa, pieza):
    r, sobre = cli("sketch", "rect", "--plane", "top", "--width", "50mm", "--height", "30mm")

    assert r.exit_code == 0, r.output
    assert sobre["data"] == {
        "perfil": 1,
        "plano": "top",
        "plano_indice": 1,
        "tipo": "rect",
        "dimensiones_si": {"ancho": 0.05, "alto": 0.03, "x": 0.0, "y": 0.0, "centrado": False},
        "valido": True,
        "codigo_end": -103,
    }
    lineas = _llamadas(app_falsa, "Lines2d.AddBy2Points")
    assert [c[1:] for c in lineas] == [
        (0.0, 0.0, 0.05, 0.0),
        (0.05, 0.0, 0.05, 0.03),
        (0.05, 0.03, 0.0, 0.03),
        (0.0, 0.03, 0.0, 0.0),
    ]
    assert _llamadas(app_falsa, "Profiles.Add") == [("Profiles.Add", "RefPlane_1")]
    assert app_falsa.historial_alertas == [False, True]


@pytest.mark.parametrize(
    ("plano", "indice", "nombre"),
    [("top", 1, "top"), ("right", 2, "right"), ("front", 3, "front"), ("3", 3, "front")],
)
def test_sketch_planos(cli, pieza, plano, indice, nombre):
    r, sobre = cli("sketch", "rect", "--plane", plano, "--width", "1mm", "--height", "1mm")
    assert r.exit_code == 0
    assert sobre["data"]["plano_indice"] == indice and sobre["data"]["plano"] == nombre


def test_sketch_rect_centrado_y_en(cli, app_falsa, pieza):
    r, sobre = cli(
        "sketch", "rect", "--width", "20mm", "--height", "10mm", "--at", "5mm,-2mm", "--centered"
    )
    assert r.exit_code == 0, r.output
    primera = _llamadas(app_falsa, "Lines2d.AddBy2Points")[0]
    assert primera[1:3] == pytest.approx((-0.005, -0.007))
    assert sobre["data"]["dimensiones_si"]["centrado"] is True


def test_sketch_circle_radio_y_diametro(cli, app_falsa, pieza):
    r, sobre = cli("sketch", "circle", "--diameter", "8mm", "--at", "25mm,15mm")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["tipo"] == "circulo" and sobre["data"]["codigo_end"] == 0
    assert sobre["data"]["dimensiones_si"] == {
        "radio": 0.004,
        "diametro": 0.008,
        "x": 0.025,
        "y": 0.015,
    }
    r, sobre = cli("sketch", "circle", "--radius", "5mm")
    assert sobre["data"]["perfil"] == 2 and sobre["data"]["dimensiones_si"]["radio"] == 0.005


@pytest.mark.parametrize(
    "args",
    [
        ["rect", "--width", "0", "--height", "5mm"],
        ["rect", "--width", "5deg", "--height", "5mm"],
        ["rect", "--width", "5mm", "--height", "5mm", "--plane", "arriba"],
        ["rect", "--width", "5mm", "--height", "5mm", "--at", "1mm"],
        ["circle"],
        ["circle", "--radius", "1mm", "--diameter", "2mm"],
        ["circle", "--radius=-1mm"],
    ],
)
def test_sketch_argumentos_invalidos_dan_exit_2(cli, app_falsa, pieza, args):
    r, sobre = cli("sketch", *args)
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_sketch_plano_inexistente_da_exit_2(cli, app_falsa, pieza):
    r, sobre = cli("sketch", "rect", "--width", "1mm", "--height", "1mm", "--plane", "9")
    assert r.exit_code == 2 and "planos de referencia" in sobre["error"]["message"]
    assert _llamadas(app_falsa, "Lines2d.AddBy2Points") == []


def test_sketch_en_modo_sincronico_da_exit_2(cli, app_falsa):
    con_modelado(app_falsa.agregar_documento("S.par", tipo=1), modo=1)
    r, sobre = cli("sketch", "rect", "--width", "1mm", "--height", "1mm")
    assert r.exit_code == 2 and "sincrónico" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_sketch_en_un_draft_da_exit_2(cli, app_falsa):
    app_falsa.agregar_documento("D.dft", tipo=2)
    r, _ = cli("sketch", "rect", "--width", "1mm", "--height", "1mm")
    assert r.exit_code == 2


def test_perfil_cerrado_con_codigo_inesperado_da_exit_4(cli, pieza):
    pieza.codigo_end = -5
    r, sobre = cli("sketch", "rect", "--width", "1mm", "--height", "1mm")
    assert r.exit_code == 4 and sobre["error"]["details"]["codigo_end"] == -5


# --- extrude --------------------------------------------------------------------------------


def test_extrude_crea_el_modelo_base(cli, app_falsa, pieza):
    cli("sketch", "rect", "--width", "50mm", "--height", "30mm")

    r, sobre = cli("extrude", "10mm")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["operacion"] == "extrusion"
    assert sobre["data"]["nombre"] == "ExtrudedProtrusion_1"
    assert sobre["data"]["distancia_si"] == 0.01 and sobre["data"]["modelo_base"] is True
    assert sobre["data"]["perfil"] == 1 and sobre["data"]["direccion"] == "normal"
    assert sobre["data"]["volumen_si"] == pytest.approx(0.05 * 0.03 * 0.01)
    assert _llamadas(app_falsa, "Models.AddFiniteExtrudedProtrusion") == [
        ("Models.AddFiniteExtrudedProtrusion", 1, 2, 0.01)
    ]


def test_segunda_extrusion_se_suma_al_modelo(cli, app_falsa, pieza):
    _caja(cli)
    cli("sketch", "rect", "--plane", "right", "--width", "10mm", "--height", "10mm")

    r, sobre = cli("extrude", "5mm", "--direction", "symmetric")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["nombre"] == "ExtrudedProtrusion_2"
    assert sobre["data"]["modelo_base"] is False
    assert _llamadas(app_falsa, "ExtrudedProtrusions.AddFiniteMulti") == [
        ("ExtrudedProtrusions.AddFiniteMulti", 1, 3, 0.005)
    ]
    assert len(_llamadas(app_falsa, "Models.AddFiniteExtrudedProtrusion")) == 1


def test_extrude_usa_el_ultimo_perfil_o_el_indicado(cli, app_falsa, pieza):
    cli("sketch", "rect", "--width", "10mm", "--height", "10mm")
    cli("sketch", "rect", "--width", "40mm", "--height", "40mm")

    r, sobre = cli("extrude", "1mm")
    assert sobre["data"]["perfil"] == 2
    r, sobre = cli("extrude", "1mm", "--profile", "ProfileSet_1")
    assert r.exit_code == 0 and sobre["data"]["perfil"] == 1


def test_extrude_sin_perfiles_da_exit_5(cli, app_falsa, pieza):
    r, sobre = cli("extrude", "10mm")
    assert r.exit_code == 5 and "se sketch" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_extrude_perfil_inexistente_da_exit_5_e_invalido_exit_2(cli, pieza):
    cli("sketch", "rect", "--width", "10mm", "--height", "10mm")
    r, _ = cli("extrude", "1mm", "--profile", "4")
    assert r.exit_code == 5
    r, _ = cli("extrude", "1mm", "--profile", "abc")
    assert r.exit_code == 2


@pytest.mark.parametrize(
    "args",
    [["0"], ["10deg"], ["1mm", "--direction", "arriba"], ["--", "-1mm"]],
)
def test_extrude_argumentos_invalidos(cli, pieza, args):
    cli("sketch", "rect", "--width", "10mm", "--height", "10mm")
    r, _ = cli("extrude", *args)
    assert r.exit_code == 2


def test_extrude_cut_resta_volumen(cli, app_falsa, pieza):
    _caja(cli)
    cli("sketch", "circle", "--radius", "4mm", "--at", "25mm,15mm")

    r, sobre = cli("extrude", "5mm", "--cut")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["operacion"] == "corte" and sobre["data"]["nombre"] == "ExtrudedCutout_1"
    quitado = math.pi * 0.004**2 * 0.005
    assert sobre["data"]["volumen_quitado_si"] == pytest.approx(quitado)
    assert sobre["data"]["volumen_si"] == pytest.approx(0.05 * 0.03 * 0.01 - quitado)


def test_cut_que_no_toca_material_se_deshace_con_exit_2(cli, app_falsa, pieza):
    _caja(cli)
    cli("sketch", "circle", "--radius", "4mm")

    r, sobre = cli("extrude", "5mm", "--cut", "--direction", "reverse")

    assert r.exit_code == 2 and "no quitó material" in sobre["error"]["message"]
    assert _llamadas(app_falsa, "Feature.Delete") == [("Feature.Delete", "ExtrudedCutout_1")]
    assert pieza.Models.Item(1).ExtrudedCutouts.Count == 0


def test_cut_sin_modelo_base_da_exit_2(cli, app_falsa, pieza):
    cli("sketch", "circle", "--radius", "4mm")
    r, sobre = cli("extrude", "5mm", "--cut")
    assert r.exit_code == 2 and "modelo base" in sobre["error"]["message"]


def test_modelado_readonly_y_dry_run(cli, app_falsa, pieza):
    r, sobre = cli.con("--readonly", "sketch", "rect", "--width", "1mm", "--height", "1mm")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con("--dry-run", "sketch", "rect", "--width", "50mm", "--height", "30mm")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "sketch.rect",
        "plano": "top",
        "plano_indice": 1,
        "ancho_si": 0.05,
        "alto_si": 0.03,
        "x_si": 0.0,
        "y_si": 0.0,
        "centrado": False,
    }
    for comando in (
        ["extrude", "10mm"],
        ["revolve", "--axis", "y"],
        ["hole", "--at", "0,0", "--diameter", "1mm", "--through"],
        ["sketch", "circle", "--radius", "1mm"],
    ):
        assert cli.con("--readonly", *comando)[0].exit_code == 6
        r, sobre = cli.con("--dry-run", *comando)
        assert r.exit_code == 0 and sobre["data"]["dry_run"] is True
    assert app_falsa.registro == []


def test_modelado_sin_instancia_da_exit_3(cli_sin_instancia):
    for comando in (
        ["sketch", "rect", "--width", "1mm", "--height", "1mm"],
        ["extrude", "1mm"],
        ["revolve", "--axis", "x"],
        ["hole", "--at", "0,0", "--diameter", "1mm", "--through"],
    ):
        r, sobre = cli_sin_instancia(*comando)
        assert r.exit_code == 3 and sobre["error"]["code"] == "no_conectado"


# --- revolve --------------------------------------------------------------------------------


def test_revolve_crea_el_modelo_y_agrega_el_eje(cli, app_falsa, pieza):
    cli(
        "sketch", "rect", "--plane", "front", "--width", "20mm", "--height", "40mm",
        "--at", "10mm,0",
    )  # fmt: skip

    r, sobre = cli("revolve", "--axis", "y")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["operacion"] == "revolucion"
    assert sobre["data"]["nombre"] == "RevolvedProtrusion_1"
    assert sobre["data"]["angulo_si"] == pytest.approx(2 * math.pi)
    assert sobre["data"]["eje"] == "y" and sobre["data"]["modelo_base"] is True
    assert sobre["data"]["volumen_si"] == pytest.approx(math.pi * (0.03**2 - 0.01**2) * 0.04)
    eje = _llamadas(app_falsa, "Lines2d.AddBy2Points")[-1]
    assert eje[1:] == (0.0, -0.5, 0.0, 0.5)
    assert _llamadas(app_falsa, "Profile.ToggleConstruction") != []
    assert _llamadas(app_falsa, "Models.AddFiniteRevolvedProtrusion")[0][1:4] == (1, "y", 2)


def test_segunda_revolucion_con_angulo_y_eje_x(cli, app_falsa, pieza):
    cli("sketch", "rect", "--width", "20mm", "--height", "40mm", "--at", "10mm,0")
    cli("revolve", "--axis", "y")
    cli("sketch", "rect", "--width", "10mm", "--height", "10mm", "--at", "0,10mm")

    r, sobre = cli("revolve", "90deg", "--axis", "x")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["modelo_base"] is False and sobre["data"]["eje"] == "x"
    assert sobre["data"]["angulo_si"] == pytest.approx(math.pi / 2)
    assert _llamadas(app_falsa, "RevolvedProtrusions.AddFiniteMulti")[0][1:3] == (1, "x")


@pytest.mark.parametrize(
    "args", [["--axis", "z"], ["0deg", "--axis", "x"], ["400deg", "--axis", "x"]]
)
def test_revolve_argumentos_invalidos(cli, pieza, args):
    cli("sketch", "rect", "--width", "10mm", "--height", "10mm")
    r, _ = cli("revolve", *args)
    assert r.exit_code == 2


def test_revolve_sin_eje_da_exit_2(cli, pieza):
    r, _ = cli("revolve")
    assert r.exit_code == 2


# --- hole -----------------------------------------------------------------------------------


def test_hole_finito_y_pasante(cli, app_falsa, pieza):
    _caja(cli)

    r, sobre = cli("hole", "--at", "10mm,10mm", "--diameter", "4mm", "--depth", "5mm")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["nombre"] == "ExtrudedCutout_1" and sobre["data"]["pasante"] is False
    assert sobre["data"]["volumen_quitado_si"] == pytest.approx(math.pi * 0.002**2 * 0.005)
    assert sobre["data"]["plano"] == "top" and sobre["data"]["perfil"] == 2

    r, sobre = cli("hole", "--at", "30mm,10mm", "--diameter", "4mm", "--through")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["pasante"] is True and sobre["data"]["profundidad_si"] is None
    assert sobre["data"]["volumen_quitado_si"] == pytest.approx(math.pi * 0.002**2 * 0.01)
    assert _llamadas(app_falsa, "ExtrudedCutouts.AddThroughAllMulti") == [
        ("ExtrudedCutouts.AddThroughAllMulti", 1, 2)
    ]
    assert app_falsa.historial_alertas == [False, True] * 4


def test_hole_sin_modelo_base_da_exit_2(cli, app_falsa, pieza):
    r, sobre = cli("hole", "--at", "0,0", "--diameter", "4mm", "--through")
    assert r.exit_code == 2 and "modelo base" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_hole_que_no_corta_se_deshace(cli, app_falsa, pieza):
    _caja(cli)
    r, sobre = cli(
        "hole", "--at", "0,0", "--diameter", "4mm", "--depth", "5mm", "--direction", "reverse"
    )
    assert r.exit_code == 2 and "no quitó material" in sobre["error"]["message"]
    assert len(_llamadas(app_falsa, "Feature.Delete")) == 1


@pytest.mark.parametrize(
    "args",
    [
        ["--at", "0,0", "--diameter", "4mm"],
        ["--at", "0,0", "--diameter", "4mm", "--depth", "1mm", "--through"],
        ["--at", "0,0", "--diameter", "4mm", "--through", "--direction", "symmetric"],
        ["--at", "0", "--diameter", "4mm", "--through"],
        ["--at", "0,0", "--diameter", "0", "--through"],
        ["--at", "0,0", "--diameter", "4mm", "--depth=-1mm"],
    ],
)
def test_hole_argumentos_invalidos(cli, app_falsa, pieza, args):
    _caja(cli)
    r, _ = cli("hole", *args)
    assert r.exit_code == 2
