"""Prueba de `edges list`, `round` y `chamfer` contra Solid Edge abierto. No corre por defecto.

Crea una caja propia de 50x30x20 mm guardada en `tmp_path`, le redondea y le achaflana aristas y
al terminar cierra con `--discard` solo ese documento. No toca documentos ajenos.
"""

import json
import math
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app

VOLUMEN_DE_LA_CAJA = 50e-3 * 30e-3 * 20e-3


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@contextmanager
def _caja_propia(carpeta):
    """Caja de 50x30x20 mm guardada; al salir cierra solo ese documento."""
    destino = carpeta / "caja_aristas_live.par"
    r, sobre = _correr("docs", "new", "part")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    try:
        r, sobre = _correr("docs", "save-as", str(destino), nombre)
        assert r.exit_code == 0, sobre
        d = ["--doc", destino.name]
        r, sobre = _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("extrude", "20mm", *d)
        assert r.exit_code == 0, sobre
        yield destino.name
    finally:
        r, sobre = _correr("docs", "list")
        for doc in sobre["data"]["documentos"]:
            if doc["nombre"] in (nombre, destino.name):
                _correr("docs", "close", doc["nombre"], "--discard")


def _aristas(doc: str) -> list[dict]:
    r, sobre = _correr("edges", "list", "--units", "mm", "--doc", doc)
    assert r.exit_code == 0, sobre
    assert sobre["data"]["unidades"] == {"longitud": "mm"}
    return sobre["data"]["aristas"]


def _volumen(doc: str) -> float:
    r, sobre = _correr("mass", "--density", "7850", "--doc", doc)
    assert r.exit_code == 0, sobre
    return sobre["data"]["volumen"]


def _operaciones(doc: str) -> list[tuple[str, str]]:
    r, sobre = _correr("features", "list", "--doc", doc)
    assert r.exit_code == 0, sobre
    return [(o["nombre"], o["estado"]) for o in sobre["data"]["operaciones"]]


def _lista(aristas: list[dict]) -> str:
    return ",".join(str(a["indice"]) for a in aristas)


def _lineas_a_z(aristas: list[dict], z: float) -> list[dict]:
    return [
        a
        for a in aristas
        if a["tipo"] == "linea" and a["inicio"][2] == pytest.approx(z) == a["fin"][2]
    ]


@pytest.mark.live
def test_caja_con_redondeos_y_chaflanes(tmp_path):
    with _caja_propia(tmp_path) as doc:
        d = ["--doc", doc]
        assert _volumen(doc) == pytest.approx(VOLUMEN_DE_LA_CAJA, rel=1e-9)

        # Una caja tiene 12 aristas rectas (4 de cada largo) y 6 caras planas.
        aristas = _aristas(doc)
        assert [a["indice"] for a in aristas] == list(range(1, 13))
        assert {a["tipo"] for a in aristas} == {"linea"}
        assert sorted(round(a["longitud"]) for a in aristas) == [20] * 4 + [30] * 4 + [50] * 4
        assert all(len(a["caras"]) == 2 for a in aristas)
        r, sobre = _correr("edges", "list", *d)
        assert sobre["data"]["cantidad_caras"] == 6
        assert sobre["data"]["aristas"][0]["longitud"] in (0.02, 0.03, 0.05)

        # Redondeo de 2 mm en las cuatro aristas verticales.
        verticales = [a for a in aristas if a["inicio"][:2] == a["fin"][:2]]
        assert len(verticales) == 4
        r, sobre = _correr("round", "2mm", "--edges", _lista(verticales), "--units", "mm", *d)
        assert r.exit_code == 0, sobre
        redondeo = sobre["data"]
        assert redondeo["nombre"] == "Round_1" and redondeo["indice"] == 2
        assert redondeo["cantidad_aristas"] == 4 and redondeo["radio"] == pytest.approx(2.0)
        assert redondeo["estado"] == "ok"
        # Cada arista vertical quita (1 - pi/4) r^2 por la altura.
        quitado = 4 * (1 - math.pi / 4) * 0.002**2 * 0.02
        assert redondeo["volumen_quitado_si"] == pytest.approx(quitado, rel=1e-6)
        despues_del_redondeo = _volumen(doc)
        assert despues_del_redondeo == pytest.approx(VOLUMEN_DE_LA_CAJA - quitado, rel=1e-6)

        # Los índices cambian: ahora hay arcos y más aristas.
        aristas = _aristas(doc)
        assert len(aristas) > 12 and "arco" in {a["tipo"] for a in aristas}

        # Chaflán de 1 mm en las aristas rectas de la base (con los índices releídos).
        base = _lineas_a_z(aristas, 0.0)
        assert len(base) == 4
        r, sobre = _correr("chamfer", "1mm", "--edges", _lista(base), "--units", "mm", *d)
        assert r.exit_code == 0, sobre
        chaflan = sobre["data"]
        assert chaflan["nombre"] == "Chamfer_1" and chaflan["indice"] == 3
        assert chaflan["distancia"] == pytest.approx(1.0) and chaflan["angulo"] is None
        despues_del_chaflan = _volumen(doc)
        assert despues_del_chaflan < despues_del_redondeo

        # Chaflán distancia + ángulo en las aristas rectas de la tapa (comparten una cara).
        tapa = _lineas_a_z(_aristas(doc), 20.0)
        assert len(tapa) == 4
        r, sobre = _correr(
            "chamfer", "1mm", "--angle", "30deg", "--edges", _lista(tapa), "--units", "mm,deg", *d
        )
        assert r.exit_code == 0, sobre
        assert sobre["data"]["angulo"] == pytest.approx(30.0)
        assert sobre["data"]["distancia"] == pytest.approx(1.0)
        assert _volumen(doc) < despues_del_chaflan

        assert _operaciones(doc) == [
            ("ExtrudedProtrusion_1", "ok"),
            ("Round_1", "ok"),
            ("Chamfer_1", "ok"),
            ("Chamfer_2", "ok"),
        ]


@pytest.mark.live
def test_errores_no_dejan_operaciones_rotas(tmp_path):
    with _caja_propia(tmp_path) as doc:
        d = ["--doc", doc]
        antes = _operaciones(doc)
        volumen = _volumen(doc)

        # Valores imposibles: Solid Edge no avisa, deja una operación fallida que se borra.
        r, sobre = _correr("round", "500mm", "--edges", "all", *d)
        assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
        assert sobre["error"]["details"]["borrada"] is True
        r, sobre = _correr("chamfer", "500mm", "--edges", "1-4", *d)
        assert r.exit_code == 4 and sobre["error"]["details"]["borrada"] is True
        assert _operaciones(doc) == antes
        assert _volumen(doc) == pytest.approx(volumen)

        # El modelo sigue sirviendo.
        r, sobre = _correr("round", "1mm", "--edges", "1", *d)
        assert r.exit_code == 0, sobre

        assert _correr("round", "1mm", "--edges", "99", *d)[0].exit_code == 5
        assert _correr("chamfer", "1mm", "--edges", "99", *d)[0].exit_code == 5
        assert _correr("round", "0", "--edges", "1", *d)[0].exit_code == 2
        assert _correr("chamfer", "1mm", "--edges", "1", "--angle", "90deg", *d)[0].exit_code == 2
        assert _correr("round", "1mm", *d)[0].exit_code == 2
