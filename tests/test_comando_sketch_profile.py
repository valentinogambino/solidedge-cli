"""`se sketch profile` sobre el COM falso."""

import json

import pytest
from com_falso import com_error, con_modelado
from test_croquis import estadio

from se_cli.cli import app


@pytest.fixture
def pieza(app_falsa):
    return con_modelado(app_falsa.agregar_documento("Part1.par", tipo=1))


@pytest.fixture
def archivo(tmp_path):
    def escribir(datos: dict | None = None) -> str:
        ruta = tmp_path / "perfil.json"
        ruta.write_text(json.dumps(datos or estadio()), encoding="utf-8")
        return str(ruta)

    return escribir


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


def test_camino_feliz_crea_entidades_y_relaciones(cli, app_falsa, pieza, archivo):
    r, sobre = cli("sketch", "profile", archivo())

    assert r.exit_code == 0, r.output
    datos = sobre["data"]
    assert datos["perfil"] == 1 and datos["plano"] == "top" and datos["valido"] is True
    assert datos["tipo"] == "perfil" and datos["codigo_end"] == -103
    assert datos["entidades"] == {"lineas": 2, "arcos": 2, "circulos": 0}
    assert datos["restricciones"] == {
        "aplicadas": 8,
        "por_tipo": {"connect": 4, "horizontal": 1, "tangent": 2, "equal": 1},
    }
    assert datos["dimensiones_si"] == pytest.approx(
        {"x_min": -0.01, "y_min": 0.0, "x_max": 0.06, "y_max": 0.02}
    )
    assert [c[1:] for c in _llamadas(app_falsa, "Lines2d.AddBy2Points")] == [
        (0.0, 0.0, 0.05, 0.0),
        (0.05, 0.02, 0.0, 0.02),
    ]
    arcos = [c[1:] for c in _llamadas(app_falsa, "Arcs2d.AddByCenterStartEnd")]
    assert arcos[0] == (0.05, 0.01, 0.05, 0.0, 0.05, 0.02)  # ccw: tal cual
    assert arcos[1] == (0.0, 0.01, 0.0, 0.02, 0.0, 0.0)  # cw: start y end intercambiados
    assert _llamadas(app_falsa, "Profile.End") == [("Profile.End", 8193)]  # Closed | AllowNested
    assert app_falsa.historial_alertas == [False, True]
    assert not _llamadas(app_falsa, "ProfileSet.Delete")


def test_keypoints_de_arco_y_linea(cli, app_falsa, pieza, archivo):
    cli("sketch", "profile", archivo())
    uniones = [c[1:] for c in _llamadas(app_falsa, "Relations2d.AddKeypoint")]
    l1 = ("line", 0.0, 0.0, 0.05, 0.0)
    a1 = ("arc", 0.05, 0.01, 0.05, 0.0, 0.05, 0.02)
    a2 = ("arc", 0.0, 0.01, 0.0, 0.02, 0.0, 0.0)  # cw: se creó con start y end cruzados
    # l1.start con a2.start: el start del usuario en un arco cw es el keypoint 2 (fin real)
    assert (l1, 0, a2, 2) in uniones
    assert (l1, 1, a1, 1) in uniones  # l1.end con a1.start (ccw: start = 1)
    assert any(u[0] == a1 and u[1] == 2 for u in uniones)  # a1.end = 2


def test_tipos_de_relacion_y_argumentos(cli, app_falsa, pieza, archivo):
    cli("sketch", "profile", archivo())
    assert len(_llamadas(app_falsa, "Relations2d.AddHorizontal")) == 1
    tangentes = _llamadas(app_falsa, "Relations2d.AddTangent")
    assert [t[1][0] for t in tangentes] == ["line", "arc"]
    assert [t[2][0] for t in tangentes] == ["arc", "line"]
    assert len(_llamadas(app_falsa, "Relations2d.AddEqual")) == 1


def test_circulo_concentrico_y_perfil_de_solo_circulos(cli, app_falsa, pieza, archivo):
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "c1", "type": "circle", "center": [0, 0], "radius": 5},
            {"id": "c2", "type": "circle", "center": [0, 0], "radius": 2},
        ],
        "constraints": [{"type": "concentric", "a": "c1", "b": "c2"}],
    }
    r, sobre = cli("sketch", "profile", archivo(datos))
    assert r.exit_code == 0, r.output
    assert sobre["data"]["codigo_end"] == 0
    assert _llamadas(app_falsa, "Relations2d.AddConcentric")[0][1][0] == "circle"
    assert len(_llamadas(app_falsa, "Circles2d.AddByCenterRadius")) == 2


def test_desde_la_entrada_estandar(cli, app_falsa, pieza):
    r = cli.runner.invoke(app, ["--json", "sketch", "profile", "-"], input=json.dumps(estadio()))
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["data"]["perfil"] == 1


def test_entrada_estandar_en_dry_run(cli, app_falsa, pieza):
    r = cli.runner.invoke(
        app, ["--json", "--dry-run", "sketch", "profile", "-"], input=json.dumps(estadio())
    )
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["data"]["conteos"]["restricciones"] == 8


def test_dry_run_devuelve_el_plan_sin_tocar_com(cli, app_falsa, pieza, archivo):
    r, sobre = cli.con("--dry-run", "sketch", "profile", archivo())

    assert r.exit_code == 0, r.output
    datos = sobre["data"]
    assert datos["dry_run"] is True and datos["accion"] == "sketch.profile"
    assert datos["entidades"][0]["hasta"] == [0.05, 0.0]
    assert datos["conteos"] == {"lineas": 2, "arcos": 2, "circulos": 0, "restricciones": 8}
    assert app_falsa.registro == []


def test_dry_run_valida_el_json(cli, app_falsa, pieza, archivo):
    datos = estadio()
    datos["entities"][0]["to"] = [40, 0]
    r, sobre = cli.con("--dry-run", "sketch", "profile", archivo(datos))
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_readonly_bloquea(cli, app_falsa, pieza, archivo):
    r, sobre = cli.con("--readonly", "sketch", "profile", archivo())
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.escrituras == []


def test_archivo_inexistente_es_exit_5(cli, pieza, tmp_path):
    r, sobre = cli("sketch", "profile", str(tmp_path / "no.json"))
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"


def test_json_invalido_es_exit_2(cli, app_falsa, pieza, tmp_path):
    ruta = tmp_path / "mal.json"
    ruta.write_text("{ no es json", encoding="utf-8")
    r, sobre = cli("sketch", "profile", str(ruta))
    assert r.exit_code == 2 and "JSON inválido" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


@pytest.mark.parametrize(
    "mutar",
    [
        lambda d: d["entities"][0].update(to=[49, 0]),  # no cierra ni cumple lo declarado
        lambda d: d["entities"][1].update(end=[50, 25]),  # radios distintos
        lambda d: d["constraints"].append({"type": "vertical", "on": "l1"}),
        lambda d: d["constraints"].append({"type": "dimension", "on": "l1"}),
        lambda d: d.update(close=False),
        lambda d: d.update(extra=1),
        lambda d: d["entities"].append({"id": "l1", "type": "line", "from": [0, 0], "to": [1, 1]}),
    ],
)
def test_errores_de_validacion_no_tocan_solid_edge(cli, app_falsa, pieza, archivo, mutar):
    datos = estadio()
    mutar(datos)
    r, sobre = cli("sketch", "profile", archivo(datos))
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == [] and app_falsa.registro == []


def test_documento_que_no_modela_da_exit_2(cli, app_falsa, archivo):
    app_falsa.agregar_documento("Draft1.dft", tipo=2)
    r, _ = cli("sketch", "profile", archivo())
    assert r.exit_code == 2


def test_modo_sincronico_da_exit_2(cli, app_falsa, archivo):
    con_modelado(app_falsa.agregar_documento("Part1.par", tipo=1), modo=1)
    r, sobre = cli("sketch", "profile", archivo())
    assert r.exit_code == 2 and "sincrónico" in sobre["error"]["message"]
    assert not _llamadas(app_falsa, "ProfileSets.Add")


def test_plano_inexistente_no_crea_nada(cli, app_falsa, pieza, archivo):
    datos = estadio()
    datos["plane"] = "7"
    r, _ = cli("sketch", "profile", archivo(datos))
    assert r.exit_code == 2 and not _llamadas(app_falsa, "ProfileSets.Add")


# --- fallo a mitad: se borra el perfil --------------------------------------------------------


@pytest.mark.parametrize(
    ("falla", "etapa", "extra"),
    [
        ("ProfileSets.Add", "perfil", {}),
        ("AddBy2Points", "entidades", {"entidad": "l1"}),
        ("AddByCenterStartEnd", "entidades", {"entidad": "a1"}),
        ("Relations2d.AddKeypoint", "restricciones", {"restriccion": 1, "tipo": "connect"}),
        ("Relations2d.AddTangent", "restricciones", {"tipo": "tangent"}),
        ("End", "cierre", {}),
    ],
)
def test_falla_a_mitad_borra_el_perfil_y_da_exit_4(
    cli, app_falsa, pieza, archivo, falla, etapa, extra
):
    pieza.fallar(falla, com_error(0x80004005, "Falló", "Falló la operación"))

    r, sobre = cli("sketch", "profile", archivo())

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
    detalles = sobre["error"]["details"]
    assert detalles["etapa"] == etapa
    for clave, valor in extra.items():
        assert detalles[clave] == valor
    if falla == "ProfileSets.Add":
        assert detalles["perfil_borrado"] is False  # no llegó a crearse el conjunto
        return
    assert detalles["perfil_borrado"] is True
    assert len(_llamadas(app_falsa, "ProfileSet.Delete")) == 1
    assert len(pieza.ProfileSets.elementos) == 0


def test_falla_del_cierre_por_codigo_invalido(cli, app_falsa, pieza, archivo):
    pieza.codigo_end = 5
    r, sobre = cli("sketch", "profile", archivo())
    assert r.exit_code == 4
    assert sobre["error"]["details"]["etapa"] == "cierre"
    assert sobre["error"]["details"]["codigo_end"] == 5
    assert len(pieza.ProfileSets.elementos) == 0


def test_si_tampoco_se_puede_borrar_lo_dice(cli, app_falsa, pieza, archivo):
    pieza.fallar("Relations2d.AddTangent", com_error(0x80004005, "Falló"))
    pieza.fallar("ProfileSet.Delete", com_error(0x80004005, "No se pudo borrar"))
    r, sobre = cli("sketch", "profile", archivo())
    assert r.exit_code == 4 and sobre["error"]["details"]["perfil_borrado"] is False


def test_el_perfil_sirve_para_extrude(cli, app_falsa, pieza, tmp_path):
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "p", "type": "polyline", "points": [[0, 0], [20, 0], [20, 10], [0, 0]]}
        ],
    }
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    r, sobre = cli("sketch", "profile", str(ruta))
    assert r.exit_code == 0, r.output
    r, sobre = cli("extrude", "5mm", "--profile", str(sobre["data"]["perfil"]))
    assert r.exit_code == 0, r.output
    assert sobre["data"]["perfil"] == 1 and sobre["data"]["modelo_base"] is True
