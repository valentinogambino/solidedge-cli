"""Lógica pura del fondo generado (`core/fondos.py`), sin COM."""

import pytest
from com_falso import contenido_de_fondo

from se_cli.core import fondos
from se_cli.core.fondos import Objeto

TAM = {"A4": (0.297, 0.210), "A3": (0.420, 0.297), "A2": (0.594, 0.420), "A1": (0.841, 0.594)}


def _objetos(nombre):
    salida = []
    for o in contenido_de_fondo(nombre, *TAM[nombre]):
        if hasattr(o, "inicio"):
            salida.append(Objeto(o.Type, (*o.inicio, *o.fin)))
        else:
            salida.append(Objeto(o.Type, o.caja, getattr(o, "Text", None)))
    return salida


def test_pareja_del_mismo_diseno_da_anclajes_0_o_1():
    anclajes = fondos.anclajes_por_pareja(_objetos("A4"), _objetos("A3"), TAM["A4"], TAM["A3"])
    assert anclajes is not None
    assert anclajes[0] == (0.0, 0.0, 1.0, 0.0)  # borde inferior del marco
    assert anclajes[4] == (1.0, 0.0, 1.0, 0.0)  # lado izquierdo del rótulo: se corre en x
    assert all(c in (0.0, 1.0) for a in anclajes for c in a)


def test_pareja_de_otro_diseno_no_sirve():
    # A1 tiene otro margen y otro rótulo: no es un A2 trasladado.
    assert fondos.anclajes_por_pareja(_objetos("A1"), _objetos("A2"), TAM["A1"], TAM["A2"]) is None
    assert (
        fondos.anclajes_por_pareja(_objetos("A4"), _objetos("A4")[:-1], TAM["A4"], TAM["A3"])
        is None
    )


def test_mitades_rechaza_un_rotulo_que_cruza_el_centro():
    assert fondos.anclajes_por_mitades(_objetos("A4"), TAM["A4"]) is None


def test_mitades_en_a1_ancla_cada_cosa_a_su_esquina():
    anclajes = fondos.anclajes_por_mitades(_objetos("A1"), TAM["A1"])
    assert anclajes is not None
    assert anclajes[1] == (1.0, 0.0, 1.0, 1.0)  # lado derecho del marco: se estira
    assert anclajes[6] == (1.0, 0.0, 1.0, 0.0)  # texto del tamaño: abajo a la derecha
    assert anclajes[10] == (1.0, 1.0, 1.0, 1.0)  # tabla de revisiones: arriba a la derecha


def test_reubicar_estira_lineas_y_traslada_cajas():
    linea = Objeto(fondos.TIPO_LINEA, (0.01, 0.01, 0.287, 0.01))
    assert fondos.reubicar(linea, (0, 0, 1, 0), TAM["A4"], (0.210, 0.148)) == pytest.approx(
        (0.01, 0.01, 0.2, 0.01)
    )
    caja = Objeto(fondos.TIPO_TEXTO, (0.2, 0.02, 0.21, 0.03), "A4")
    assert fondos.reubicar(caja, (1, 0, 1, 0), TAM["A4"], (0.210, 0.148)) == pytest.approx(
        (0.113, 0.02, 0.123, 0.03)
    )


def test_dentro_de_la_hoja():
    assert fondos.dentro_de_la_hoja((0.0, 0.0, 0.21, 0.148), (0.210, 0.148))
    assert not fondos.dentro_de_la_hoja((-0.01, 0.0, 0.1, 0.1), (0.210, 0.148))


def test_elegir_fuentes_por_area():
    disponibles = {f"{n}-Sheet": t for n, t in TAM.items()}
    assert fondos.elegir_fuentes(disponibles, (0.210, 0.148))[:2] == ["A4-Sheet", "A3-Sheet"]
    assert fondos.elegir_fuentes(disponibles, (1.189, 0.841))[:2] == ["A1-Sheet", "A2-Sheet"]
    assert fondos.elegir_fuentes({"raro": (0.0, 0.0)}, (0.2, 0.1)) == []
    assert fondos.nombre_de_tamano("A4-Sheet") == "A4"
