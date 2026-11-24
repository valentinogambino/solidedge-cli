"""Prueba de `se draft parts-list` y `se draft dim` contra Solid Edge abierto. No corre por defecto.

En `tmp_path` arma una caja extruida, un ensamble con dos ocurrencias y los Drafts de ambos; al
terminar cierra con `--discard` solo esos documentos. No toca documentos ajenos.
"""

import json
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
    r, sobre = _correr("docs", "save-as", str(destino), sobre["data"]["nombre"])
    assert r.exit_code == 0, sobre


@contextmanager
def _modelos_propios(carpeta):
    """Caja extruida y ensamble con dos cajas, guardados; al salir cierra solo lo propio."""
    pieza, conjunto = carpeta / "caja_ann_live.par", carpeta / "conj_ann_live.asm"
    propios = {pieza.name, conjunto.name, "caja_ann_live.dft", "conj_ann_live.dft"}
    try:
        _nuevo_guardado("part", pieza)
        d = ["--doc", pieza.name]
        r, sobre = _correr("sketch", "rect", "--width", "50mm", "--height", "30mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("extrude", "20mm", *d)
        assert r.exit_code == 0, sobre
        r, sobre = _correr("docs", "save", pieza.name)
        assert r.exit_code == 0, sobre
        _nuevo_guardado("assembly", conjunto)
        for desplazamiento in ("0,0,0", "100mm,0,0"):
            r, sobre = _correr(
                "asm", "add", str(pieza), "--at", desplazamiento, "--doc", conjunto.name
            )
            assert r.exit_code == 0, sobre
        r, sobre = _correr("docs", "save", conjunto.name)
        assert r.exit_code == 0, sobre
        yield pieza, conjunto
    finally:
        r, sobre = _correr("docs", "list")
        # Los Drafts primero, luego el ensamble: la pieza es su referencia.
        orden = {"draft": 0, "assembly": 1}
        for doc in sorted(sobre["data"]["documentos"], key=lambda d: orden.get(d["tipo"], 2)):
            if doc["nombre"] in propios:
                _correr("docs", "close", doc["nombre"], "--discard")


def _draft_de(modelo, *vistas: str):
    r, sobre = _correr(
        "draft", "from-part", str(modelo), "--views", ",".join(vistas), "--keep-open"
    )
    assert r.exit_code == 0, sobre
    return modelo.with_suffix(".dft").name


@pytest.mark.live
def test_lista_de_piezas_con_globos_de_un_ensamble(tmp_path):
    with _modelos_propios(tmp_path) as (pieza, conjunto):
        draft = _draft_de(conjunto, "front", "iso")

        r, sobre = _correr("draft", "parts-list", "--view", "1", "--balloons", "--doc", draft)
        assert r.exit_code == 0, sobre
        data = sobre["data"]
        assert data["vista"] == 1 and data["globos"] is True
        # Dos ocurrencias de la misma pieza: una sola fila, un solo globo.
        assert data["filas"] == 1 and data["globos_agregados"] == 1

        # Una vista de pieza no es un ensamble.
        draft_pieza = _draft_de(pieza, "front", "top")
        r, sobre = _correr("draft", "parts-list", "--doc", draft_pieza)
        assert r.exit_code == 2, sobre

        r, sobre = _correr("draft", "parts-list", "--view", "9", "--doc", draft)
        assert r.exit_code == 5, sobre


@pytest.mark.live
def test_cotas_automaticas_de_la_vista_de_una_pieza(tmp_path):
    with _modelos_propios(tmp_path) as (pieza, _conjunto):
        draft = _draft_de(pieza, "front", "top")

        r, sobre = _correr("draft", "dim", "--view", "1", "--auto", "--doc", draft)
        assert r.exit_code == 0, sobre
        data = sobre["data"]
        assert data["vista"] == 1 and data["cotas_agregadas"] > 0
        assert data["cotas_despues"] == data["cotas_antes"] + data["cotas_agregadas"]

        # Repetirlo no agrega nada nuevo.
        r, sobre = _correr("draft", "dim", "--view", "1", "--auto", "--doc", draft)
        assert r.exit_code == 0 and sobre["data"]["cotas_agregadas"] == 0

        r, sobre = _correr("draft", "dim", "--view", "1", "--doc", draft)
        assert r.exit_code == 2, sobre
        r, sobre = _correr("draft", "dim", "--view", "9", "--auto", "--doc", draft)
        assert r.exit_code == 5, sobre
