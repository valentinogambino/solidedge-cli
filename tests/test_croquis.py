"""Validación del perfil JSON de `se sketch profile` (esquema v1), sin COM."""

import copy
import math

import pytest

from se_cli.core import croquis
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado


def estadio() -> dict:
    """Ranura de 50 x 20 mm: dos líneas y dos arcos (uno ccw y otro cw), con tangencias."""
    return {
        "version": 1,
        "plane": "top",
        "units": "mm",
        "entities": [
            {"id": "l1", "type": "line", "from": [0, 0], "to": [50, 0]},
            {"id": "a1", "type": "arc", "center": [50, 10], "start": [50, 0], "end": [50, 20]},
            {"id": "l2", "type": "line", "from": [50, 20], "to": [0, 20]},
            {"id": "a2", "type": "arc", "center": [0, 10], "start": [0, 0], "end": [0, 20],
             "dir": "cw"},
        ],
        "constraints": [
            {"type": "horizontal", "on": "l1"},
            {"type": "tangent", "a": "l1", "b": "a1"},
            {"type": "tangent", "a": "a2", "b": "l2"},
            {"type": "equal", "a": "a1", "b": "a2"},
        ],
    }  # fmt: skip


def con(**cambios) -> dict:
    datos = estadio()
    datos.update(cambios)
    return datos


def invalido(datos: dict, texto: str) -> ArgumentoInvalido:
    with pytest.raises(ArgumentoInvalido, match=texto) as info:
        croquis.validar_perfil(datos)
    return info.value


# --- camino feliz -----------------------------------------------------------------------------


def test_estadio_valido_en_si_con_uniones_automaticas():
    perfil = croquis.validar_perfil(estadio())

    assert perfil.plano == "top" and perfil.plano_indice == 1
    assert perfil.tolerancia_si == croquis.TOLERANCIA_POR_DEFECTO
    assert perfil.conteos() == {"lineas": 2, "arcos": 2, "circulos": 0}
    l1, a1 = perfil.entidades[0], perfil.entidades[1]
    assert l1["hasta"] == (0.05, 0.0)
    assert a1["centro"] == (0.05, 0.01) and a1["radio"] == pytest.approx(0.01)
    assert a1["dir"] == "ccw" and perfil.entidades[3]["dir"] == "cw"
    por_tipo = perfil.por_tipo_de_restriccion()
    assert por_tipo == {"connect": 4, "horizontal": 1, "tangent": 2, "equal": 1}
    # las uniones van primero y todas son automáticas
    assert [r["tipo"] for r in perfil.restricciones[:4]] == ["connect"] * 4
    assert all(r["auto"] for r in perfil.restricciones[:4])


def test_auto_connect_false_no_genera_uniones_pero_valida_el_cierre():
    perfil = croquis.validar_perfil(con(auto_connect=False))
    assert "connect" not in perfil.por_tipo_de_restriccion()
    datos = con(auto_connect=False, constraints=[])
    datos["entities"][0]["to"] = [49, 0]
    invalido(datos, "no está cerrado")


def test_connect_explicito_no_se_duplica_con_la_automatica():
    datos = con(constraints=[{"type": "connect", "a": "a1.start", "b": "l1.end"}])
    perfil = croquis.validar_perfil(datos)
    assert perfil.por_tipo_de_restriccion()["connect"] == 4
    explicitas = [r for r in perfil.restricciones if r["tipo"] == "connect" and not r["auto"]]
    assert len(explicitas) == 1


def test_numeros_y_strings_con_unidad_dan_lo_mismo():
    datos = con(units="in", constraints=[])
    datos["entities"] = [{"id": "c", "type": "circle", "center": ["25.4mm", 0], "radius": 1}]
    circulo = croquis.validar_perfil(datos).entidades[0]
    assert circulo["centro"] == (pytest.approx(0.0254), 0.0)
    assert circulo["radio"] == pytest.approx(0.0254)


def test_polilinea_se_expande_a_segmentos_y_el_circulo_es_su_propio_lazo():
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "p1", "type": "polyline", "points": [[0, 0], [40, 0], [40, 20], [0, 0]]},
            {"id": "c1", "type": "circle", "center": [30, 5], "radius": 2},
        ],
        "constraints": [{"type": "horizontal", "on": "p1.1"}, {"type": "vertical", "on": "p1.2"}],
    }
    perfil = croquis.validar_perfil(datos)
    assert [e["id"] for e in perfil.entidades] == ["p1.1", "p1.2", "p1.3", "c1"]
    assert perfil.entidades[0]["origen"] == "p1"
    assert perfil.por_tipo_de_restriccion() == {"connect": 3, "horizontal": 1, "vertical": 1}


def test_tolerancia_con_unidad_y_plano_por_indice():
    perfil = croquis.validar_perfil(con(tolerance="0.5mm", plane="3"))
    assert perfil.tolerancia_si == pytest.approx(0.0005) and perfil.plano_indice == 3


def test_caja_de_incluye_los_extremos_de_los_arcos_en_ambos_sentidos():
    caja = croquis.caja_de(croquis.validar_perfil(estadio()))
    assert caja == pytest.approx({"x_min": -0.01, "y_min": 0.0, "x_max": 0.06, "y_max": 0.02})
    # el cw sin extremos hacia afuera: semicírculo derecho recorrido al revés
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "a", "type": "arc", "center": [0, 0], "start": [0, 10], "end": [0, -10],
             "dir": "cw"},
            {"id": "l", "type": "line", "from": [0, -10], "to": [0, 10]},
        ],
    }  # fmt: skip
    caja = croquis.caja_de(croquis.validar_perfil(datos))
    assert caja["x_max"] == pytest.approx(0.01) and caja["x_min"] == pytest.approx(0.0)


def test_el_plan_esta_en_si_y_es_serializable():
    import json

    plan = croquis.validar_perfil(estadio()).plan()
    json.dumps(plan)
    assert plan["conteos"] == {"lineas": 2, "arcos": 2, "circulos": 0, "restricciones": 8}
    assert plan["entidades"][0]["hasta"] == [0.05, 0.0]
    assert plan["restricciones"][0]["origen"] == "auto"


# --- errores de forma -------------------------------------------------------------------------


def test_json_invalido_y_raiz_que_no_es_objeto():
    with pytest.raises(ArgumentoInvalido, match="JSON inválido"):
        croquis.parsear_json("{ nope")
    with pytest.raises(ArgumentoInvalido, match="objeto JSON"):
        croquis.parsear_json("[1, 2]")
    with pytest.raises(ArgumentoInvalido, match="repetida"):
        croquis.parsear_json('{"version": 1, "version": 1}')


def test_archivo_inexistente_es_exit_5(tmp_path):
    with pytest.raises(DocNoEncontrado):
        croquis.leer_fuente(str(tmp_path / "no.json"))
    with pytest.raises(ArgumentoInvalido, match="no es un archivo"):
        croquis.leer_fuente(str(tmp_path))


def test_lee_utf8_con_bom(tmp_path):
    ruta = tmp_path / "p.json"
    ruta.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')
    assert croquis.parsear_json(croquis.leer_fuente(str(ruta))) == {"a": 1}


@pytest.mark.parametrize(
    ("cambios", "texto"),
    [
        ({"version": 2}, "version"),
        ({"version": True}, "version"),
        ({"extra": 1}, "campos desconocidos extra"),
        ({"close": False}, "abiertos"),
        ({"close": "si"}, "true o false"),
        ({"auto_connect": 1}, "true o false"),
        ({"units": "furlong"}, "units"),
        ({"units": "deg"}, "units"),
        ({"tolerance": 0}, "mayor que 0"),
        ({"tolerance": "5kg"}, "no es una longitud"),
        ({"plane": "lateral"}, "Plano inválido"),
        ({"plane": 1}, "plane"),
        ({"entities": []}, "al menos una"),
        ({"entities": "x"}, "al menos una"),
        ({"constraints": {}}, "lista"),
    ],
)
def test_raiz_invalida(cambios, texto):
    invalido(con(**cambios), texto)


def test_falta_version_o_entities():
    datos = estadio()
    del datos["version"]
    invalido(datos, "version")
    datos = estadio()
    del datos["entities"]
    invalido(datos, "al menos una")


def test_numero_sin_units_pide_units_y_con_todo_en_strings_no():
    datos = estadio()
    del datos["units"]
    invalido(datos, "falta `units`")
    todo = {
        "version": 1,
        "entities": [{"id": "c", "type": "circle", "center": ["0mm", "0mm"], "radius": "2mm"}],
    }
    assert croquis.validar_perfil(todo).entidades[0]["radio"] == pytest.approx(0.002)


@pytest.mark.parametrize(
    ("dato", "texto"),
    [
        ("50", "necesita una unidad"),
        ("", "necesita una unidad"),
        ("50 kg", "no es una longitud"),
        ("1,5mm", "punto"),
        ("abc", "inválido"),
        (True, "número"),
        (None, "número"),
        ([1], "número"),
        (float("nan"), "finito"),
    ],
)
def test_coordenada_invalida(dato, texto):
    datos = estadio()
    datos["entities"][0]["to"] = [dato, 0]
    invalido(datos, texto)


def test_punto_mal_formado():
    for punto in ([1], [1, 2, 3], "1,2", {"x": 1}):
        datos = estadio()
        datos["entities"][0]["from"] = punto
        invalido(datos, "punto")


# --- errores de entidades ---------------------------------------------------------------------


def test_entidad_invalida():
    datos = estadio()
    datos["entities"][0]["type"] = "spline"
    invalido(datos, "tipo desconocido 'spline'")
    datos = estadio()
    datos["entities"][0]["color"] = "red"
    invalido(datos, "campos desconocidos color")
    datos = estadio()
    del datos["entities"][0]["to"]
    invalido(datos, "faltan los campos to")
    datos = estadio()
    datos["entities"][0] = "l1"
    invalido(datos, "objeto")
    datos = estadio()
    del datos["entities"][0]["id"]
    invalido(datos, "faltan los campos id")


@pytest.mark.parametrize("ident", ["", "  ", "a.b", " l1", 3, None])
def test_id_invalido(ident):
    datos = estadio()
    datos["entities"][0]["id"] = ident
    invalido(datos, "id")


def test_id_duplicado():
    datos = estadio()
    datos["entities"][1]["id"] = "l1"
    invalido(datos, "repetido")


def test_linea_de_largo_cero_y_polilinea_corta():
    datos = estadio()
    datos["entities"][0]["to"] = [0, 0]
    invalido(datos, "largo cero")
    datos = estadio()
    datos["entities"][0] = {"id": "p", "type": "polyline", "points": [[0, 0]]}
    invalido(datos, "al menos 2")
    datos["entities"][0]["points"] = [[0, 0], [0, 0]]
    invalido(datos, "largo cero")


def test_arco_con_radios_distintos_radio_cero_o_sin_barrido():
    datos = estadio()
    datos["entities"][1]["end"] = [50, 21]
    err = invalido(datos, "radios distintos")
    assert err.details["radio_start_si"] == pytest.approx(0.01)
    datos = estadio()
    datos["entities"][1]["start"] = [50, 10]
    invalido(datos, "radio cero")
    datos = estadio()
    datos["entities"][1]["end"] = [50, 0]
    invalido(datos, "circle")
    datos = estadio()
    datos["entities"][1]["dir"] = "izq"
    invalido(datos, "ccw o cw")


def test_circulo_con_radio_no_positivo():
    for radio in (0, -1):
        datos = {
            "version": 1,
            "units": "mm",
            "entities": [{"id": "c", "type": "circle", "center": [0, 0], "radius": radio}],
        }
        invalido(datos, "mayor que 0")


# --- errores de restricciones -----------------------------------------------------------------


def restriccion(**campos) -> dict:
    return con(constraints=[campos])


@pytest.mark.parametrize(
    ("campos", "texto"),
    [
        ({"type": "dimension", "on": "l1"}, "cotas"),
        ({"type": "collinear", "a": "l1", "b": "l2"}, "collinear"),
        ({"type": "symmetric", "a": "l1", "b": "l2"}, "symmetric"),
        ({"type": "fix", "on": "l1"}, "tipo desconocido"),
        ({"on": "l1"}, "tipo desconocido"),
        ({"type": "horizontal", "on": "l1", "x": 1}, "campos desconocidos x"),
        ({"type": "horizontal"}, "faltan los campos on"),
        ({"type": "horizontal", "on": "zz"}, "no existe la entidad 'zz'"),
        ({"type": "horizontal", "on": "a1"}, "no se aplica a 'a1'"),
        ({"type": "parallel", "a": "l1"}, "faltan los campos b"),
        ({"type": "parallel", "a": "l1", "b": "l1"}, "misma entidad"),
        ({"type": "parallel", "a": "l1", "b": "a1"}, "no se aplica a 'a1'"),
        ({"type": "concentric", "a": "l1", "b": "a1"}, "no se aplica a 'l1'"),
        ({"type": "equal", "a": "l1", "b": "a1"}, "no admite line con arc"),
        ({"type": "tangent", "a": "l1", "b": "l2"}, "no admite line con line"),
        ({"type": "connect", "a": "l1", "b": "a1.start"}, r"<id>\.<punto>"),
        ({"type": "connect", "a": "l1.mid", "b": "a1.start"}, "no existe"),
        ({"type": "connect", "a": "l1.center", "b": "a1.start"}, "no existe"),
        ({"type": "connect", "a": "l1.end", "b": "l1.end"}, "consigo mismo"),
        ({"type": "connect", "a": "nada.end", "b": "a1.start"}, "no existe la entidad"),
        ({"type": "connect", "a": 5, "b": "a1.start"}, "<id>"),
    ],
)
def test_restriccion_invalida(campos, texto):
    invalido(restriccion(**campos), texto)


def test_referencia_a_una_polilinea_sugiere_el_segmento():
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [{"id": "p1", "type": "polyline", "points": [[0, 0], [1, 0], [0, 0]]}],
        "constraints": [{"type": "horizontal", "on": "p1"}],
    }
    invalido(datos, "p1.1")


def test_restriccion_que_las_coordenadas_no_cumplen():
    casos = [
        ({"type": "vertical", "on": "l2"}, "se desvía"),
        ({"type": "vertical", "on": "l1"}, "se desvía"),
        ({"type": "connect", "a": "l1.start", "b": "l1.end"}, "están a"),
        ({"type": "parallel", "a": "l1", "b": "l2"}, None),  # sí las cumple
        ({"type": "perpendicular", "a": "l1", "b": "l2"}, "desvío angular"),
        ({"type": "concentric", "a": "a1", "b": "a2"}, "centros"),
        ({"type": "tangent", "a": "a1", "b": "a2"}, "centros"),
    ]
    for campos, texto in casos:
        if texto is None:
            croquis.validar_perfil(restriccion(**campos))
        else:
            err = invalido(restriccion(**campos), texto)
            assert err.details["restriccion"]["tipo"] == campos["type"]


def test_igualdad_y_tangencia_que_no_se_cumplen():
    datos = estadio()
    datos["entities"][1]["center"] = [50, 10]  # a1 queda con radio 10 y a2 con radio 10: iguales
    datos["constraints"] = [{"type": "equal", "a": "l1", "b": "l2"}]
    croquis.validar_perfil(datos)  # los dos largos son 50: se cumple
    datos["entities"][2]["to"] = [10, 20]
    invalido(datos, "largos son")
    datos = estadio()
    datos["constraints"] = [{"type": "tangent", "a": "l1", "b": "a2"}]
    croquis.validar_perfil(datos)  # l1 es tangente a a2 en (0, 0)
    datos["constraints"] = [{"type": "tangent", "a": "l2", "b": "a1"}]
    croquis.validar_perfil(datos)
    datos["entities"][0]["from"] = [0, 5]
    datos["constraints"] = [{"type": "tangent", "a": "l1", "b": "a1"}]
    invalido(datos, "radio es")


def test_tangencia_con_el_pie_fuera_del_segmento():
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "l", "type": "line", "from": [0, 0], "to": [5, 0]},
            {"id": "c", "type": "circle", "center": [20, 3], "radius": 3},
        ],
        "constraints": [{"type": "tangent", "a": "l", "b": "c"}],
    }
    invalido(datos, "fuera del segmento")


def test_tangencia_entre_curvas_interior_y_exterior():
    def con_circulos(r2, x2):
        return {
            "version": 1,
            "units": "mm",
            "entities": [
                {"id": "c1", "type": "circle", "center": [0, 0], "radius": 10},
                {"id": "c2", "type": "circle", "center": [x2, 0], "radius": r2},
            ],
            "constraints": [{"type": "tangent", "a": "c1", "b": "c2"}],
        }

    croquis.validar_perfil(con_circulos(5, 15))  # exterior
    croquis.validar_perfil(con_circulos(5, 5))  # interior
    invalido(con_circulos(5, 12), "centros")
    invalido(con_circulos(10, 0), "centros")  # concéntricos: no es tangencia


def test_paralelas_perpendiculares_y_concentricas_que_si_se_cumplen():
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "l1", "type": "line", "from": [0, 0], "to": [10, 0]},
            {"id": "l2", "type": "line", "from": [10, 0], "to": [10, 10]},
            {"id": "l3", "type": "line", "from": [10, 10], "to": [0, 10]},
            {"id": "l4", "type": "line", "from": [0, 10], "to": [0, 0]},
            {"id": "c1", "type": "circle", "center": [5, 5], "radius": 1},
            {"id": "c2", "type": "circle", "center": [5, 5], "radius": 2},
        ],
        "constraints": [
            {"type": "parallel", "a": "l1", "b": "l3"},
            {"type": "perpendicular", "a": "l1", "b": "l2"},
            {"type": "concentric", "a": "c1", "b": "c2"},
            {"type": "equal", "a": "l1", "b": "l2"},
        ],
    }
    assert croquis.validar_perfil(datos).por_tipo_de_restriccion()["parallel"] == 1
    otro = copy.deepcopy(datos)
    otro["entities"][2]["to"] = [0, 11]
    invalido(otro, "desvío angular")


def test_la_tolerancia_se_respeta():
    datos = estadio()
    datos["entities"][1]["start"] = [50, 0.0000005]  # 5e-10 m: dentro de la tolerancia
    croquis.validar_perfil(datos)
    datos["entities"][1]["start"] = [50, 0.01]  # 1e-5 m: fuera de la tolerancia por defecto
    invalido(datos, "radios distintos")
    datos["tolerance"] = "0.05mm"  # 5e-5 m: ahora entra
    croquis.validar_perfil(datos)


# --- contorno ---------------------------------------------------------------------------------


def test_contorno_abierto_y_ramificado():
    datos = con(constraints=[])
    del datos["entities"][2]
    err = invalido(datos, "no está cerrado")
    assert err.details["extremo_suelto"] in ("a1.end", "a2.end")
    datos = con(constraints=[])
    datos["entities"].append({"id": "l3", "type": "line", "from": [50, 0], "to": [60, 0]})
    err = invalido(datos, "se ramifica")
    assert "l3.start" in err.details["extremos"]


def test_perfil_de_solo_circulos_es_valido():
    datos = {
        "version": 1,
        "units": "mm",
        "entities": [
            {"id": "c1", "type": "circle", "center": [0, 0], "radius": 5},
            {"id": "c2", "type": "circle", "center": [0, 0], "radius": 3},
        ],
    }
    perfil = croquis.validar_perfil(datos)
    assert perfil.restricciones == []
    assert math.isclose(croquis.caja_de(perfil)["x_max"], 0.005)
