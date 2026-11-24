"""Pruebas de `se sketch profile` contra Solid Edge abierto. No corren por defecto (`-m live`).

Cada prueba crea una pieza propia, la guarda en `tmp_path` y al terminar la cierra con
`--discard` (solo esa, por nombre). No tocan documentos ajenos. Las formas tienen volumen
analítico conocido, así que verifican la geometría de verdad: un arco `cw` mal armado o un
keypoint equivocado cambiarían el volumen.
"""

import json
import math
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app

MM3 = 1e-9


def _correr(*args: str, entrada: str | None = None):
    resultado = CliRunner().invoke(app, ["--json", *args], input=entrada)
    return resultado, json.loads(resultado.stdout)


def _ok(*args: str, entrada: str | None = None) -> dict:
    r, sobre = _correr(*args, entrada=entrada)
    assert r.exit_code == 0, sobre
    return sobre["data"]


@contextmanager
def _pieza(carpeta, nombre: str):
    """Pieza nueva guardada en `carpeta`; al salir se cierra solo ella."""
    ruta = carpeta / nombre
    doc = _ok("docs", "new", "part")["nombre"]
    _ok("docs", "save-as", str(ruta), doc)
    try:
        yield nombre
    finally:
        r, sobre = _correr("docs", "list")
        for d in sobre["data"]["documentos"]:
            if d["nombre"] in (doc, nombre):
                _correr("docs", "close", d["nombre"], "--discard")


def _escribir(carpeta, datos: dict) -> str:
    ruta = carpeta / "perfil.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return str(ruta)


def _volumen(doc: str) -> float:
    return _ok("mass", "--density", "7850", "--doc", doc)["volumen"]


ESTADIO = {
    "version": 1,
    "plane": "top",
    "units": "mm",
    "tolerance": 0.001,
    "auto_connect": True,
    "close": True,
    "entities": [
        {"id": "l1", "type": "line", "from": [0, 0], "to": [50, 0]},
        {"id": "a1", "type": "arc", "center": [50, 10], "start": [50, 0], "end": [50, 20]},
        {"id": "l2", "type": "line", "from": [50, 20], "to": [0, 20]},
        {
            "id": "a2",
            "type": "arc",
            "center": [0, 10],
            "start": [0, 0],
            "end": [0, 20],
            "dir": "cw",
        },
    ],
    "constraints": [
        {"type": "horizontal", "on": "l1"},
        {"type": "horizontal", "on": "l2"},
        {"type": "tangent", "a": "l1", "b": "a1"},
        {"type": "tangent", "a": "a1", "b": "l2"},
        {"type": "tangent", "a": "l2", "b": "a2"},
        {"type": "tangent", "a": "a2", "b": "l1"},
        {"type": "equal", "a": "a1", "b": "a2"},
    ],
}


@pytest.mark.live
def test_ranura_con_un_arco_ccw_y_otro_cw_extruida(tmp_path):
    with _pieza(tmp_path, "ranura_sketch_profile_live.par") as doc:
        datos = _ok("sketch", "profile", _escribir(tmp_path, ESTADIO), "--doc", doc)
        assert datos["perfil"] == 1 and datos["valido"] is True
        assert datos["entidades"] == {"lineas": 2, "arcos": 2, "circulos": 0}
        assert datos["restricciones"]["por_tipo"] == {
            "connect": 4,
            "horizontal": 2,
            "tangent": 4,
            "equal": 1,
        }
        _ok("extrude", "10mm", "--profile", str(datos["perfil"]), "--doc", doc)
        esperado = (50 * 20 + math.pi * 10**2) * 10 * MM3
        assert _volumen(doc) == pytest.approx(esperado, rel=1e-6)


@pytest.mark.live
def test_placa_en_l_por_polilinea_con_un_circulo_adentro(tmp_path):
    forma = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "p1", "type": "polyline",
             "points": [[0, 0], [60, 0], [60, 20], [20, 20], [20, 50], [0, 50], [0, 0]]},
            {"id": "c1", "type": "circle", "center": [10, 35], "radius": 4},
        ],
        "constraints": [
            {"type": "horizontal", "on": "p1.1"},
            {"type": "vertical", "on": "p1.2"},
            {"type": "perpendicular", "a": "p1.1", "b": "p1.2"},
            {"type": "parallel", "a": "p1.1", "b": "p1.3"},
        ],
    }  # fmt: skip
    with _pieza(tmp_path, "placa_l_sketch_profile_live.par") as doc:
        # Por la entrada estándar, como la usaría un agente.
        datos = _ok("sketch", "profile", "-", "--doc", doc, entrada=json.dumps(forma))
        assert datos["entidades"] == {"lineas": 6, "arcos": 0, "circulos": 1}
        assert datos["codigo_end"] == 0  # unidos y anidado: cierra limpio
        _ok("extrude", "8mm", "--doc", doc)
        esperado = (60 * 20 + 20 * 30 - math.pi * 4**2) * 8 * MM3
        assert _volumen(doc) == pytest.approx(esperado, rel=1e-6)


@pytest.mark.live
def test_perfil_con_arco_para_revolve(tmp_path):
    medio_disco = {
        "version": 1,
        "plane": "front",
        "units": "mm",
        "entities": [
            {"id": "a", "type": "arc", "center": [15, 0], "start": [15, -10], "end": [15, 10]},
            {"id": "l", "type": "line", "from": [15, 10], "to": [15, -10]},
        ],
        "constraints": [{"type": "vertical", "on": "l"}],
    }
    with _pieza(tmp_path, "revolve_sketch_profile_live.par") as doc:
        datos = _ok("sketch", "profile", _escribir(tmp_path, medio_disco), "--doc", doc)
        assert datos["plano"] == "front"
        _ok("revolve", "--axis", "y", "--profile", str(datos["perfil"]), "--doc", doc)
        area = math.pi * 10**2 / 2
        centroide = 15 + 4 * 10 / (3 * math.pi)
        esperado = area * 2 * math.pi * centroide * MM3  # Pappus
        assert _volumen(doc) == pytest.approx(esperado, rel=1e-6)


@pytest.mark.live
def test_restriccion_que_las_coordenadas_no_cumplen_no_deja_perfiles(tmp_path):
    torcido = json.loads(json.dumps(ESTADIO))
    torcido["entities"][2]["to"] = [0, 22]  # l2 deja de ser horizontal
    with _pieza(tmp_path, "torcido_sketch_profile_live.par") as doc:
        r, sobre = _correr("sketch", "profile", _escribir(tmp_path, torcido), "--doc", doc)
        assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
        # sin perfiles nuevos: no hay nada que extruir
        r, sobre = _correr("extrude", "1mm", "--doc", doc)
        assert r.exit_code == 5 and sobre["error"]["details"] == {"perfiles": 0}


@pytest.mark.live
def test_falla_de_solid_edge_a_mitad_borra_el_perfil(tmp_path):
    duplicado = json.loads(json.dumps(ESTADIO))
    duplicado["constraints"].append({"type": "horizontal", "on": "l1"})  # Solid Edge la rechaza
    with _pieza(tmp_path, "falla_sketch_profile_live.par") as doc:
        r, sobre = _correr("sketch", "profile", _escribir(tmp_path, duplicado), "--doc", doc)
        assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
        detalles = sobre["error"]["details"]
        assert detalles["etapa"] == "restricciones" and detalles["tipo"] == "horizontal"
        assert detalles["perfil_borrado"] is True
        # el perfil a medio armar se borró: el documento sigue sin perfiles
        r, sobre = _correr("extrude", "1mm", "--doc", doc)
        assert r.exit_code == 5 and sobre["error"]["details"] == {"perfiles": 0}
        # y se puede crear el bueno enseguida, otra vez como perfil 1
        assert _ok("sketch", "profile", _escribir(tmp_path, ESTADIO), "--doc", doc)["perfil"] == 1
