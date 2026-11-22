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
