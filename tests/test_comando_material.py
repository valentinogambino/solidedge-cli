"""`se material list|get|set` sobre el COM falso."""

import pytest

import se_cli.mcp_server as servidor


@pytest.fixture
def pieza(app_falsa):
    return app_falsa.agregar_documento("Pieza.par", ruta="C:\\p\\Pieza.par", tipo=1)


def test_list_agrupa_por_biblioteca(cli, app_falsa):
    r, sobre = cli("material", "list")

    assert r.exit_code == 0
    bibliotecas = sobre["data"]["bibliotecas"]
    assert [b["biblioteca"] for b in bibliotecas] == ["Materials", "Materials-DIN"]
    assert bibliotecas[0]["materiales"] == ["Steel", "Aluminum, 1060", "Stainless Steel, 304"]


def test_list_con_biblioteca_sin_distinguir_mayusculas(cli, app_falsa):
    r, sobre = cli("material", "list", "--library", "materials-din")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "bibliotecas": [{"biblioteca": "Materials-DIN", "materiales": ["S235JR"]}]
    }


def test_list_biblioteca_inexistente_exit_5(cli, app_falsa):
    r, sobre = cli("material", "list", "--library", "Nada")

    assert r.exit_code == 5
    assert sobre["error"]["details"]["bibliotecas"] == ["Materials", "Materials-DIN"]


def test_get_sin_material_da_null(cli, pieza):
    r, sobre = cli("material", "get")

    assert r.exit_code == 0
    assert sobre["data"] == {"material": None}


def test_get_en_ensamble_exit_2(cli, app_falsa):
    app_falsa.agregar_documento("Ens.asm", ruta="C:\\p\\Ens.asm", tipo=3)

    r, _ = cli("material", "get")

    assert r.exit_code == 2


def test_set_asigna_con_la_grafia_exacta(cli, app_falsa, pieza):
    r, sobre = cli("material", "set", "aluminum, 1060")

    assert r.exit_code == 0, sobre
    assert sobre["data"] == {
        "material": "Aluminum, 1060",
        "biblioteca": "Materials",
        "anterior": None,
        "guardado": False,
    }
    assert pieza.material == "Aluminum, 1060"
    assert app_falsa.tabla_de_materiales.aplicados == [("Aluminum, 1060", "Materials")]


def test_set_busca_en_la_biblioteca_indicada(cli, app_falsa, pieza):
    pieza.material = "Steel"

    r, sobre = cli("material", "set", "S235JR", "--library", "Materials-DIN")

    assert r.exit_code == 0
    assert sobre["data"]["anterior"] == "Steel"
    assert sobre["data"]["biblioteca"] == "Materials-DIN"


def test_set_inexistente_exit_5_con_parecidos_y_sin_escribir(cli, app_falsa, pieza):
    r, sobre = cli("material", "set", "steel, 9")

    assert r.exit_code == 5
    assert "se material list" in sobre["error"]["message"]
    assert not getattr(app_falsa, "tabla_de_materiales", None) or not (
        app_falsa.tabla_de_materiales.aplicados
    )
    assert getattr(pieza, "material", "") == ""

    r, sobre = cli("material", "set", "stainless")
    assert r.exit_code == 5
    assert sobre["error"]["details"]["parecidos"] == ["Stainless Steel, 304"]


def test_set_vacio_exit_2(cli, pieza):
    r, _ = cli("material", "set", "  ")

    assert r.exit_code == 2


def test_set_respeta_readonly_y_dry_run(cli, app_falsa, pieza):
    r, _ = cli("--readonly", "material", "set", "Steel")
    assert r.exit_code == 6

    r, sobre = cli("--dry-run", "material", "set", "Steel")
    assert r.exit_code == 0
    assert sobre["data"]["accion"] == "material.set"
    assert getattr(pieza, "material", "") == ""


def test_mass_sin_material_sugiere_material_set(cli, app_falsa, pieza):
    from com_falso import ColeccionFalsa, ModeloFalso

    pieza.Models = ColeccionFalsa([ModeloFalso(pieza)])

    r, sobre = cli("mass")

    assert r.exit_code == 2
    assert "se material set" in sobre["error"]["message"]


@pytest.fixture
def mcp_con_sesion(monkeypatch, sesion):
    def crear(*, plazo):
        sesion.plazo = plazo
        return sesion

    monkeypatch.setattr(servidor, "Sesion", crear)


def test_tool_mcp_material(mcp_con_sesion, app_falsa, pieza):
    sobre = servidor.material()
    assert sobre == {"ok": True, "data": {"material": None}, "error": None}

    sobre = servidor.material(name="steel")
    assert sobre["ok"] is True
    assert sobre["data"]["material"] == "Steel"

    sobre = servidor.material(name="No existe")
    assert sobre["ok"] is False
    assert sobre["error"]["code"] == "doc_no_encontrado"
