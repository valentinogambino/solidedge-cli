"""Conversión de unidades: tabla, ida y vuelta, parseo."""

import math

import pytest

from se_cli.core.errors import ArgumentoInvalido
from se_cli.core.unidades import (
    FACTORES,
    a_si,
    convertir,
    de_si,
    dimension_de,
    parsear_unidades,
    parsear_valor,
)


@pytest.mark.parametrize(
    ("valor", "unidad", "si"),
    [
        (1, "m", 1.0),
        (1000, "mm", 1.0),
        (100, "cm", 1.0),
        (1, "in", 0.0254),
        (12, "in", 0.3048),
        (1, "ft", 0.3048),
        (1, "rad", 1.0),
        (180, "deg", math.pi),
        (90, "deg", math.pi / 2),
        (1, "kg", 1.0),
        (1000, "g", 1.0),
        (1, "lb", 0.45359237),
    ],
)
def test_tabla_de_conversiones_ida_y_vuelta(valor, unidad, si):
    assert a_si(valor, unidad) == pytest.approx(si, rel=1e-12)
    assert de_si(si, unidad) == pytest.approx(valor, rel=1e-12)


def test_pulgada_es_exacta():
    assert FACTORES["longitud"]["in"] == 0.0254
    assert FACTORES["longitud"]["ft"] == pytest.approx(12 * 0.0254, rel=1e-15)


@pytest.mark.parametrize(
    ("texto", "si", "unidad", "dimension"),
    [
        ("10mm", 0.01, "mm", "longitud"),
        ("2.5 in", 0.0635, "in", "longitud"),
        ("45deg", math.radians(45), "deg", "angulo"),
        ("0.01", 0.01, None, None),
        ("  3 kg ", 3.0, "kg", "masa"),
        ("-5mm", -0.005, "mm", "longitud"),
        (".5m", 0.5, "m", "longitud"),
        ("1e-3m", 0.001, "m", "longitud"),
        ("2lb", 0.90718474, "lb", "masa"),
    ],
)
def test_parseo_valido(texto, si, unidad, dimension):
    c = parsear_valor(texto)
    assert c.valor_si == pytest.approx(si, rel=1e-12)
    assert (c.unidad, c.dimension) == (unidad, dimension)


@pytest.mark.parametrize(
    "texto", ["1,5mm", "1,5", "abc", "", "10 parsecs", "mm", "1.2.3mm", "10 mm mm"]
)
def test_parseo_invalido_es_argumento_invalido(texto):
    with pytest.raises(ArgumentoInvalido):
        parsear_valor(texto)


def test_coma_decimal_explica_el_punto():
    with pytest.raises(ArgumentoInvalido, match="punto"):
        parsear_valor("1,5mm")


def test_dimension_de_unidad_desconocida():
    assert dimension_de("mm") == "longitud"
    with pytest.raises(ArgumentoInvalido):
        dimension_de("furlong")


def test_parsear_unidades():
    assert parsear_unidades(None) == {}
    assert parsear_unidades("mm") == {"longitud": "mm"}
    assert parsear_unidades("mm, deg,lb") == {"longitud": "mm", "angulo": "deg", "masa": "lb"}
    with pytest.raises(ArgumentoInvalido):
        parsear_unidades("mm,in")


def test_convertir():
    assert convertir(0.12, "longitud", {"longitud": "mm"}) == (pytest.approx(120.0), "mm")
    assert convertir(0.12, "longitud", {}) == (0.12, "m")
    assert convertir(math.pi, "angulo", {"angulo": "deg"}) == (pytest.approx(180.0), "deg")
    assert convertir(0.12, "longitud", {"angulo": "deg"}) == (0.12, "m")
    assert convertir(7.0, None, {"longitud": "mm"}) == (7.0, None)
