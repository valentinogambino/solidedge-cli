"""`se features list` sobre el COM falso."""

import pytest
from com_falso import ColeccionFalsa, FeatureFalsa, ModeloFalso, PlanoRefFalso

EXTRUSION = 462094706
CORTE = 462094714
SUPRIMIDA = 1216476313


def _pieza(app, features, tipo=1, nombre="Pieza.par"):
    doc = app.agregar_documento(nombre, ruta=f"C:\\p\\{nombre}", tipo=tipo)
    doc.Models = ColeccionFalsa([ModeloFalso(doc, features)])
    return doc


@pytest.fixture
def con_features(app_falsa):
    _pieza(
        app_falsa,
        [
            FeatureFalsa("ExtrudedProtrusion_1", EXTRUSION),
            FeatureFalsa("ExtrudedCutout_1", CORTE, suprimida=True, estado=SUPRIMIDA),
            FeatureFalsa("Hole_9", 123456789, estado=1216476311),
        ],
    )
    return app_falsa


def test_list_con_suprimidas(cli, con_features):
    r, sobre = cli("features", "list")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "cantidad": 3,
        "operaciones": [
            {
                "indice": 1,
                "nombre": "ExtrudedProtrusion_1",
                "tipo": "ExtrudedProtrusion",
                "suprimida": False,
                "estado": "ok",
            },
            {
                "indice": 2,
                "nombre": "ExtrudedCutout_1",
                "tipo": "ExtrudedCutout",
                "suprimida": True,
                "estado": "suppressed",
            },
            {
                "indice": 3,
                "nombre": "Hole_9",
                "tipo": 123456789,  # sin enum: el entero
                "suprimida": False,
                "estado": "failed",
            },
        ],
    }
    assert con_features.escrituras == []


def test_chapa_es_soportada(cli, app_falsa):
    _pieza(app_falsa, [FeatureFalsa("Tab_1", EXTRUSION)], tipo=4, nombre="Chapa.psm")
    r, sobre = cli("features", "list")
    assert r.exit_code == 0 and sobre["data"]["cantidad"] == 1


def test_sin_features_lista_vacia(cli, app_falsa):
    _pieza(app_falsa, [])
    r, sobre = cli("features", "list")
    assert r.exit_code == 0 and sobre["data"] == {"cantidad": 0, "operaciones": []}


def test_modo_sincronico_cae_al_pathfinder_sin_planos(cli, app_falsa):
    doc = app_falsa.agregar_documento("Sync.par", ruta="C:\\p\\Sync.par", tipo=1)
    doc.Models = ColeccionFalsa([ModeloFalso(doc, [])])  # Features vacío
    doc.DesignEdgebarFeatures = ColeccionFalsa(
        [
            PlanoRefFalso("Top"),
            PlanoRefFalso("Front"),
            FeatureFalsa("ExtrudedProtrusion_1", EXTRUSION),
        ]
    )
    r, sobre = cli("features", "list")
    assert r.exit_code == 0
    assert [o["nombre"] for o in sobre["data"]["operaciones"]] == ["ExtrudedProtrusion_1"]
    assert sobre["data"]["operaciones"][0]["indice"] == 1


@pytest.mark.parametrize("tipo", [2, 3, 6])
def test_tipo_no_soportado_da_exit_2(cli, app_falsa, tipo):
    app_falsa.agregar_documento("Otro", ruta="C:\\p\\Otro", tipo=tipo)
    r, sobre = cli("features", "list")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_modo_humano(cli, con_features):
    r, _ = cli("features", "list", como_json=False)
    assert r.exit_code == 0 and "ExtrudedCutout_1" in r.stdout


def test_funciona_con_readonly_y_dry_run(cli, con_features):
    assert cli("--readonly", "features", "list")[0].exit_code == 0
    assert cli("--dry-run", "features", "list")[0].exit_code == 0


def test_doc_inexistente_da_exit_5(cli, con_features):
    r, _ = cli("features", "list", "--doc", "NoExiste.par")
    assert r.exit_code == 5


def test_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("features", "list")
    assert r.exit_code == 3 and sobre["ok"] is False


# --- suppress / unsuppress ---------------------------------------------------------------------


def test_suppress_por_indice(cli, con_features):
    r, sobre = cli("features", "suppress", "1")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "indice": 1,
        "nombre": "ExtrudedProtrusion_1",
        "tipo": "ExtrudedProtrusion",
        "suprimida": True,
        "estado": "suppressed",
        "changed": True,
    }
    assert con_features.escrituras == [("Feature.Suppress=", "ExtrudedProtrusion_1", True)]


def test_unsuppress_por_nombre_sin_distinguir_mayusculas(cli, con_features):
    r, sobre = cli("features", "unsuppress", "extrudedcutout_1")

    assert r.exit_code == 0
    assert sobre["data"]["suprimida"] is False and sobre["data"]["changed"] is True
    assert sobre["data"]["estado"] == "ok" and sobre["data"]["indice"] == 2
    assert con_features.escrituras == [("Feature.Suppress=", "ExtrudedCutout_1", False)]


def test_suppress_ya_suprimida_es_idempotente(cli, con_features):
    r, sobre = cli("features", "suppress", "ExtrudedCutout_1")

    assert r.exit_code == 0
    assert sobre["data"]["suprimida"] is True and sobre["data"]["changed"] is False
    assert con_features.escrituras == []


def test_unsuppress_ya_activa_es_idempotente(cli, con_features):
    r, sobre = cli("features", "unsuppress", "1")
    assert r.exit_code == 0 and sobre["data"]["changed"] is False
    assert con_features.escrituras == []


def test_suppress_y_list_coinciden(cli, con_features):
    cli("features", "suppress", "3")
    _, sobre = cli("features", "list")
    assert [o["suprimida"] for o in sobre["data"]["operaciones"]] == [False, True, True]


@pytest.mark.parametrize("selector", ["0", "4", "99", "NoExiste"])
@pytest.mark.parametrize("accion", ["suppress", "unsuppress"])
def test_operacion_inexistente_da_exit_5(cli, con_features, accion, selector):
    r, sobre = cli("features", accion, selector)
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert con_features.escrituras == []


@pytest.mark.parametrize("accion", ["suppress", "unsuppress"])
@pytest.mark.parametrize("tipo", [2, 3, 6])
def test_suppress_tipo_no_soportado_da_exit_2(cli, app_falsa, accion, tipo):
    app_falsa.agregar_documento("Otro", ruta="C:\\p\\Otro", tipo=tipo)
    r, sobre = cli("features", accion, "1")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_suppress_chapa_es_soportado(cli, app_falsa):
    _pieza(app_falsa, [FeatureFalsa("Tab_1", EXTRUSION)], tipo=4, nombre="Chapa.psm")
    r, sobre = cli("features", "suppress", "Tab_1")
    assert r.exit_code == 0 and sobre["data"]["suprimida"] is True


def test_suppress_en_modo_sincronico_usa_el_pathfinder(cli, app_falsa):
    doc = app_falsa.agregar_documento("Sync.par", ruta="C:\\p\\Sync.par", tipo=1)
    doc.Models = ColeccionFalsa([ModeloFalso(doc, [])])
    feature = FeatureFalsa("ExtrudedProtrusion_1", EXTRUSION)
    doc.DesignEdgebarFeatures = ColeccionFalsa([PlanoRefFalso("Top"), feature])
    r, sobre = cli("features", "suppress", "1")
    assert r.exit_code == 0 and sobre["data"]["nombre"] == "ExtrudedProtrusion_1"
    assert feature.Suppress is True


def test_si_solid_edge_no_aplica_la_escritura_da_exit_4(cli, app_falsa):
    feature = FeatureFalsa("ExtrudedProtrusion_1", EXTRUSION)
    feature.ignora_escritura = True
    _pieza(app_falsa, [feature])
    r, sobre = cli("features", "suppress", "1")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_suppress_error_com_da_exit_4(cli, app_falsa):
    from com_falso import com_error

    class Rota(FeatureFalsa):
        @property
        def Suppress(self):
            return False

        @Suppress.setter
        def Suppress(self, valor):
            raise com_error(0x80004005, "Error no especificado")

    _pieza(app_falsa, [Rota("ExtrudedProtrusion_1", EXTRUSION)])
    r, sobre = cli("features", "suppress", "1")
    assert r.exit_code == 4 and sobre["ok"] is False


@pytest.mark.parametrize("accion", ["suppress", "unsuppress"])
def test_readonly_bloquea_y_dry_run_no_escribe(cli, con_features, accion):
    r, sobre = cli("--readonly", "features", accion, "1")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    r, sobre = cli("--dry-run", "features", accion, "1")
    assert r.exit_code == 0
    assert sobre["data"] == {"dry_run": True, "accion": f"features.{accion}", "operacion": "1"}
    assert con_features.escrituras == []


def test_suppress_modo_humano(cli, con_features):
    r, _ = cli("features", "suppress", "ExtrudedProtrusion_1", como_json=False)
    assert r.exit_code == 0 and "ExtrudedProtrusion_1" in r.stdout


def test_suppress_doc_inexistente_da_exit_5(cli, con_features):
    r, _ = cli("features", "suppress", "1", "--doc", "NoExiste.par")
    assert r.exit_code == 5


def test_suppress_sin_argumento_da_exit_2(cli, con_features):
    r, _ = cli("features", "suppress")
    assert r.exit_code == 2


def test_suppress_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("features", "suppress", "1")
    assert r.exit_code == 3 and sobre["ok"] is False
