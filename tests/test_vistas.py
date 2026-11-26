"""Layout, escala y nombres de vista de `draft from-part`: Python puro."""

import itertools

import pytest

from se_cli.core import vistas
from se_cli.core.errors import ArgumentoInvalido

TODAS = ["front", "top", "right", "iso", "left", "bottom"]


def _rectangulos(hoja, nombres):
    distribucion = vistas.distribuir(hoja, nombres)
    ancho, alto = distribucion.celda
    return [
        (p.nombre, p.x - ancho / 2, p.y - alto / 2, p.x + ancho / 2, p.y + alto / 2)
        for p in distribucion.posiciones
    ]


@pytest.mark.parametrize("hoja", ["A4", "A3"])
@pytest.mark.parametrize("cantidad", [1, 2, 3, 4, 5, 6])
def test_las_celdas_no_se_superponen_y_caben_en_la_hoja(hoja, cantidad):
    tamano = vistas.HOJAS[hoja]
    rects = _rectangulos(tamano, TODAS[:cantidad])

    assert len(rects) == cantidad
    for _, x0, y0, x1, y1 in rects:
        assert x0 >= -1e-9 and y0 >= -1e-9
        assert x1 <= tamano[0] + 1e-9 and y1 <= tamano[1] + 1e-9
    for (_, ax0, ay0, ax1, ay1), (_, bx0, by0, bx1, by1) in itertools.combinations(rects, 2):
        separadas = ax1 <= bx0 + 1e-9 or bx1 <= ax0 + 1e-9 or ay1 <= by0 + 1e-9 or by1 <= ay0 + 1e-9
        assert separadas


def test_posiciones_en_el_orden_pedido_y_proyeccion_de_tercer_angulo():
    d = vistas.distribuir(vistas.HOJAS["A3"], ["iso", "front", "right", "top"])
    por_nombre = {p.nombre: p for p in d.posiciones}

    assert [p.nombre for p in d.posiciones] == ["iso", "front", "right", "top"]
    assert por_nombre["top"].y > por_nombre["front"].y
    assert por_nombre["top"].x == pytest.approx(por_nombre["front"].x)
    assert por_nombre["right"].x > por_nombre["front"].x
    assert por_nombre["right"].y == pytest.approx(por_nombre["front"].y)
    assert (
        por_nombre["iso"].x > por_nombre["front"].x and por_nombre["iso"].y > por_nombre["front"].y
    )


def test_una_vista_va_al_centro_de_la_zona_util():
    (p,) = vistas.distribuir(vistas.HOJAS["A4"], ["front"]).posiciones
    assert p.x == pytest.approx(0.297 / 2)
    assert vistas.area_util(vistas.HOJAS["A4"])[1] < p.y < 0.210


def test_vistas_sin_celda_preferida_ocupan_las_libres():
    d = vistas.distribuir(vistas.HOJAS["A4"], ["left", "right"])
    assert len({(p.x, p.y) for p in d.posiciones}) == 2


def test_vistas_por_defecto_y_validacion():
    assert vistas.parsear_vistas(None) == ["front", "top", "right", "iso"]
    assert vistas.parsear_vistas(" Front , isometric") == ["front", "iso"]
    for malo in ("frente", "front,front", " , ", "front,top,right,left,bottom,back,iso"):
        with pytest.raises(ArgumentoInvalido):
            vistas.parsear_vistas(malo)


def test_orientaciones_coinciden_con_viewOrientationConstants():
    assert vistas.orientacion_de("front") == 4
    assert vistas.orientacion_de("top") == 1
    assert vistas.orientacion_de("right") == 2
    assert vistas.orientacion_de("iso") == 9
    assert {vistas.orientacion_de(n) for n in vistas.ORIENTACIONES} == {4, 1, 2, 3, 5, 6, 9}


def test_hojas():
    assert vistas.parsear_hoja(None) is None
    assert vistas.parsear_hoja("a3") == "A3"
    with pytest.raises(ArgumentoInvalido):
        vistas.parsear_hoja("B7")


@pytest.mark.parametrize(
    ("texto", "factor"),
    [("1:2", 0.5), ("0.5", 0.5), ("2:1", 2.0), ("1:1", 1.0), (" 1 : 10 ", 0.1), ("2", 2.0)],
)
def test_parseo_de_escala(texto, factor):
    assert vistas.parsear_escala(texto) == pytest.approx(factor)


def test_escala_auto_devuelve_none():
    assert vistas.parsear_escala("AUTO") is None


@pytest.mark.parametrize(
    "texto", ["", "abc", "1:0", "0", "-1", "-1:2", "1:2:3", "nan", "inf", "1:"]
)
def test_escalas_invalidas(texto):
    with pytest.raises(ArgumentoInvalido):
        vistas.parsear_escala(texto)


@pytest.mark.parametrize(
    ("factor", "texto"), [(1.0, "1:1"), (0.5, "1:2"), (2.0, "2:1"), (0.1, "1:10"), (0.3, "0.3")]
)
def test_nombre_de_escala(factor, texto):
    assert vistas.nombre_de_escala(factor) == texto


def test_escala_auto_con_caja_elige_la_normalizada_mas_grande_que_entra():
    celda = vistas.distribuir(vistas.HOJAS["A3"], ["front", "top", "right", "iso"]).celda
    chica = vistas.elegir_escala((0.005, 0.005, 0.005), celda, ["front", "top", "right", "iso"])
    assert chica == (5.0, True)
    # La serie ISO 5455 sigue más allá de 5:1 para piezas muy chicas.
    muy_chica = vistas.elegir_escala((0.002, 0.002, 0.002), celda, ["front", "top", "right", "iso"])
    assert muy_chica == (20.0, True)

    # Una pieza de 0.3 m no entra a 1:1 en una celda de ~0.2 m, pero sí a 1:2.
    mediana = vistas.elegir_escala((0.3, 0.3, 0.3), celda, ["front", "top", "right", "iso"])
    assert mediana[1] is True and mediana[0] < 1.0
    for _, factor in vistas.ESCALAS_NORMALIZADAS:
        if factor > mediana[0]:
            anchos = [
                vistas.extension_de_vista(v, (0.3, 0.3, 0.3))
                for v in ("front", "top", "right", "iso")
            ]
            assert any(
                w * factor > celda[0] * vistas.RELLENO or h * factor > celda[1] * vistas.RELLENO
                for w, h in anchos
            )


def test_escala_auto_con_la_caja_entrando_cumple_el_limite():
    nombres = ["front", "top"]
    celda = vistas.distribuir(vistas.HOJAS["A4"], nombres).celda
    caja = (0.1, 0.05, 0.08)
    factor, auto = vistas.elegir_escala(caja, celda, nombres)
    assert auto is True
    for nombre in nombres:
        ancho, alto = vistas.extension_de_vista(nombre, caja)
        assert ancho * factor <= celda[0] * vistas.RELLENO + 1e-12
        assert alto * factor <= celda[1] * vistas.RELLENO + 1e-12


def test_escala_auto_sin_caja_usa_1_a_1_e_informa():
    assert vistas.elegir_escala(None, (0.1, 0.1), ["front"]) == (1.0, False)


def test_escala_auto_enorme_cae_en_la_mas_chica():
    assert vistas.elegir_escala((500.0, 500.0, 500.0), (0.1, 0.1), ["front"]) == (0.001, True)


def test_la_serie_de_escalas_es_la_iso_5455_de_mayor_a_menor():
    nombres = [n for n, _ in vistas.ESCALAS_NORMALIZADAS]
    assert nombres[nombres.index("10:1") : nombres.index("1:10") + 1] == [
        "10:1",
        "5:1",
        "2:1",
        "1:1",
        "1:2",
        "1:5",
        "1:10",
    ]
    factores = [f for _, f in vistas.ESCALAS_NORMALIZADAS]
    assert factores == sorted(factores, reverse=True)
    for nombre, factor in vistas.ESCALAS_NORMALIZADAS:
        assert vistas.nombre_de_escala(factor) == nombre


@pytest.mark.parametrize(
    ("hoja", "marco", "tope"),
    [("A5", 0.010, 0.0608), ("A4", 0.010, 0.0608), ("A2", 0.010, 0.0608), ("A1", 0.020, 0.0771)],
)
def test_area_util_excluye_marco_y_toda_la_franja_del_rotulo(hoja, marco, tope):
    ancho, alto = vistas.HOJAS[hoja]
    x0, y0, x1, y1 = vistas.area_util(vistas.HOJAS[hoja])
    assert (x0, y0) == pytest.approx((marco + vistas.HOLGURA, tope + vistas.HOLGURA))
    assert (x1, y1) == pytest.approx(
        (ancho - marco - vistas.HOLGURA, alto - marco - vistas.HOLGURA)
    )


def test_hoja_desconocida_usa_las_medidas_del_tamano_mas_parecido():
    assert vistas.medidas_de_hoja((0.5, 0.4)) == vistas.MEDIDAS_DE_HOJA["A2"]
    assert vistas.medidas_de_hoja((0.9, 0.6)) == vistas.MEDIDAS_DE_HOJA["A1"]
    assert vistas.medidas_de_hoja((0.2971, 0.2099)) == vistas.MEDIDAS_DE_HOJA["A4"]


@pytest.mark.parametrize("hoja", ["A4", "A3", "A1"])
def test_vista_grande_con_escala_auto_queda_en_el_area_util_y_sobre_el_rotulo(hoja):
    caja = (0.4, 0.3, 0.2)  # prisma de 400 x 300 x 200 mm
    nombres = ["front", "top", "right", "iso"]
    distribucion = vistas.distribuir(vistas.HOJAS[hoja], nombres)
    factor, auto = vistas.elegir_escala(caja, distribucion.celda, nombres)
    assert auto is True
    x0, y0, x1, y1 = distribucion.area_util
    assert y0 >= vistas.MEDIDAS_DE_HOJA[hoja][1] + vistas.HOLGURA - 1e-12
    for posicion in distribucion.posiciones:
        ancho, alto = vistas.extension_de_vista(posicion.nombre, caja)
        assert posicion.x - ancho * factor / 2 >= x0 - 1e-9
        assert posicion.x + ancho * factor / 2 <= x1 + 1e-9
        assert posicion.y - alto * factor / 2 >= y0 - 1e-9  # no toca el rótulo
        assert posicion.y + alto * factor / 2 <= y1 + 1e-9
    # Es la mayor de la serie que entra: la siguiente se pasa del área.
    mayores = [f for _, f in vistas.ESCALAS_NORMALIZADAS if f > factor]
    assert mayores and not vistas.entran(caja, distribucion.celda, nombres, mayores[-1], 0.85)


def test_entran_distingue_la_celda_completa_del_relleno():
    celda = (0.1, 0.1)
    assert vistas.entran((0.095, 0.095, 0.0), celda, ["front"], 1.0)
    assert not vistas.entran((0.095, 0.095, 0.0), celda, ["front"], 1.0, 0.85)
