"""Prueba de `features suppress|unsuppress` contra Solid Edge abierto. No corre por defecto.

Crea una pieza propia (`docs new part`), la guarda en `tmp_path`, extruye, suprime y reactiva la
extrusión, y al terminar cierra con `--discard` solo ese documento. No toca documentos ajenos.
"""

import json
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


@contextmanager
def _pieza_propia(destino):
    r, sobre = _correr("docs", "new", "part")
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    try:
        r, sobre = _correr("docs", "save-as", str(destino), nombre)
        assert r.exit_code == 0, sobre
        yield destino.name
    finally:
        r, sobre = _correr("docs", "list")
        for doc in sobre["data"]["documentos"]:
            if doc["nombre"] in (nombre, destino.name):
                _correr("docs", "close", doc["nombre"], "--discard")


def _operaciones(doc: str) -> list[dict]:
    r, sobre = _correr("features", "list", "--doc", doc)
    assert r.exit_code == 0, sobre
    return sobre["data"]["operaciones"]


@pytest.mark.live
def test_suprimir_y_reactivar_una_extrusion(tmp_path):
    with _pieza_propia(tmp_path / "suprimir.par") as doc:
        d = ["--doc", doc]
        r, sobre = _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("extrude", "10mm", *d)
        assert r.exit_code == 0, sobre
        extrusion = next(o for o in _operaciones(doc) if o["tipo"] == "ExtrudedProtrusion")
        assert extrusion["suprimida"] is False

        r, sobre = _correr("features", "suppress", str(extrusion["indice"]), *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["suprimida"] is True and sobre["data"]["changed"] is True
        assert sobre["data"]["nombre"] == extrusion["nombre"]
        assert _operaciones(doc)[extrusion["indice"] - 1]["suprimida"] is True

        r, sobre = _correr("features", "suppress", extrusion["nombre"], *d)
        assert r.exit_code == 0 and sobre["data"]["changed"] is False

        r, sobre = _correr("features", "unsuppress", extrusion["nombre"], *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["suprimida"] is False and sobre["data"]["changed"] is True
        assert _operaciones(doc)[extrusion["indice"] - 1]["suprimida"] is False

        r, _ = _correr("features", "suppress", "NoExiste", *d)
        assert r.exit_code == 5
        r, _ = _correr("features", "suppress", "999", *d)
        assert r.exit_code == 5


@pytest.mark.live
def test_features_list_informa_si_la_lectura_ensucio(tmp_path):
    """`modificado_por_lectura` coincide con lo que `docs list` ve después de leer."""
    destino = tmp_path / "leer.par"
    with _pieza_propia(destino) as doc:
        d = ["--doc", doc]
        assert (
            _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *d)[0].exit_code == 0
        )
        assert _correr("extrude", "10mm", *d)[0].exit_code == 0
        assert _correr("docs", "save", doc)[0].exit_code == 0
        assert _correr("docs", "close", doc)[0].exit_code == 0
        assert _correr("docs", "open", str(destino))[0].exit_code == 0

        r, sobre = _correr("features", "list", *d)
        assert r.exit_code == 0, sobre
        _, lista = _correr("docs", "list")
        modificado = next(x for x in lista["data"]["documentos"] if x["nombre"] == doc)[
            "modificado"
        ]
        assert sobre["data"]["modificado_por_lectura"] is modificado
        assert ("advertencia" in sobre["data"]) is modificado
