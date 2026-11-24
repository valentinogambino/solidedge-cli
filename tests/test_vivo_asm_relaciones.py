"""Prueba de `asm relate` y `asm relations` contra Solid Edge abierto. No corre por defecto.

Crea una caja de 50x30x20 mm, un cilindro de 20 mm de diámetro y 40 mm de alto y un ensamble con dos
ocurrencias de cada uno, todo guardado en `tmp_path`; relaciona caras (mate, align con offset,
axial), lista y borra relaciones, y al terminar cierra con `--discard` solo esos tres documentos.
No toca documentos ajenos.

Caras de la caja extruida (índices de `edges list`, verificados en vivo): la 1 es la x=0 y la 3 es
la x=50 mm. El cilindro trae la cara cilíndrica como cara 1.
"""

import json
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from se_cli.cli import app

MM = 1e-3


def _correr(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


def _ok(*args: str) -> dict:
    r, sobre = _correr(*args)
    assert r.exit_code == 0, sobre
    return sobre["data"]


def _nuevo_guardado(tipo: str, destino) -> str:
    nombre = _ok("docs", "new", tipo)["nombre"]
    _ok("docs", "save-as", str(destino), nombre)
    return nombre


@contextmanager
def _documentos_propios(carpeta):
    """Caja, cilindro y ensamble vacío guardados; al salir cierra solo esos documentos."""
    caja, cilindro, conjunto = (
        carpeta / "caja_rel_live.par",
        carpeta / "cil_rel_live.par",
        carpeta / "conj_rel_live.asm",
    )
    creados = []
    try:
        creados.append(_nuevo_guardado("part", caja))
        _ok("sketch", "rect", "--width", "50mm", "--height", "30mm", "--doc", caja.name)
        _ok("extrude", "20mm", "--doc", caja.name)
        _ok("docs", "save", caja.name)
        creados.append(_nuevo_guardado("part", cilindro))
        _ok("sketch", "circle", "--radius", "10mm", "--doc", cilindro.name)
        _ok("extrude", "40mm", "--doc", cilindro.name)
        _ok("docs", "save", cilindro.name)
        creados.append(_nuevo_guardado("assembly", conjunto))
        yield caja, cilindro, conjunto.name
    finally:
        r, sobre = _correr("docs", "list")
        propios = {*creados, caja.name, cilindro.name, conjunto.name}
        # El ensamble primero: las piezas son sus referencias.
        for doc in sorted(sobre["data"]["documentos"], key=lambda d: d["tipo"] != "assembly"):
            if doc["nombre"] in propios:
                _correr("docs", "close", doc["nombre"], "--discard")


def _relaciones(doc: str) -> list[dict]:
    return _ok("asm", "relations", "list", "--units", "mm", "--doc", doc)["relaciones"]


@pytest.mark.live
def test_relaciones_en_un_ensamble(tmp_path):
    with _documentos_propios(tmp_path) as (caja, cilindro, conjunto):
        d = ["--doc", conjunto]
        for pieza, en in (
            (caja, "0,0,0"),
            (caja, "200mm,0,0"),
            (cilindro, "0,300mm,0"),
            (cilindro, "200mm,300mm,0"),
        ):
            _ok("asm", "add", str(pieza), "--at", en, *d)

        # La cara cilíndrica es la que `edges list` marca como cilindro.
        aristas = _ok("edges", "list", "--doc", cilindro.name)["aristas"]
        cara_cilindro = next(
            c["indice"] for a in aristas for c in a["caras"] if c["tipo"] == "cilindro"
        )

        # Todas nacen fijas: con las dos fijas no hay relación posible y se informa cómo seguir.
        r, sobre = _correr("asm", "relate", "mate", "--a", "1:3", "--b", "2:1", *d)
        assert r.exit_code == 4, sobre
        assert "se asm ground <occ> --release" in sobre["error"]["message"]
        assert [x["tipo"] for x in _relaciones(conjunto)] == ["ground"] * 4

        _ok("asm", "ground", "2", "--release", *d)
        _ok("asm", "ground", "4", "--release", *d)

        # mate: la cara x=0 de la segunda caja queda sobre la x=50 mm de la primera.
        mate = _ok("asm", "relate", "mate", "--a", "1:3", "--b", "2:1", "--units", "mm", *d)
        assert mate["tipo"] == "mate" and mate["estado"] == "resuelta"
        assert mate["offset"] == 0.0
        segunda = mate["ocurrencias"][1]
        assert segunda["fija"] is False
        assert segunda["posicion"] == pytest.approx([50.0, 0.0, 0.0], abs=1e-6)
        lista = _relaciones(conjunto)
        assert [x["tipo"] for x in lista] == ["ground", "ground", "mate"]
        assert lista[-1]["indice"] == mate["indice"]

        # Se borra y se hace un align con offset: la cara x=50 de la segunda caja a +5 mm de la
        # x=50 de la primera deja la segunda en x=5 mm.
        borrada = _ok("asm", "relations", "delete", str(mate["indice"]), *d)
        assert borrada["removed"] is True and borrada["tipo"] == "mate"
        align = _ok(
            *("asm", "relate", "align", "--a", "1:3", "--b", "2:3"),
            *("--offset", "5mm", "--units", "mm", *d),
        )
        assert align["tipo"] == "align" and align["offset"] == pytest.approx(5.0)
        assert align["ocurrencias"][1]["posicion"] == pytest.approx([5.0, 0.0, 0.0], abs=1e-6)
        assert _relaciones(conjunto)[-1]["tipo"] == "align"
        assert _relaciones(conjunto)[-1]["offset"] == pytest.approx(5.0)

        # axial: los dos cilindros quedan coaxiales (la segunda pasa de x=200 a x=0).
        axial = _ok(
            *("asm", "relate", "axial", "--a", f"3:{cara_cilindro}"),
            *("--b", f"cil_rel_live.par:2:{cara_cilindro}", "--units", "mm", *d),
        )
        assert axial["tipo"] == "axial" and axial["offset"] is None
        assert axial["ocurrencias"][1]["posicion"][:2] == pytest.approx([0.0, 300.0], abs=1e-6)
        tipos = [x["tipo"] for x in _relaciones(conjunto)]
        assert tipos == ["ground", "ground", "align", "axial"]

        # Tipo de cara incompatible: se detecta antes de tocar Solid Edge.
        r, sobre = _correr("asm", "relate", "mate", "--a", f"3:{cara_cilindro}", "--b", "2:1", *d)
        assert r.exit_code == 2, sobre
        r, sobre = _correr("asm", "relate", "mate", "--a", "1:99", "--b", "2:1", *d)
        assert r.exit_code == 5, sobre
        r, sobre = _correr("asm", "relations", "delete", "99", *d)
        assert r.exit_code == 5, sobre

        # Borrar las dos relaciones creadas deja solo las ground.
        _ok("asm", "relations", "delete", "4", *d)
        _ok("asm", "relations", "delete", "3", *d)
        assert [x["tipo"] for x in _relaciones(conjunto)] == ["ground", "ground"]
