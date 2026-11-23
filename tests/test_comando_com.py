"""`se com get|set|invoke` sobre el COM falso, y el parser de rutas."""

import pytest
from com_falso import con_modelado

from se_cli.core import com
from se_cli.core.errors import ArgumentoInvalido, SoloLectura

# --- parser ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Version", "Version"),
        ("ActiveDocument.Name", "ActiveDocument.Name"),
        ("Documents.Item(1).Name", "Documents.Item(1).Name"),
        ('Documents.Item("Pieza 1").Name', 'Documents.Item("Pieza 1").Name'),
        ("Documents.Item( 2 )", "Documents.Item(2)"),
        ("A.B(1, 2.5, 'x', true, false, null, -3)", 'A.B(1, 2.5, "x", true, false, null, -3)'),
        ("A.B()", "A.B()"),
        ("A.B('con \\' comilla y . punto')", 'A.B("con \' comilla y . punto")'),
    ],
)
def test_parsear_ruta_valida(texto, esperado):
    assert com.texto_de_ruta(com.parsear_ruta(texto)) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "   ",
        ".A",
        "A.",
        "A..B",
        "A B",
        "1A",
        "_A",
        "A._oleobj_",
        "A.__class__",
        "A(",
        "A(1",
        "A(1,)",
        "A(,1)",
        "A(1 2)",
        "A(foo)",
        "A(True)",
        "A('x)",
        "A('x\\n')",
        "A(1)(2)",
        "A(1)B",
        "A-B",
        "A.B(__import__('os'))",
        "A.B(1+1)",
        "A[0]",
        "A;B",
        'A.B("x").',
    ],
)
def test_parsear_ruta_invalida_da_exit_2(texto):
    with pytest.raises(ArgumentoInvalido):
        com.parsear_ruta(texto)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("10", 10),
        ("-2", -2),
        ("0.5", 0.5),
        ("1e-3", 0.001),
        ('"hola"', "hola"),
        ("'hola'", "hola"),
        ("true", True),
        ("false", False),
        ("null", None),
    ],
)
def test_parsear_literal(texto, esperado):
    valor = com.parsear_literal(texto)
    assert valor == esperado and type(valor) is type(esperado)


@pytest.mark.parametrize("texto", ["", "abc", "1 2", "True", "[1]", "1.5mm", "'x"])
def test_parsear_literal_invalido(texto):
    with pytest.raises(ArgumentoInvalido):
        com.parsear_literal(texto)


def test_quit_esta_denegado_en_cualquier_posicion():
    for ruta in ("Quit", "Application.Quit", "quit", "Quit.Foo"):
        with pytest.raises(SoloLectura):
            com.rechazar_prohibidos(com.parsear_ruta(ruta))
    com.rechazar_prohibidos(com.parsear_ruta("Documents.Count"))


# --- get ------------------------------------------------------------------------------------


@pytest.fixture
def pieza(app_falsa):
    doc = con_modelado(app_falsa.agregar_documento("Part1.par", tipo=1))
    return doc


def test_get_valores_simples(cli, app_falsa, pieza):
    r, sobre = cli("com", "get", "Version")
    assert r.exit_code == 0 and sobre["data"] == {"ruta": "Version", "valor": "226.00.00.00"}

    r, sobre = cli("com", "get", "Documents.Count")
    assert sobre["data"] == {"ruta": "Documents.Count", "valor": 1}

    r, sobre = cli("com", "get", "ActiveDocument.Name")
    assert sobre["data"]["valor"] == "Part1.par"

    r, sobre = cli("com", "get", "Documents.Item(1).Name")
    assert sobre["data"] == {"ruta": "Documents.Item(1).Name", "valor": "Part1.par"}
    assert app_falsa.escrituras == []


def test_get_item_por_nombre_y_objeto_com(cli, app_falsa, pieza):
    pieza.Properties = pieza.Models  # cualquier colección con Item por nombre
    r, sobre = cli("com", "get", "Documents.Item(1)")
    assert r.exit_code == 0
    valor = sobre["data"]["valor"]
    assert valor["tipo"] == "objeto_com" and valor["nombre"] == "Part1.par"
    assert "DocumentoFalso" in valor["repr"]


def test_get_de_coleccion_no_enumera_salvo_list(cli, app_falsa, pieza):
    cli("sketch", "rect", "--width", "1mm", "--height", "1mm")
    cli("extrude", "1mm")

    r, sobre = cli("com", "get", "ActiveDocument.Models")
    assert sobre["data"]["valor"]["tipo"] == "objeto_com"

    r, sobre = cli("com", "get", "ActiveDocument.Models.Item(1).ExtrudedProtrusions", "--list")
    valor = sobre["data"]["valor"]
    assert valor["tipo"] == "coleccion" and valor["cantidad"] == 1 and valor["truncado"] is False
    assert valor["items"][0]["indice"] == 1
    assert valor["items"][0]["nombre"] == "ExtrudedProtrusion_1"


def test_get_list_respeta_limit(cli, app_falsa):
    for n in range(3):
        app_falsa.agregar_documento(f"D{n}.par")
    r, sobre = cli("com", "get", "Documents", "--list", "--limit", "2")
    valor = sobre["data"]["valor"]
    assert [i["nombre"] for i in valor["items"]] == ["D0.par", "D1.par"]
    assert valor["cantidad"] == 3 and valor["truncado"] is True
    r, _ = cli("com", "get", "Documents", "--list", "--limit", "0")
    assert r.exit_code == 2


def test_get_list_sobre_un_valor_da_exit_2(cli, app_falsa, pieza):
    r, sobre = cli("com", "get", "Version", "--list")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_get_no_ejecuta_metodos(cli, app_falsa, pieza):
    r, sobre = cli("com", "get", "ActiveDocument.Save")
    assert r.exit_code == 2 and "com invoke" in sobre["error"]["message"]
    r, sobre = cli("com", "get", "ActiveDocument.Save()")
    assert r.exit_code == 2 and "com invoke" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


@pytest.mark.parametrize(
    "ruta", ["Nada", "ActiveDocument.Nada", "Version.Foo", "Documents.Count.Foo"]
)
def test_get_miembro_inexistente_o_sobre_un_valor_da_exit_2(cli, pieza, ruta):
    r, sobre = cli("com", "get", ruta)
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_get_item_fuera_de_rango_es_error_com_o_interno(cli, pieza):
    r, _ = cli("com", "get", "Documents.Item(99).Name")
    assert r.exit_code != 0


@pytest.mark.parametrize("ruta", ["Application.Quit", "Quit", "ActiveDocument._x", "A..B"])
def test_get_rutas_prohibidas_o_invalidas(cli, app_falsa, ruta):
    r, sobre = cli("com", "get", ruta)
    assert r.exit_code in (2, 6)
    assert app_falsa.registro == [] and not app_falsa.salio


def test_quit_da_exit_6_en_los_tres_subcomandos(cli, app_falsa):
    for sub in (("get", "Quit"), ("set", "Quit", "1"), ("invoke", "Quit"), ("invoke", "Quit()")):
        r, sobre = cli("com", *sub)
        assert r.exit_code == 6 and "se quit" in sobre["error"]["message"], sub
    r, sobre = cli.con("--dry-run", "com", "invoke", "Quit")
    assert r.exit_code == 6
    assert app_falsa.salio is False and app_falsa.registro == []


# --- set e invoke ---------------------------------------------------------------------------


def test_set_asigna_y_devuelve_el_valor_actual(cli, app_falsa, pieza):
    r, sobre = cli("com", "set", "ActiveDocument.Name", '"Otra.par"')
    assert r.exit_code == 0, r.output
    assert sobre["data"] == {
        "ruta": "ActiveDocument.Name",
        "valor": "Otra.par",
        "valor_actual": "Otra.par",
    }
    assert pieza.Name == "Otra.par"
    assert app_falsa.historial_alertas == [False, True]


def test_set_de_display_alerts_no_se_deshace(cli, app_falsa):
    r, sobre = cli("com", "set", "DisplayAlerts", "false")
    assert r.exit_code == 0 and sobre["data"]["valor_actual"] is False
    assert app_falsa._alertas is False


@pytest.mark.parametrize(
    ("args", "codigo"),
    [
        (("ActiveDocument.Name", "sin comillas"), 2),
        (("ActiveDocument.Name()", "1"), 2),
        (("Version.Foo", "1"), 2),
        (("_x", "1"), 2),
    ],
)
def test_set_invalido(cli, pieza, args, codigo):
    r, _ = cli("com", "set", *args)
    assert r.exit_code == codigo
    assert pieza.Name == "Part1.par"


def test_invoke_con_argumentos_sueltos_y_resultado_objeto(cli, app_falsa, pieza):
    r, sobre = cli("com", "invoke", "Documents.Item", "1")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["ruta"] == "Documents.Item" and sobre["data"]["argumentos"] == [1]
    assert sobre["data"]["resultado"]["tipo"] == "objeto_com"
    assert sobre["data"]["resultado"]["nombre"] == "Part1.par"


def test_invoke_sin_resultado_y_con_escritura(cli, app_falsa, pieza):
    r, sobre = cli("com", "invoke", "ActiveDocument.Activate")
    assert r.exit_code == 0
    assert sobre["data"]["resultado"] is None and sobre["data"]["argumentos"] == []
    assert app_falsa.escrituras == [("Activate", "Part1.par")]


def test_invoke_con_parentesis_en_la_ruta(cli, app_falsa, pieza):
    r, sobre = cli("com", "invoke", "Documents.Item(1).Name")
    assert r.exit_code == 2  # Name no es un método
    r, sobre = cli("com", "invoke", "Documents.Item(1)")
    assert r.exit_code == 0 and sobre["data"]["argumentos"] == [1]
    assert sobre["data"]["ruta"] == "Documents.Item"
    r, sobre = cli("com", "invoke", "Documents.Item(1).Activate()")
    assert r.exit_code == 0
    r, sobre = cli("com", "invoke", "Documents.Item(1)", "1")
    assert r.exit_code == 2


def test_invoke_argumentos_invalidos_o_metodo_inexistente(cli, pieza):
    r, _ = cli("com", "invoke", "Documents.Item", "abc")
    assert r.exit_code == 2
    r, _ = cli("com", "invoke", "Documents.Nada", "1")
    assert r.exit_code == 2
    r, _ = cli("com", "invoke", "Documents.Count")
    assert r.exit_code == 2


def test_readonly_y_dry_run_de_set_e_invoke(cli, app_falsa, pieza):
    for comando in (
        ["set", "ActiveDocument.Name", '"X"'],
        ["invoke", "ActiveDocument.Activate"],
    ):
        r, sobre = cli.con("--readonly", "com", *comando)
        assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
        r, sobre = cli.con("--dry-run", "com", *comando)
        assert r.exit_code == 0 and sobre["data"]["dry_run"] is True
    r, sobre = cli.con("--dry-run", "com", "invoke", "Documents.Item", "1", "'a'")
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "com.invoke",
        "ruta": "Documents.Item",
        "segmentos": ["Documents", "Item"],
        "argumentos": [1, "a"],
    }
    assert app_falsa.registro == [] and pieza.Name == "Part1.par"


def test_get_funciona_con_readonly(cli, pieza):
    r, sobre = cli.con("--readonly", "com", "get", "Documents.Count")
    assert r.exit_code == 0 and sobre["data"]["valor"] == 1


def test_sin_instancia_da_exit_3(cli_sin_instancia):
    for comando in (
        ("get", "Version"),
        ("set", "DisplayAlerts", "true"),
        ("invoke", "Documents.Item", "1"),
    ):
        r, sobre = cli_sin_instancia("com", *comando)
        assert r.exit_code == 3 and sobre["error"]["code"] == "no_conectado"
