"""`se docs list|active|open|new` y el selector de documentos, sobre el COM falso."""

import pytest

from se_cli.core import documentos
from se_cli.core.errors import DocNoEncontrado

CLAVES = {"indice", "nombre", "ruta", "tipo", "modificado", "activo", "solo_lectura"}


@pytest.fixture
def con_documentos(app_falsa):
    app_falsa.agregar_documento("Base.par", ruta="C:\\p\\Base.par", tipo=1)
    app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3, sucio=True)
    app_falsa.agregar_documento("Plano.dft", ruta="C:\\q\\Plano.dft", tipo=2, solo_lectura=True)
    app_falsa.agregar_documento("Part1.par")  # nunca guardado
    return app_falsa


def test_list_camino_feliz(cli, con_documentos):
    r, sobre = cli("docs", "list")

    assert r.exit_code == 0
    assert set(sobre) == {"ok", "data", "error"} and sobre["ok"] is True
    data = sobre["data"]
    assert data["cantidad"] == 4
    assert all(set(d) == CLAVES for d in data["documentos"])
    assert [d["indice"] for d in data["documentos"]] == [1, 2, 3, 4]
    assert [d["tipo"] for d in data["documentos"]] == ["part", "assembly", "draft", "part"]
    assert [d["modificado"] for d in data["documentos"]] == [False, True, False, False]
    assert [d["activo"] for d in data["documentos"]] == [False, False, False, True]
    assert [d["solo_lectura"] for d in data["documentos"]] == [False, False, True, False]
    assert data["documentos"][0]["ruta"] == "C:\\p\\Base.par"
    assert data["documentos"][3]["ruta"] is None
    assert con_documentos.escrituras == []


def test_list_vacio(cli):
    r, sobre = cli("docs", "list")
    assert r.exit_code == 0
    assert sobre["data"] == {"cantidad": 0, "documentos": []}


def test_list_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("docs", "list")
    assert r.exit_code == 3
    assert sobre["ok"] is False and sobre["error"]["code"] == "no_conectado"


def test_list_funciona_con_readonly(cli, con_documentos):
    r, _ = cli("--readonly", "docs", "list")
    assert r.exit_code == 0


def test_list_modo_humano(cli, con_documentos):
    r, _ = cli("docs", "list", como_json=False)
    assert r.exit_code == 0
    assert "Base.par" in r.stdout


@pytest.mark.parametrize(
    ("nombre_tipo", "valor"),
    [
        ("part", 1),
        ("draft", 2),
        ("assembly", 3),
        ("sheetmetal", 4),
        ("desconocido", 5),
        ("weldment", 6),
        ("desconocido", 999),
        ("desconocido", None),
    ],
)
def test_nombres_de_tipo(nombre_tipo, valor):
    assert documentos.nombre_de_tipo(valor) == nombre_tipo


def test_active_camino_feliz(cli, con_documentos):
    r, sobre = cli("docs", "active")

    assert r.exit_code == 0
    assert set(sobre["data"]) == CLAVES
    assert sobre["data"]["nombre"] == "Part1.par" and sobre["data"]["activo"] is True
    assert sobre["data"]["indice"] == 4


def test_active_sin_documentos_da_exit_5(cli):
    r, sobre = cli("docs", "active")
    assert r.exit_code == 5
    assert sobre["error"]["code"] == "doc_no_encontrado"


def test_active_sin_instancia(cli_sin_instancia):
    r, _ = cli_sin_instancia("docs", "active")
    assert r.exit_code == 3


# --- open ---------------------------------------------------------------------------------


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "Pieza.par"
    ruta.write_bytes(b"x")
    return ruta


def test_open_camino_feliz(cli, app_falsa, archivo):
    r, sobre = cli("docs", "open", str(archivo))

    assert r.exit_code == 0
    assert sobre["data"]["nombre"] == "Pieza.par"
    assert sobre["data"]["ya_abierto"] is False
    assert sobre["data"]["activo"] is True
    assert ("Documents.Open", str(archivo), None) in app_falsa.registro
    assert app_falsa._alertas is True


def test_open_pasa_ruta_absoluta(cli, app_falsa, archivo, monkeypatch):
    monkeypatch.chdir(archivo.parent)
    cli("docs", "open", "Pieza.par")
    assert app_falsa.registro[-1][1] == str(archivo)


def test_open_solo_lectura(cli, app_falsa, archivo):
    r, sobre = cli("docs", "open", str(archivo), "--read-only-doc")

    assert r.exit_code == 0
    assert sobre["data"]["solo_lectura"] is True


def test_open_ruta_inexistente_da_exit_5(cli, app_falsa, tmp_path):
    r, sobre = cli("docs", "open", str(tmp_path / "no.par"))

    assert r.exit_code == 5
    assert sobre["error"]["code"] == "doc_no_encontrado"
    assert app_falsa.registro == []


def test_open_ya_abierto_lo_activa_sin_abrir_dos_veces(cli, app_falsa, archivo):
    app_falsa.agregar_documento("Pieza.par", ruta=str(archivo))
    app_falsa.agregar_documento("Otra.par", ruta="C:\\p\\Otra.par")

    r, sobre = cli("docs", "open", str(archivo))

    assert r.exit_code == 0
    assert sobre["data"]["ya_abierto"] is True
    assert sobre["data"]["activo"] is True and sobre["data"]["indice"] == 1
    assert [c[0] for c in app_falsa.escrituras] == ["Activate"]
    assert app_falsa._documentos.Count == 2


def test_open_ya_abierto_ignora_mayusculas_en_la_ruta(cli, app_falsa, archivo):
    app_falsa.agregar_documento("Pieza.par", ruta=str(archivo).upper())
    r, sobre = cli("docs", "open", str(archivo))
    assert sobre["data"]["ya_abierto"] is True


# --- new ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tipo", "progid"),
    [
        ("part", "SolidEdge.PartDocument"),
        ("assembly", "SolidEdge.AssemblyDocument"),
        ("draft", "SolidEdge.DraftDocument"),
        ("sheetmetal", "SolidEdge.SheetMetalDocument"),
    ],
)
def test_new_usa_el_progid_del_tipo(cli, app_falsa, tipo, progid):
    r, sobre = cli("docs", "new", tipo)

    assert r.exit_code == 0
    assert set(sobre["data"]) == CLAVES
    assert sobre["data"]["activo"] is True
    assert ("Documents.Add", progid) in app_falsa.registro


def test_new_con_plantilla(cli, app_falsa, tmp_path):
    plantilla = tmp_path / "base.psm"
    plantilla.write_bytes(b"x")

    r, _ = cli("docs", "new", "sheetmetal", "--template", str(plantilla))

    assert r.exit_code == 0
    assert ("Documents.Add", str(plantilla)) in app_falsa.registro


def test_new_plantilla_inexistente(cli, app_falsa, tmp_path):
    r, _ = cli("docs", "new", "part", "--template", str(tmp_path / "no.par"))
    assert r.exit_code == 5
    assert app_falsa.registro == []


def test_new_tipo_invalido_da_exit_2(cli, app_falsa):
    r, sobre = cli("docs", "new", "cubo")

    assert r.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert "part" in sobre["error"]["message"]
    assert app_falsa.registro == []


def test_new_weldment_exige_plantilla(cli, app_falsa):
    r, sobre = cli("docs", "new", "weldment")
    assert r.exit_code == 2
    assert "--template" in sobre["error"]["message"]
    assert app_falsa.registro == []


def test_new_weldment_con_plantilla(cli, app_falsa, tmp_path):
    plantilla = tmp_path / "w.pwd"
    plantilla.write_bytes(b"x")
    r, _ = cli("docs", "new", "weldment", "--template", str(plantilla))
    assert r.exit_code == 0


# --- readonly / dry-run -------------------------------------------------------------------


@pytest.mark.parametrize("modo", ["--readonly", "--dry-run"])
def test_open_y_new_no_escriben_con_readonly_o_dry_run(cli, app_falsa, archivo, modo):
    for comando in (["docs", "open", str(archivo)], ["docs", "new", "part"]):
        r, sobre = cli(modo, *comando)
        if modo == "--readonly":
            assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
        else:
            assert r.exit_code == 0 and sobre["data"]["dry_run"] is True
    assert app_falsa.registro == []
    assert app_falsa.historial_alertas == []


def test_dry_run_de_open_valida_la_ruta(cli, tmp_path):
    r, _ = cli("--dry-run", "docs", "open", str(tmp_path / "no.par"))
    assert r.exit_code == 5


# --- selector -----------------------------------------------------------------------------


def test_selector_por_indice_nombre_y_ruta(con_documentos):
    app = con_documentos
    assert documentos.resolver(app, "2")[1].Name == "Conj.asm"
    assert documentos.resolver(app, "conj.ASM")[1].Name == "Conj.asm"
    assert documentos.resolver(app, "C:\\q\\Plano.dft")[1].Name == "Plano.dft"
    assert documentos.resolver(app, None)[1].Name == "Part1.par"


@pytest.mark.parametrize("selector", ["0", "9", "nada.par", "C:\\p\\nada.par"])
def test_selector_inexistente_da_exit_5(con_documentos, selector):
    with pytest.raises(DocNoEncontrado) as info:
        documentos.resolver(con_documentos, selector)
    assert info.value.exit_code == 5


def test_selector_ambiguo_da_exit_5(app_falsa):
    app_falsa.agregar_documento("Igual.par", ruta="C:\\a\\Igual.par")
    app_falsa.agregar_documento("igual.PAR", ruta="C:\\b\\igual.PAR")

    with pytest.raises(DocNoEncontrado, match="ambiguo") as info:
        documentos.resolver(app_falsa, "IGUAL.par")
    assert info.value.exit_code == 5
    assert documentos.resolver(app_falsa, "C:\\b\\igual.par")[0] == 2
