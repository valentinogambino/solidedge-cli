"""`se draft parts-list` y `se draft dim` sobre el COM falso."""

import pytest
from com_falso import com_error, con_anotaciones


@pytest.fixture
def conjunto(app_falsa):
    """Draft con dos vistas de un ensamble; la lista tiene 2 filas."""
    doc = app_falsa.agregar_documento("Conj.dft", ruta="C:/p/Conj.dft", tipo=2)
    return con_anotaciones(doc, ["C:/p/Conj.asm", "C:/p/Conj.asm"], filas=2)


@pytest.fixture
def pieza(app_falsa):
    doc = app_falsa.agregar_documento("Caja.dft", ruta="C:/p/Caja.dft", tipo=2)
    return con_anotaciones(doc, ["C:/p/Caja.par", "C:/p/Caja.par"], cotas=3)


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


# --- parts-list -------------------------------------------------------------------------------


def test_parts_list_por_defecto_vista_1_sin_globos(cli, app_falsa, conjunto):
    r, sobre = cli("draft", "parts-list")

    assert r.exit_code == 0, sobre
    assert sobre["data"] == {
        "vista": 1,
        "modelo": "C:/p/Conj.asm",
        "filas": 2,
        "globos": False,
        "globos_agregados": 0,
    }
    assert _llamadas(app_falsa, "PartsLists.Add") == [("PartsLists.Add", 1, "", 0, 1)]


def test_parts_list_con_globos_y_vista(cli, app_falsa, conjunto):
    r, sobre = cli("draft", "parts-list", "--view", "2", "--balloons")

    assert r.exit_code == 0, sobre
    assert sobre["data"]["vista"] == 2 and sobre["data"]["globos"] is True
    assert sobre["data"]["globos_agregados"] == 2 and sobre["data"]["filas"] == 2
    assert _llamadas(app_falsa, "PartsLists.Add") == [("PartsLists.Add", 2, "", 1, 1)]


def test_parts_list_con_doc_explicito(cli, app_falsa, conjunto):
    app_falsa.agregar_documento("Otro.par", tipo=1)
    r, sobre = cli("draft", "parts-list", "--doc", "Conj.dft")
    assert r.exit_code == 0, sobre


def test_parts_list_vista_inexistente_da_exit_5(cli, app_falsa, conjunto):
    r, sobre = cli("draft", "parts-list", "--view", "3")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert sobre["error"]["details"] == {"vista": 3, "vistas": 2}
    assert _llamadas(app_falsa, "PartsLists.Add") == []


@pytest.mark.parametrize("vista", ["0", "-1"])
def test_parts_list_vista_menor_que_1_da_exit_2_sin_com(cli, app_falsa, vista):
    r, sobre = cli("draft", "parts-list", "--view", vista)
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.registro == []


def test_parts_list_de_una_vista_de_pieza_da_exit_2(cli, app_falsa, pieza):
    r, sobre = cli("draft", "parts-list")
    assert r.exit_code == 2 and "no es de un ensamble" in sobre["error"]["message"]
    assert _llamadas(app_falsa, "PartsLists.Add") == []


def test_parts_list_en_un_documento_que_no_es_draft_da_exit_2(cli, app_falsa):
    app_falsa.agregar_documento("Part1.par", tipo=1)
    r, sobre = cli("draft", "parts-list")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_parts_list_si_solid_edge_rechaza_da_exit_4(cli, app_falsa, conjunto):
    conjunto.PartsLists.fallar("Add", com_error(0x80004005, "Error", "No se pudo"))
    r, sobre = cli("draft", "parts-list", "--balloons")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_parts_list_sin_conteo_de_globos_lo_deja_en_null(cli, app_falsa, conjunto):
    conjunto.ActiveSheet.Balloons = None
    r, sobre = cli("draft", "parts-list", "--balloons")
    assert r.exit_code == 0, sobre
    assert sobre["data"]["globos"] is True and sobre["data"]["globos_agregados"] is None


def test_parts_list_readonly_y_dry_run(cli, app_falsa, conjunto):
    r, sobre = cli.con("--readonly", "draft", "parts-list")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    r, sobre = cli.con("--dry-run", "draft", "parts-list", "--view", "2", "--balloons")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "draft.parts-list",
        "vista": 2,
        "globos": True,
    }
    assert app_falsa.escrituras == []


# --- dim --------------------------------------------------------------------------------------


def test_dim_auto_cuenta_antes_y_despues(cli, app_falsa, pieza):
    r, sobre = cli("draft", "dim", "--view", "1", "--auto")

    assert r.exit_code == 0, sobre
    assert sobre["data"] == {
        "vista": 1,
        "cotas_antes": 0,
        "cotas_despues": 3,
        "cotas_agregadas": 3,
    }
    assert _llamadas(app_falsa, "DrawingView.RetrieveDimensions") == [
        ("DrawingView.RetrieveDimensions", 1)
    ]


def test_dim_auto_repetido_agrega_cero(cli, app_falsa, pieza):
    cli("draft", "dim", "--auto")
    r, sobre = cli("draft", "dim", "--auto")
    assert r.exit_code == 0 and sobre["data"]["cotas_agregadas"] == 0
    assert sobre["data"]["cotas_antes"] == 3


def test_dim_sin_auto_da_exit_2_sin_com(cli, app_falsa, pieza):
    r, sobre = cli("draft", "dim", "--view", "1")
    assert r.exit_code == 2 and "--auto" in sobre["error"]["message"]
    assert app_falsa.registro == []


def test_dim_vista_inexistente_da_exit_5(cli, app_falsa, pieza):
    r, sobre = cli("draft", "dim", "--view", "9", "--auto")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert _llamadas(app_falsa, "DrawingView.RetrieveDimensions") == []


def test_dim_en_un_documento_que_no_es_draft_da_exit_2(cli, app_falsa):
    app_falsa.agregar_documento("Conj.asm", tipo=3)
    r, sobre = cli("draft", "dim", "--auto")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_dim_si_solid_edge_falla_da_exit_4(cli, app_falsa, pieza):
    pieza.ActiveSheet.DrawingViews.Item(1).fallar("RetrieveDimensions", com_error(0x80004005))
    r, sobre = cli("draft", "dim", "--auto")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_dim_readonly_y_dry_run(cli, app_falsa, pieza):
    r, _ = cli.con("--readonly", "draft", "dim", "--auto")
    assert r.exit_code == 6
    r, sobre = cli.con("--dry-run", "draft", "dim", "--view", "2", "--auto")
    assert sobre["data"] == {"dry_run": True, "accion": "draft.dim", "vista": 2, "auto": True}
    assert app_falsa.escrituras == []
