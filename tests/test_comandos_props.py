"""`se props get|set` sobre el COM falso."""

import pytest
from com_falso import con_propiedades


@pytest.fixture
def con_props(app_falsa):
    doc = app_falsa.agregar_documento("Pieza.par", ruta="C:\\p\\Pieza.par", tipo=1)
    con_propiedades(
        doc,
        {
            "SummaryInformation": {"Title": "Soporte", "Author": "Ana"},
            "ProjectInformation": {"Document Number": "A-1", "Revision": "B"},
            "Custom": {"Proveedor": "ACME", "Revision": "C"},
        },
    )
    return app_falsa


def test_get_lista_todo(cli, con_props):
    r, sobre = cli("props", "get")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "cantidad": 6,
        "propiedades": [
            {"conjunto": "SummaryInformation", "nombre": "Title", "valor": "Soporte"},
            {"conjunto": "SummaryInformation", "nombre": "Author", "valor": "Ana"},
            {"conjunto": "ProjectInformation", "nombre": "Document Number", "valor": "A-1"},
            {"conjunto": "ProjectInformation", "nombre": "Revision", "valor": "B"},
            {"conjunto": "Custom", "nombre": "Proveedor", "valor": "ACME"},
            {"conjunto": "Custom", "nombre": "Revision", "valor": "C"},
        ],
    }
    assert con_props.escrituras == []


def test_get_de_un_conjunto(cli, con_props):
    r, sobre = cli("props", "get", "--set", "custom")
    assert r.exit_code == 0
    assert [p["nombre"] for p in sobre["data"]["propiedades"]] == ["Proveedor", "Revision"]


def test_get_una_propiedad(cli, con_props):
    r, sobre = cli("props", "get", "Title")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "conjunto": "SummaryInformation",
        "nombre": "Title",
        "valor": "Soporte",
    }


def test_get_propiedad_repetida_pide_conjunto(cli, con_props):
    r, sobre = cli("props", "get", "Revision")
    assert r.exit_code == 2 and "--set" in sobre["error"]["message"]

    r, sobre = cli("props", "get", "Revision", "--set", "Custom")
    assert r.exit_code == 0 and sobre["data"]["valor"] == "C"


def test_get_inexistente_o_conjunto_inexistente_da_exit_5(cli, con_props):
    assert cli("props", "get", "Nada")[0].exit_code == 5
    r, sobre = cli("props", "get", "--set", "Inventado")
    assert r.exit_code == 5
    assert "Custom" in sobre["error"]["details"]["conjuntos"]


def test_get_modo_humano(cli, con_props):
    r, _ = cli("props", "get", como_json=False)
    assert r.exit_code == 0 and "Soporte" in r.stdout


def test_set_crea_en_custom_y_no_guarda(cli, con_props):
    r, sobre = cli("props", "set", "Lote", "L-7")

    assert r.exit_code == 0
    assert con_props.escrituras == [("Properties.Add", "Custom", "Lote", "L-7")]
    assert sobre["data"] == {
        "conjunto": "Custom",
        "nombre": "Lote",
        "antes": None,
        "despues": "L-7",
        "creada": True,
        "guardado": False,
    }
    assert not any(e[0] in ("Save", "SaveAs") for e in con_props.registro)


def test_set_actualiza_una_existente(cli, con_props):
    r, sobre = cli("props", "set", "Proveedor", "Otro")
    assert r.exit_code == 0
    assert con_props.escrituras == [("Property.Value=", "Proveedor", "Otro")]
    assert sobre["data"]["antes"] == "ACME" and sobre["data"]["creada"] is False


def test_set_en_otro_conjunto_existente(cli, con_props):
    r, sobre = cli("props", "set", "Title", "Nuevo", "--set", "SummaryInformation")
    assert r.exit_code == 0 and sobre["data"]["conjunto"] == "SummaryInformation"
    assert con_props.escrituras == [("Property.Value=", "Title", "Nuevo")]


def test_set_inexistente_en_otro_conjunto_da_exit_5(cli, con_props):
    r, sobre = cli("props", "set", "Nueva", "x", "--set", "SummaryInformation")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert con_props.escrituras == []


def test_set_conjunto_inexistente_da_exit_5(cli, con_props):
    r, _ = cli("props", "set", "A", "b", "--set", "Inventado")
    assert r.exit_code == 5 and con_props.escrituras == []


def test_set_con_save_guarda(cli, con_props):
    r, sobre = cli("props", "set", "Lote", "L-7", "--save")

    assert r.exit_code == 0 and sobre["data"]["guardado"] is True
    assert [e[0] for e in con_props.escrituras] == ["Properties.Add", "Save"]


def test_set_save_en_doc_nunca_guardado_no_escribe_nada(cli, app_falsa):
    doc = app_falsa.agregar_documento("Part1.par")
    con_propiedades(doc, {"Custom": {}})
    r, sobre = cli("props", "set", "A", "b", "--save")
    assert r.exit_code == 2
    assert app_falsa.escrituras == []


def test_set_save_en_doc_solo_lectura_da_exit_6_sin_escribir(cli, app_falsa):
    doc = app_falsa.agregar_documento("RO.par", ruta="C:\\p\\RO.par", solo_lectura=True)
    con_propiedades(doc, {"Custom": {}})
    r, _ = cli("props", "set", "A", "b", "--save")
    assert r.exit_code == 6 and app_falsa.escrituras == []


def test_readonly_y_dry_run_no_escriben(cli, con_props):
    r, sobre = cli("--readonly", "props", "set", "Lote", "x")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli("--dry-run", "props", "set", "Lote", "x", "--save")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "props.set",
        "conjunto": "Custom",
        "nombre": "Lote",
        "valor": "x",
        "save": True,
    }
    assert con_props.registro == []


def test_get_funciona_con_readonly(cli, con_props):
    assert cli("--readonly", "props", "get")[0].exit_code == 0


def test_doc_inexistente_da_exit_5(cli, con_props):
    for comando in (["get"], ["set", "A", "b"]):
        r, sobre = cli("props", *comando, "--doc", "NoExiste.par")
        assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"


@pytest.mark.parametrize("comando", [["get"], ["set", "A", "b"]])
def test_sin_instancia_da_exit_3(cli_sin_instancia, comando):
    r, sobre = cli_sin_instancia("props", *comando)
    assert r.exit_code == 3 and sobre["ok"] is False


def test_get_omite_las_propiedades_sin_nombre(cli, app_falsa):
    doc = app_falsa.agregar_documento("Pieza.par", ruta="C:\\p\\Pieza.par", tipo=1)
    con_propiedades(doc, {"ExtendedSummaryInformation": {"Status": 0, "": "", " ": ""}})

    r, sobre = cli("props", "get")

    assert [p["nombre"] for p in sobre["data"]["propiedades"]] == ["Status"]
