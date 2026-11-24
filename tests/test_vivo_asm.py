"""Prueba de `asm add|ground|move|remove` contra Solid Edge abierto. No corre por defecto.

Crea una pieza propia (caja extruida) y un ensamble propio, ambos guardados en `tmp_path`;
inserta la caja dos veces, la fija, la mueve y la borra, y al terminar cierra con `--discard` solo
esos dos documentos. No toca documentos ajenos.
"""

import json
import math
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


def _nuevo_guardado(tipo: str, destino):
    r, sobre = _correr("docs", "new", tipo)
    assert r.exit_code == 0, sobre
    nombre = sobre["data"]["nombre"]
    r, sobre = _correr("docs", "save-as", str(destino), nombre)
    assert r.exit_code == 0, sobre
    return nombre


@contextmanager
def _documentos_propios(carpeta):
    """Caja extruida y ensamble vacío, guardados; al salir cierra solo esos documentos."""
    pieza, conjunto = carpeta / "caja_asm_live.par", carpeta / "conj_asm_live.asm"
    creados = []
    try:
        creados.append(_nuevo_guardado("part", pieza))
        d = ["--doc", pieza.name]
        r, sobre = _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("extrude", "20mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("docs", "save", pieza.name)
        assert r.exit_code == 0, sobre
        creados.append(_nuevo_guardado("assembly", conjunto))
        yield pieza, conjunto.name
    finally:
        r, sobre = _correr("docs", "list")
        propios = {*creados, pieza.name, conjunto.name}
        # El ensamble primero: la pieza es su referencia.
        for doc in sorted(sobre["data"]["documentos"], key=lambda d: d["tipo"] != "assembly"):
            if doc["nombre"] in propios:
                _correr("docs", "close", doc["nombre"], "--discard")


def _arbol(doc: str) -> list[dict]:
    r, sobre = _correr("asm", "tree", "--doc", doc)
    assert r.exit_code == 0, sobre
    return sobre["data"]["arbol"]


@pytest.mark.live
def test_armar_un_ensamble_con_dos_ocurrencias(tmp_path):
    with _documentos_propios(tmp_path) as (pieza, conjunto):
        d = ["--doc", conjunto]

        # Una en el origen y otra desplazada y girada.
        r, sobre = _correr("asm", "add", str(pieza), *d)
        assert r.exit_code == 0, sobre
        primera = sobre["data"]
        assert primera["indice"] == 1 and primera["fija"] is True
        assert primera["posicion"] == [0.0, 0.0, 0.0]

        r, sobre = _correr(
            "asm", "add", str(pieza), "--at", "100mm,0,5mm", "--rot", "0,0,90deg", *d
        )
        assert r.exit_code == 0, sobre
        segunda = sobre["data"]
        assert segunda["indice"] == 2 and segunda["nombre"] != primera["nombre"]
        assert segunda["posicion"] == pytest.approx([0.1, 0.0, 0.005])
        assert segunda["rotacion"] == pytest.approx([0.0, 0.0, math.pi / 2])

        nodo = _arbol(conjunto)[0]
        assert nodo["cantidad"] == 2 and nodo["indices"] == [1, 2]

        # Ground: toda ocurrencia nace fija; se suelta y se vuelve a fijar.
        r, sobre = _correr("asm", "ground", segunda["nombre"].upper(), *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["fija"] is True and sobre["data"]["changed"] is False
        r, sobre = _correr("asm", "ground", "2", "--release", *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["fija"] is False and sobre["data"]["changed"] is True
        r, sobre = _correr("asm", "ground", "2", *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["fija"] is True and sobre["data"]["changed"] is True

        # Move: relativo, absoluto y solo rotación.
        r, sobre = _correr("asm", "move", "2", "--by", "10mm,0,0", "--units", "mm,deg", *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["posicion"] == pytest.approx([110.0, 0.0, 5.0])
        assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, 90.0])

        r, sobre = _correr("asm", "move", "2", "--at", "0,40mm,0", "--units", "mm,deg", *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["posicion"] == pytest.approx([0.0, 40.0, 0.0])
        assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, 90.0])

        r, sobre = _correr("asm", "move", "2", "--rot", "0,0,0", "--units", "mm,deg", *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["posicion"] == pytest.approx([0.0, 40.0, 0.0])
        assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, 0.0])

        # Errores.
        assert _correr("asm", "ground", "9", *d)[0].exit_code == 5
        assert _correr("asm", "move", "nada", "--by", "1mm,0,0", *d)[0].exit_code == 5
        assert _correr("asm", "remove", "nada", *d)[0].exit_code == 5
        assert _correr("asm", "add", str(tmp_path / "no_existe.par"), *d)[0].exit_code == 5
        assert _correr("asm", "add", str(pieza), "--doc", pieza.name)[0].exit_code == 2

        # Remove: borra la ocurrencia, no el archivo.
        r, sobre = _correr("asm", "remove", segunda["nombre"], *d)
        assert r.exit_code == 0, sobre
        assert sobre["data"]["removed"] is True and sobre["data"]["restantes"] == 1
        nodo = _arbol(conjunto)[0]
        assert nodo["cantidad"] == 1 and nodo["nombre"] == primera["nombre"]
        assert pieza.exists()
