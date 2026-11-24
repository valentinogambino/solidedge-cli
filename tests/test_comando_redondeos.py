"""`se edges list`, `se round` y `se chamfer` sobre el COM falso (caja de 50x30x20 mm)."""

import math

import pytest
from com_falso import (
    GEOMETRIA_CILINDRO,
    GEOMETRIA_CIRCULO,
    GEOMETRIA_ELIPSE,
    com_error,
    con_modelado,
)

from se_cli.core import redondeos
from se_cli.core.errors import ArgumentoInvalido


@pytest.fixture
def pieza(app_falsa):
    return con_modelado(app_falsa.agregar_documento("Part1.par", tipo=1))


@pytest.fixture
def caja(cli, pieza):
    """Caja de 50x30x20 mm hecha por el CLI, sin escrituras sueltas en el registro."""
    cli("sketch", "rect", "--width", "50mm", "--height", "30mm")
    r, _ = cli("extrude", "20mm")
    assert r.exit_code == 0
    pieza.registro.clear()
    return pieza


def _llamadas(doc, que):
    return [c for c in doc.registro if c[0] == que]


# --- parsear_aristas ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("all", "all"),
        (" ALL ", "all"),
        ("3", [3]),
        ("1,3,5", [1, 3, 5]),
        ("5, 1,3,1", [1, 3, 5]),
        ("1-4", [1, 2, 3, 4]),
        ("1-3,7,6-6", [1, 2, 3, 6, 7]),
    ],
)
def test_parsear_aristas(texto, esperado):
    assert redondeos.parsear_aristas(texto) == esperado


@pytest.mark.parametrize("texto", ["", "0", "-1", "a", "1,,2", "4-2", "0-3", "1-", "1;2", "all,1"])
def test_parsear_aristas_invalidas(texto):
    with pytest.raises(ArgumentoInvalido):
        redondeos.parsear_aristas(texto)


# --- edges list -----------------------------------------------------------------------------


def test_edges_list_da_las_doce_aristas_de_la_caja(cli, app_falsa, caja):
    r, sobre = cli("edges", "list")

    assert r.exit_code == 0, r.output
    data = sobre["data"]
    assert data["cantidad"] == 12 and data["cantidad_caras"] == 6
    assert [a["indice"] for a in data["aristas"]] == list(range(1, 13))
    assert data["unidades"] == {"longitud": "m"}
    primera = data["aristas"][0]
    assert primera["tipo"] == "linea"
    assert primera["longitud"] == pytest.approx(0.02)
    assert primera["inicio"] == pytest.approx([0.0, 0.0, 0.0])
    assert primera["fin"] == pytest.approx([0.0, 0.0, 0.02])
    assert primera["caras"] == [{"indice": 1, "tipo": "plano"}, {"indice": 3, "tipo": "plano"}]
    longitudes = sorted(round(a["longitud"], 6) for a in data["aristas"])
    assert longitudes == [0.02] * 4 + [0.03] * 4 + [0.05] * 4
    assert app_falsa.escrituras == []


def test_edges_list_en_las_unidades_pedidas(cli, caja):
    r, sobre = cli("edges", "list", "--units", "mm")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["unidades"] == {"longitud": "mm"}
    arista = sobre["data"]["aristas"][0]
    assert arista["longitud"] == 20.0 and arista["fin"] == [0.0, 0.0, 20.0]

    r, sobre = cli("edges", "list", "--units", "in")
    assert sobre["data"]["aristas"][0]["longitud"] == pytest.approx(20 / 25.4)


def test_edges_list_distingue_linea_arco_circulo_y_otra(cli, caja):
    aristas = caja.Models.Item(1).Body.aristas
    aristas[1].Geometry.Type = GEOMETRIA_CIRCULO  # abierta: arco
    aristas[2].Geometry.Type = GEOMETRIA_CIRCULO
    aristas[2].IsClosed = True
    aristas[3].Geometry.Type = GEOMETRIA_ELIPSE
    caja.Models.Item(1).Body.caras[0].Geometry.Type = GEOMETRIA_CILINDRO

    r, sobre = cli("edges", "list")
    assert r.exit_code == 0, r.output
    tipos = [a["tipo"] for a in sobre["data"]["aristas"][:4]]
    assert tipos == ["linea", "arco", "circulo", "otra"]
    assert sobre["data"]["aristas"][0]["caras"][0] == {"indice": 1, "tipo": "cilindro"}


def test_edges_list_deja_en_none_lo_que_la_api_no_da(cli, caja):
    arista = caja.Models.Item(1).Body.aristas[0]

    def sin_datos(*_):
        raise com_error(0x80004005, "Error no especificado")

    arista.GetEndPoints = sin_datos
    arista.GetParamExtents = sin_datos
    arista.GetFaces = sin_datos

    r, sobre = cli("edges", "list")
    assert r.exit_code == 0, r.output
    primera = sobre["data"]["aristas"][0]
    assert primera["longitud"] is None and primera["inicio"] is None and primera["fin"] is None
    assert primera["caras"] == []
    assert sobre["data"]["aristas"][1]["longitud"] is not None


def test_edges_list_elige_documento(cli, app_falsa, caja):
    con_modelado(app_falsa.agregar_documento("Otra.par", tipo=1))
    r, sobre = cli("edges", "list", "--doc", "Part1.par")
    assert r.exit_code == 0 and sobre["data"]["cantidad"] == 12


@pytest.mark.parametrize("comando", [["edges", "list"], ["round", "1mm", "--edges", "all"]])
def test_comandos_de_aristas_en_un_draft_o_ensamble_dan_exit_2(cli, app_falsa, comando):
    app_falsa.agregar_documento("D.dft", tipo=2)
    r, sobre = cli(*comando)
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    app_falsa.agregar_documento("E.asm", tipo=3)
    assert cli(*comando)[0].exit_code == 2


def test_chapa_tambien_se_acepta(cli, app_falsa):
    chapa = con_modelado(app_falsa.agregar_documento("C.psm", tipo=4))
    cli("sketch", "rect", "--width", "50mm", "--height", "30mm")
    cli("extrude", "20mm")
    r, sobre = cli("edges", "list")
    assert r.exit_code == 0 and sobre["data"]["cantidad"] == 12
    r, sobre = cli("round", "1mm", "--edges", "1")
    assert r.exit_code == 0, r.output
    assert _llamadas(chapa, "Rounds.Add")


def test_edges_list_sin_modelo_o_en_modo_sincronico_da_exit_2(cli, app_falsa, pieza):
    r, sobre = cli("edges", "list")
    assert r.exit_code == 2 and "modelo" in sobre["error"]["message"]
    con_modelado(app_falsa.agregar_documento("S.par", tipo=1), modo=1)
    r, sobre = cli("edges", "list")
    assert r.exit_code == 2 and "sincrónico" in sobre["error"]["message"]


def test_edges_list_con_unidad_invalida_da_exit_2(cli, app_falsa, caja):
    r, _ = cli("edges", "list", "--units", "parsecs")
    assert r.exit_code == 2


# --- round ----------------------------------------------------------------------------------


def test_round_sobre_algunas_aristas(cli, caja):
    r, sobre = cli("round", "2mm", "--edges", "1,3,5")

    assert r.exit_code == 0, r.output
    assert _llamadas(caja, "Rounds.Add") == [("Rounds.Add", 3, (1, 3, 5), (0.002,) * 3)]
    data = sobre["data"]
    assert data["operacion"] == "redondeo"
    assert data["nombre"] == "Round_1" and data["indice"] == 2
    assert data["cantidad_aristas"] == 3 and data["aristas"] == [1, 3, 5]
    assert data["radio"] == pytest.approx(0.002) and data["unidades"] == {"longitud": "m"}
    assert data["estado"] == "ok"
    assert data["volumen_quitado_si"] == pytest.approx(3e-9)
    assert data["volumen_si"] == pytest.approx(0.05 * 0.03 * 0.02 - 3e-9)


def test_round_aparece_en_features_list(cli, caja):
    cli("round", "2mm", "--edges", "1")
    r, sobre = cli("features", "list")
    assert [o["nombre"] for o in sobre["data"]["operaciones"]] == [
        "ExtrudedProtrusion_1",
        "Round_1",
    ]


def test_round_all_y_rangos(cli, caja):
    r, sobre = cli("round", "1mm", "--edges", "all")
    assert r.exit_code == 0 and sobre["data"]["cantidad_aristas"] == 12
    r, sobre = cli("round", "1mm", "--edges", "1-4,6")
    assert r.exit_code == 0 and sobre["data"]["aristas"] == [1, 2, 3, 4, 6]
    assert _llamadas(caja, "Rounds.Add")[-1][2] == (1, 2, 3, 4, 6)


def test_round_en_unidades_pedidas(cli, caja):
    r, sobre = cli("round", "0.1in", "--edges", "2", "--units", "mm")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["radio"] == pytest.approx(2.54)
    assert sobre["data"]["unidades"] == {"longitud": "mm"}
    assert _llamadas(caja, "Rounds.Add")[0][3] == (pytest.approx(0.00254),)


def test_round_sin_unidad_es_metros(cli, caja):
    r, _ = cli("round", "0.002", "--edges", "1")
    assert r.exit_code == 0
    assert _llamadas(caja, "Rounds.Add")[0][3] == (0.002,)


def test_round_informa_lo_que_leyo_de_solid_edge(cli, caja):
    caja.sin_valores = False
    r, sobre = cli("round", "2mm", "--edges", "1")
    assert sobre["data"]["radio"] == pytest.approx(0.002)
    caja.sin_valores = True
    r, sobre = cli("round", "3mm", "--edges", "1")
    assert r.exit_code == 0 and sobre["data"]["radio"] == pytest.approx(0.003)


@pytest.mark.parametrize(
    "args",
    [
        ["0", "--edges", "1"],
        ["0mm", "--edges", "1"],
        ["-2", "--edges", "1"],
        ["2deg", "--edges", "1"],
        ["abc", "--edges", "1"],
        ["1,5mm", "--edges", "1"],
        ["2mm", "--edges", "0"],
        ["2mm", "--edges", "4-2"],
        ["2mm", "--edges", "x"],
        ["2mm", "--edges", ""],
        ["2mm"],
        [],
    ],
)
def test_round_argumentos_invalidos_dan_exit_2(cli, app_falsa, caja, args):
    r, sobre = cli("round", *args)
    assert r.exit_code == 2, r.output
    assert sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_round_sin_edges_pide_la_opcion(cli, caja):
    r, sobre = cli("round", "2mm")
    assert r.exit_code == 2 and "--edges" in sobre["error"]["message"]


def test_round_con_indice_fuera_de_rango_da_exit_5(cli, app_falsa, caja):
    r, sobre = cli("round", "2mm", "--edges", "1,13")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert sobre["error"]["details"] == {"fuera_de_rango": [13], "cantidad": 12}
    assert "edges list" in sobre["error"]["message"]
    assert app_falsa.escrituras == []
    assert cli("round", "2mm", "--edges", "10-14")[0].exit_code == 5


def test_round_sin_modelo_da_exit_2(cli, pieza):
    r, sobre = cli("round", "2mm", "--edges", "all")
    assert r.exit_code == 2 and "modelo" in sobre["error"]["message"]


def test_round_que_solid_edge_no_puede_hacer_se_borra_y_da_exit_4(cli, caja):
    caja.geometria_imposible = True
    r, sobre = cli("round", "500mm", "--edges", "1-4")

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
    assert "fallida" in sobre["error"]["message"] and "se borró" in sobre["error"]["message"]
    assert sobre["error"]["details"] == {
        "operacion_fallida": "Round_1",
        "borrada": True,
        "aristas": [1, 2, 3, 4],
        "estado": "failed",
    }
    assert _llamadas(caja, "Feature.Delete") == [("Feature.Delete", "Round_1")]
    modelo = caja.Models.Item(1)
    assert [f.Name for f in modelo.Features.elementos] == ["ExtrudedProtrusion_1"]
    assert modelo.Rounds.Count == 0


def test_round_fallido_que_no_se_puede_borrar_lo_dice(cli, caja):
    caja.geometria_imposible = True
    caja.operacion_no_borrable = True
    r, sobre = cli("round", "500mm", "--edges", "1")
    assert r.exit_code == 4
    assert sobre["error"]["details"]["borrada"] is False
    assert "no se pudo borrar" in sobre["error"]["message"]
    assert "Round_1" in sobre["error"]["message"]


def test_round_con_error_com_no_deja_operaciones_nuevas(cli, caja):
    caja.fallar("Rounds.Add", com_error(0x80004005, "Error no especificado", "Radio inválido"))
    r, sobre = cli("round", "2mm", "--edges", "1")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
    assert caja.Models.Item(1).Rounds.Count == 0


def test_round_readonly_y_dry_run(cli, app_falsa, caja):
    r, sobre = cli.con("--readonly", "round", "2mm", "--edges", "1")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    r, sobre = cli.con("--dry-run", "round", "2mm", "--edges", "1-3,7")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "round",
        "radio_si": 0.002,
        "aristas": [1, 2, 3, 7],
    }
    r, sobre = cli.con("--dry-run", "round", "2mm", "--edges", "all")
    assert sobre["data"]["aristas"] == "all"
    assert app_falsa.registro == []


def test_round_deja_las_alertas_apagadas_y_las_restaura(cli, app_falsa, caja):
    antes = len(app_falsa.historial_alertas)
    cli("round", "2mm", "--edges", "1")
    assert app_falsa.historial_alertas[antes:] == [False, True]


# --- chamfer --------------------------------------------------------------------------------


def test_chamfer_de_distancias_iguales(cli, caja):
    r, sobre = cli("chamfer", "1mm", "--edges", "2,4", "--units", "mm")

    assert r.exit_code == 0, r.output
    assert _llamadas(caja, "Chamfers.AddEqualSetback") == [
        ("Chamfers.AddEqualSetback", 2, (2, 4), 0.001)
    ]
    data = sobre["data"]
    assert data["operacion"] == "chaflan" and data["nombre"] == "Chamfer_1"
    assert data["indice"] == 2 and data["cantidad_aristas"] == 2 and data["aristas"] == [2, 4]
    assert data["distancia"] == pytest.approx(1.0) and data["angulo"] is None
    assert data["unidades"] == {"longitud": "mm", "angulo": "rad"}
    assert data["estado"] == "ok" and data["volumen_quitado_si"] == pytest.approx(2e-9)


def test_chamfer_con_angulo_usa_la_cara_comun(cli, caja):
    r, sobre = cli("chamfer", "2mm", "--angle", "30deg", "--edges", "1,2", "--units", "mm,deg")

    assert r.exit_code == 0, r.output
    llamada = _llamadas(caja, "Chamfers.AddSetbackAngle")
    assert llamada == [
        ("Chamfers.AddSetbackAngle", 1, 2, (1, 2), 0.002, pytest.approx(math.radians(30)))
    ]
    data = sobre["data"]
    assert data["distancia"] == pytest.approx(2.0) and data["angulo"] == pytest.approx(30.0)
    assert data["unidades"] == {"longitud": "mm", "angulo": "deg"}
    assert not _llamadas(caja, "Chamfers.AddEqualSetback")


def test_chamfer_con_angulo_sin_cara_comun_da_exit_2_sin_tocar_nada(cli, app_falsa, caja):
    r, sobre = cli("chamfer", "2mm", "--angle", "30deg", "--edges", "1,4")
    assert r.exit_code == 2 and "compartir una cara" in sobre["error"]["message"]
    assert sobre["error"]["details"] == {"aristas": [1, 4]}
    r, sobre = cli("chamfer", "2mm", "--angle", "30deg", "--edges", "all")
    assert r.exit_code == 2
    assert app_falsa.escrituras == []


def test_chamfer_all_sin_angulo(cli, caja):
    r, sobre = cli("chamfer", "1mm", "--edges", "all")
    assert r.exit_code == 0 and sobre["data"]["cantidad_aristas"] == 12


def test_chamfer_informa_el_angulo_en_radianes_por_defecto(cli, caja):
    r, sobre = cli("chamfer", "1mm", "--angle", "0.5", "--edges", "1")
    assert r.exit_code == 0 and sobre["data"]["angulo"] == pytest.approx(0.5)
    caja.sin_valores = True
    r, sobre = cli("chamfer", "1mm", "--angle", "45deg", "--edges", "1")
    assert sobre["data"]["angulo"] == pytest.approx(math.pi / 4)
    assert sobre["data"]["distancia"] == pytest.approx(0.001)


@pytest.mark.parametrize(
    "args",
    [
        ["0", "--edges", "1"],
        ["-1", "--edges", "1"],
        ["1deg", "--edges", "1"],
        ["1mm", "--edges", "1", "--angle", "0"],
        ["1mm", "--edges", "1", "--angle", "90deg"],
        ["1mm", "--edges", "1", "--angle", "120deg"],
        ["1mm", "--edges", "1", "--angle", "-5deg"],
        ["1mm", "--edges", "1", "--angle", "3mm"],
        ["1mm", "--edges", "1", "--angle", "x"],
        ["1mm", "--edges", "a"],
        ["1mm"],
    ],
)
def test_chamfer_argumentos_invalidos_dan_exit_2(cli, app_falsa, caja, args):
    r, sobre = cli("chamfer", *args)
    assert r.exit_code == 2, r.output
    assert sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_chamfer_con_indice_fuera_de_rango_da_exit_5(cli, app_falsa, caja):
    r, sobre = cli("chamfer", "1mm", "--edges", "99")
    assert r.exit_code == 5
    assert app_falsa.escrituras == []
    r, sobre = cli("chamfer", "1mm", "--angle", "30deg", "--edges", "99")
    assert r.exit_code == 5


def test_chamfer_que_solid_edge_no_puede_hacer_se_borra_y_da_exit_4(cli, caja):
    caja.geometria_imposible = True
    for args in (["50mm", "--edges", "1"], ["50mm", "--angle", "30deg", "--edges", "1,2"]):
        r, sobre = cli("chamfer", *args)
        assert r.exit_code == 4, r.output
        assert sobre["error"]["details"]["borrada"] is True
    assert caja.Models.Item(1).Chamfers.Count == 0
    assert [f.Name for f in caja.Models.Item(1).Features.elementos] == ["ExtrudedProtrusion_1"]


def test_chamfer_readonly_dry_run_y_sin_instancia(cli, app_falsa, caja):
    assert cli.con("--readonly", "chamfer", "1mm", "--edges", "1")[0].exit_code == 6
    r, sobre = cli.con("--dry-run", "chamfer", "1mm", "--angle", "45deg", "--edges", "all")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "chamfer",
        "distancia_si": 0.001,
        "angulo_si": pytest.approx(math.pi / 4),
        "aristas": "all",
    }
    assert app_falsa.registro == []


def test_comandos_de_aristas_sin_instancia_dan_exit_3(cli_sin_instancia):
    for comando in (
        ["edges", "list"],
        ["round", "1mm", "--edges", "1"],
        ["chamfer", "1mm", "--edges", "1"],
    ):
        r, sobre = cli_sin_instancia(*comando)
        assert r.exit_code == 3 and sobre["error"]["code"] == "no_conectado"
