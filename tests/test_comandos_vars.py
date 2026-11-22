"""`se vars list|get|set|add` sobre el COM falso."""

import math

import pytest
from com_falso import VariableFalsa

DIM = 1661573600


@pytest.fixture
def con_vars(app_falsa):
    doc = app_falsa.agregar_documento("Pieza.par", ruta="C:\\p\\Pieza.par", tipo=1)
    for variable in (
        VariableFalsa("Largo", 0.1, unidad=1),
        VariableFalsa("Ancho", 0.05, unidad=1),
        VariableFalsa("Doble", 0.1, unidad=1, formula="Ancho*2"),
        VariableFalsa("Giro", math.pi / 2, unidad=2),
        VariableFalsa("Cant", 4.0, unidad=58),
        VariableFalsa("Fija", 9.0, unidad=58, solo_lectura=True),
        VariableFalsa("Dimension 346", 0.02, unidad=1, tipo=DIM),
    ):
        doc.Variables.agregar(variable)
    return app_falsa


def _var(app, nombre):
    return app.ActiveDocument.Variables.Item(nombre)


def test_list_camino_feliz(cli, con_vars):
    r, sobre = cli("vars", "list")

    assert r.exit_code == 0
    assert sobre["ok"] is True and sobre["error"] is None
    data = sobre["data"]
    assert data["cantidad"] == 7
    claves = {
        "nombre",
        "valor_si",
        "valor",
        "unidad",
        "formula",
        "tipo_unidad",
        "es_cota",
        "solo_lectura",
    }
    assert all(set(v) == claves for v in data["variables"])
    por_nombre = {v["nombre"]: v for v in data["variables"]}
    assert por_nombre["Largo"] == {
        "nombre": "Largo",
        "valor_si": 0.1,
        "valor": 0.1,
        "unidad": "m",
        "formula": None,
        "tipo_unidad": "distance",
        "es_cota": False,
        "solo_lectura": False,
    }
    assert por_nombre["Doble"]["formula"] == "Ancho*2"
    assert por_nombre["Dimension 346"]["es_cota"] is True
    assert por_nombre["Fija"]["solo_lectura"] is True
    assert por_nombre["Cant"]["unidad"] is None and por_nombre["Cant"]["tipo_unidad"] == "scalar"
    assert con_vars.escrituras == []


def test_list_consulta_con_vartype_explicito_y_namedby_ambos(cli, con_vars):
    cli("vars", "list")
    consultas = [c for c in con_vars.registro if c[0] == "Variables.Query"]
    assert [c[3] for c in consultas] == [1560616706, DIM, 215773802, -170730141]
    assert {c[2] for c in consultas} == {2}


def test_list_filter(cli, con_vars):
    r, sobre = cli("vars", "list", "--filter", "*a*")

    assert r.exit_code == 0
    assert {v["nombre"] for v in sobre["data"]["variables"]} == {"Largo", "Ancho", "Cant", "Fija"}
    assert sobre["data"]["cantidad"] == 4


def test_list_units(cli, con_vars):
    r, sobre = cli("vars", "list", "--units", "mm,deg")

    assert r.exit_code == 0
    por_nombre = {v["nombre"]: v for v in sobre["data"]["variables"]}
    assert por_nombre["Largo"]["valor"] == pytest.approx(100.0)
    assert por_nombre["Largo"]["unidad"] == "mm"
    assert por_nombre["Largo"]["valor_si"] == 0.1
    assert por_nombre["Giro"]["valor"] == pytest.approx(90.0)
    assert por_nombre["Giro"]["unidad"] == "deg"
    assert por_nombre["Cant"]["valor"] == 4.0


def test_list_units_invalida_da_exit_2(cli, con_vars):
    r, sobre = cli("vars", "list", "--units", "furlong")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_list_modo_humano(cli, con_vars):
    r, _ = cli("vars", "list", como_json=False)
    assert r.exit_code == 0
    assert "Largo" in r.stdout


def test_get_camino_feliz(cli, con_vars):
    r, sobre = cli("vars", "get", "Largo", "--units", "mm")

    assert r.exit_code == 0
    assert sobre["data"]["nombre"] == "Largo"
    assert sobre["data"]["valor"] == pytest.approx(100.0)
    assert sobre["data"]["unidad"] == "mm"


def test_get_encuentra_una_cota_y_sin_distinguir_mayusculas(cli, con_vars):
    r, sobre = cli("vars", "get", "dimension 346")
    assert r.exit_code == 0 and sobre["data"]["es_cota"] is True


def test_get_inexistente_da_exit_5(cli, con_vars):
    r, sobre = cli("vars", "get", "Nada")
    assert r.exit_code == 5
    assert sobre["error"]["code"] == "doc_no_encontrado"


def test_get_modo_humano(cli, con_vars):
    r, _ = cli("vars", "get", "Largo", como_json=False)
    assert r.exit_code == 0 and "Largo" in r.stdout


def test_set_con_unidad_convierte_a_si_antes_de_escribir(cli, con_vars):
    r, sobre = cli("vars", "set", "Largo", "120mm")

    assert r.exit_code == 0
    assert con_vars.escrituras == [("Variable.Value=", "Largo", pytest.approx(0.12))]
    data = sobre["data"]
    assert set(data) == {"nombre", "antes", "despues"}
    assert data["antes"]["valor_si"] == 0.1
    assert data["despues"]["valor_si"] == pytest.approx(0.12)
    assert _var(con_vars, "Largo").Value == pytest.approx(0.12)


def test_set_pulgadas_y_grados(cli, con_vars):
    cli("vars", "set", "Largo", "2.5 in")
    cli("vars", "set", "Giro", "45deg")
    assert _var(con_vars, "Largo").Value == pytest.approx(0.0635)
    assert _var(con_vars, "Giro").Value == pytest.approx(math.radians(45))


def test_set_sin_unidad_es_si(cli, con_vars):
    cli("vars", "set", "Largo", "0.2")
    assert _var(con_vars, "Largo").Value == 0.2


def test_set_con_units_muestra_el_resultado_convertido(cli, con_vars):
    _, sobre = cli("vars", "set", "Largo", "120mm", "--units", "mm")
    assert sobre["data"]["despues"]["valor"] == pytest.approx(120.0)
    assert sobre["data"]["despues"]["unidad"] == "mm"


def test_set_formula(cli, con_vars):
    r, sobre = cli("vars", "set", "Largo", "--formula", "Ancho*3")

    assert r.exit_code == 0
    assert con_vars.escrituras == [("Variable.Formula=", "Largo", "Ancho*3")]
    assert sobre["data"]["despues"]["formula"] == "Ancho*3"
    assert sobre["data"]["antes"]["formula"] is None


def test_set_unidad_de_otra_dimension_da_exit_2(cli, con_vars):
    r, sobre = cli("vars", "set", "Largo", "45deg")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert con_vars.escrituras == []


def test_set_coma_decimal_da_exit_2_sin_conectar(cli_sin_instancia):
    r, sobre = cli_sin_instancia("vars", "set", "Largo", "1,5mm")
    assert r.exit_code == 2
    assert cli_sin_instancia.proveedor.llamadas == 0


def test_set_valor_y_formula_a_la_vez_o_ninguno_da_exit_2(cli, con_vars):
    r, _ = cli("vars", "set", "Largo", "1mm", "--formula", "Ancho")
    assert r.exit_code == 2
    r, _ = cli("vars", "set", "Largo")
    assert r.exit_code == 2
    assert con_vars.escrituras == []


def test_set_solo_lectura_da_exit_6_salvo_force(cli, con_vars):
    r, sobre = cli("vars", "set", "Fija", "1")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert con_vars.escrituras == []

    r, _ = cli("vars", "set", "Fija", "1", "--force")
    assert r.exit_code == 0
    assert con_vars.escrituras == [("Variable.Value=", "Fija", 1.0)]


def test_set_valor_en_variable_con_formula_da_exit_6_salvo_force(cli, con_vars):
    r, sobre = cli("vars", "set", "Doble", "5mm")
    assert r.exit_code == 6
    assert "Ancho*2" in sobre["error"]["message"]
    assert con_vars.escrituras == []

    r, _ = cli("vars", "set", "Doble", "5mm", "--force")
    assert r.exit_code == 0
    assert con_vars.escrituras == [("Variable.Value=", "Doble", pytest.approx(0.005))]


def test_set_formula_en_variable_con_formula_se_permite(cli, con_vars):
    r, _ = cli("vars", "set", "Doble", "--formula", "Ancho*4")
    assert r.exit_code == 0
    assert con_vars.escrituras == [("Variable.Formula=", "Doble", "Ancho*4")]


def test_set_inexistente_da_exit_5(cli, con_vars):
    r, _ = cli("vars", "set", "Nada", "1")
    assert r.exit_code == 5


def test_add_camino_feliz_deduce_el_tipo_de_la_unidad(cli, con_vars):
    r, sobre = cli("vars", "add", "Alto", "80mm")

    assert r.exit_code == 0
    assert con_vars.escrituras == [
        ("Variables.Add", "Alto", "0", 1),
        ("Variable.Value=", "Alto", pytest.approx(0.08)),
    ]
    data = sobre["data"]
    assert data["nombre"] == "Alto"
    assert data["valor_si"] == pytest.approx(0.08)
    assert data["tipo_unidad"] == "distance"
    assert data["es_cota"] is False


def test_add_con_unit_type_explicito(cli, con_vars):
    r, sobre = cli("vars", "add", "Vueltas", "3", "--unit-type", "scalar")
    assert r.exit_code == 0
    assert con_vars.escrituras[0] == ("Variables.Add", "Vueltas", "0", 58)
    assert sobre["data"]["valor_si"] == 3.0


def test_add_sin_unidad_ni_tipo_no_pasa_unitstype(cli, con_vars):
    cli("vars", "add", "X", "3")
    assert con_vars.escrituras[0] == ("Variables.Add", "X", "0", None)


def test_add_unit_type_incoherente_o_invalido_da_exit_2(cli, con_vars):
    r, _ = cli("vars", "add", "X", "3mm", "--unit-type", "angle")
    assert r.exit_code == 2
    r, sobre = cli("vars", "add", "X", "3", "--unit-type", "inventado")
    assert r.exit_code == 2 and "validos" in sobre["error"]["details"]
    assert con_vars.escrituras == []


def test_add_duplicada_da_exit_6(cli, con_vars):
    r, sobre = cli("vars", "add", "Largo", "1mm")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert con_vars.escrituras == []


def test_doc_con_selector_inexistente_da_exit_5(cli, con_vars):
    for comando in (["list"], ["get", "Largo"], ["set", "Largo", "1"], ["add", "Z", "1"]):
        r, sobre = cli("vars", *comando, "--doc", "NoExiste.par")
        assert r.exit_code == 5, comando
        assert sobre["error"]["code"] == "doc_no_encontrado"
    assert con_vars.escrituras == []


def test_doc_selecciona_otro_documento(cli, con_vars):
    otro = con_vars.agregar_documento("Otra.par", ruta="C:\\p\\Otra.par")
    otro.Variables.agregar(VariableFalsa("Solo", 1.0))
    r, sobre = cli("vars", "get", "Solo", "--doc", "1")  # el 1 es Pieza.par
    assert r.exit_code == 5
    r, sobre = cli("vars", "get", "Solo", "--doc", "Otra.par")
    assert r.exit_code == 0 and sobre["data"]["nombre"] == "Solo"


@pytest.mark.parametrize(
    "comando", [["set", "Largo", "1mm"], ["set", "Largo", "--formula", "Ancho"], ["add", "Z", "1"]]
)
def test_readonly_bloquea_con_exit_6_sin_escrituras(cli, con_vars, comando):
    r, sobre = cli("--readonly", "vars", *comando)
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert con_vars.escrituras == []


@pytest.mark.parametrize(
    ("comando", "accion"),
    [
        (["set", "Largo", "1mm"], "vars.set"),
        (["add", "Z", "1mm"], "vars.add"),
    ],
)
def test_dry_run_informa_el_plan_sin_escribir(cli, con_vars, comando, accion):
    r, sobre = cli("--dry-run", "vars", *comando)
    assert r.exit_code == 0
    assert sobre["data"]["dry_run"] is True and sobre["data"]["accion"] == accion
    assert con_vars.escrituras == []
    assert con_vars.registro == []


def test_dry_run_set_muestra_el_valor_en_si(cli, con_vars):
    _, sobre = cli("--dry-run", "vars", "set", "Largo", "120mm")
    assert sobre["data"]["valor_si"] == pytest.approx(0.12)


def test_dry_run_valida_los_argumentos(cli, con_vars):
    r, _ = cli("--dry-run", "vars", "set", "Largo", "1,5mm")
    assert r.exit_code == 2


def test_lecturas_funcionan_con_readonly(cli, con_vars):
    assert cli("--readonly", "vars", "list")[0].exit_code == 0
    assert cli("--readonly", "vars", "get", "Largo")[0].exit_code == 0


@pytest.mark.parametrize(
    "comando", [["list"], ["get", "Largo"], ["set", "Largo", "1"], ["add", "Z", "1"]]
)
def test_sin_instancia_da_exit_3_con_sobre_valido(cli_sin_instancia, comando):
    r, sobre = cli_sin_instancia("vars", *comando)
    assert r.exit_code == 3
    assert sobre["ok"] is False and sobre["error"]["code"] == "no_conectado"


def test_query_que_falla_en_todos_los_tipos_da_error_com(cli, con_vars, monkeypatch):
    from com_falso import com_error

    def falla(*args):
        raise com_error(0x80004005, "Error", "Query rota")

    monkeypatch.setattr(con_vars.ActiveDocument.Variables, "Query", falla)
    r, sobre = cli("vars", "list")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_alertas_se_restauran_tras_escribir(cli, con_vars):
    cli("vars", "set", "Largo", "1mm")
    assert con_vars.historial_alertas == [False, True]
