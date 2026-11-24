"""`se asm relate` y `se asm relations list|delete` sobre el COM falso."""

import pytest
from com_falso import (
    GEOMETRIA_CILINDRO,
    GEOMETRIA_PLANO,
    OcurrenciaFalsa,
    com_error,
    con_armado,
    pieza_con_caras,
)

MM = 0.001


@pytest.fixture
def conjunto(app_falsa, tmp_path):
    """Conj.asm: caja.par:1 y :2 (6 caras planas) y cil.par:1 y :2 (cilindro + 2 planos), fijas."""
    doc = app_falsa.agregar_documento("Conj.asm", ruta=str(tmp_path / "Conj.asm"), tipo=3)
    ocurrencias = []
    for nombre, tipos in (
        ("caja.par:1", None),
        ("caja.par:2", None),
        ("cil.par:1", [GEOMETRIA_CILINDRO, GEOMETRIA_PLANO, GEOMETRIA_PLANO]),
        ("cil.par:2", [GEOMETRIA_CILINDRO, GEOMETRIA_PLANO, GEOMETRIA_PLANO]),
    ):
        ocurrencia = OcurrenciaFalsa(nombre, str(tmp_path / nombre.split(":")[0]))
        ocurrencia.OccurrenceDocument = pieza_con_caras(nombre.split(":")[0], tipos)
        ocurrencias.append(ocurrencia)
    con_armado(doc, ocurrencias)
    doc.registro.clear()
    return doc


@pytest.fixture
def suelto(cli, conjunto):
    """El conjunto con caja.par:2 y cil.par:2 sueltas (hay que soltar una para relacionar)."""
    for ocurrencia in ("2", "4"):
        r, sobre = cli("asm", "ground", ocurrencia, "--release")
        assert r.exit_code == 0, sobre
    conjunto.registro.clear()
    return conjunto


def _escrituras(doc):
    return [e for e in doc.registro if e[0] != "Documents.Add"]


def _tipos(doc):
    return [r.Type for r in doc.Relations3d.elementos]


# --- relate: casos buenos ---------------------------------------------------------------------


def test_mate_entre_dos_caras_planas(cli, suelto):
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1")

    assert r.exit_code == 0, sobre
    data = sobre["data"]
    assert data["indice"] == 3 and data["tipo"] == "mate" and data["estado"] == "resuelta"
    assert data["a"] == {"ocurrencia": 1, "cara": 3, "tipo_de_cara": "plano"}
    assert data["b"] == {"ocurrencia": 2, "cara": 1, "tipo_de_cara": "plano"}
    assert data["offset"] == 0.0
    assert [o["nombre"] for o in data["ocurrencias"]] == ["caja.par:1", "caja.par:2"]
    assert [o["fija"] for o in data["ocurrencias"]] == [True, False]
    assert data["ocurrencias"][1]["posicion"] == [0.0, 0.0, 0.0]
    # mate = normalsAligned True
    assert _escrituras(suelto) == [
        ("Relations3d.AddPlanar", "caja.par:1", 3, "caja.par:2", 1, True)
    ]


def test_align_usa_normales_no_alineadas(cli, suelto):
    r, sobre = cli("asm", "relate", "align", "--a", "caja.par:1:2", "--b", "2:2")

    assert r.exit_code == 0 and sobre["data"]["tipo"] == "align"
    assert _escrituras(suelto)[0] == (
        "Relations3d.AddPlanar",
        "caja.par:1",
        2,
        "caja.par:2",
        2,
        False,
    )


def test_offset_se_escribe_en_metros_y_se_muestra_en_units(cli, suelto):
    r, sobre = cli(
        "asm", "relate", "align", "--a", "1:2", "--b", "2:2", "--offset", "5mm", "--units", "mm"
    )

    assert r.exit_code == 0, sobre
    assert sobre["data"]["offset"] == pytest.approx(5.0)
    assert ("Relation3d.Offset", pytest.approx(5 * MM)) in _escrituras(suelto)


def test_offset_negativo_y_sin_unidad_son_metros(cli, suelto):
    r, sobre = cli("asm", "relate", "mate", "--a", "1:1", "--b", "2:1", "--offset=-0.002")

    assert r.exit_code == 0 and sobre["data"]["offset"] == pytest.approx(-0.002)


def test_axial_entre_cilindros(cli, suelto):
    r, sobre = cli("asm", "relate", "axial", "--a", "cil.par:1:1", "--b", "4:1")

    assert r.exit_code == 0, sobre
    data = sobre["data"]
    assert data["tipo"] == "axial" and data["offset"] is None
    assert data["a"]["tipo_de_cara"] == "cilindro"
    assert _escrituras(suelto) == [("Relations3d.AddAxial", "cil.par:1", 1, "cil.par:2", 1, True)]


def test_relate_por_doc(cli, suelto, app_falsa):
    app_falsa.agregar_documento("Otra.par", tipo=1)
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1", "--doc", "Conj.asm")
    assert r.exit_code == 0, sobre


# --- relate: errores de uso -------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ("foo", "--a", "1:1", "--b", "2:1"),
        ("mate", "--a", "1", "--b", "2:1"),
        ("mate", "--a", "1:0", "--b", "2:1"),
        ("mate", "--a", "1:x", "--b", "2:1"),
        ("mate", "--a", ":3", "--b", "2:1"),
        ("mate", "--a", "1:1", "--b", "2:-1"),
        ("axial", "--a", "3:1", "--b", "4:1", "--offset", "1mm"),
        ("mate", "--a", "1:1", "--b", "2:1", "--offset", "30deg"),
        ("mate", "--a", "1:1", "--b", "2:1", "--offset", "abc"),
        ("mate", "--a", "1:1", "--b", "1:2"),  # misma ocurrencia
        ("mate", "--a", "caja.par:1:1", "--b", "1:2"),  # misma ocurrencia por nombre
        ("mate", "--a", "3:1", "--b", "2:1"),  # cilindro en mate
        ("align", "--a", "1:1", "--b", "4:1"),  # cilindro en align
        ("axial", "--a", "1:1", "--b", "3:1"),  # plano en axial
        ("axial", "--a", "3:1", "--b", "4:2"),  # plano en axial (b)
    ],
)
def test_relate_uso_invalido_es_2(cli, suelto, args):
    r, sobre = cli("asm", "relate", *args)

    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido", sobre
    assert _escrituras(suelto) == []


@pytest.mark.parametrize(
    "args",
    [
        ("mate", "--a", "9:1", "--b", "2:1"),
        ("mate", "--a", "1:1", "--b", "nada.par:7:1"),
        ("mate", "--a", "1:7", "--b", "2:1"),
        ("mate", "--a", "1:1", "--b", "2:99"),
    ],
)
def test_relate_inexistente_es_5(cli, suelto, args):
    r, sobre = cli("asm", "relate", *args)

    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado", sobre
    assert _escrituras(suelto) == []


def test_relate_no_ensamble_es_2(cli, app_falsa):
    app_falsa.agregar_documento("Pieza.par", tipo=1)
    r, sobre = cli("asm", "relate", "mate", "--a", "1:1", "--b", "2:1")

    assert r.exit_code == 2 and sobre["error"]["details"]["tipo"] == "part"


def test_relate_dry_run_no_toca_com(cli, suelto, app_falsa):
    r, sobre = cli.con("--dry-run", "asm", "relate", "align", "--a", "1:1", "--b", "2:1")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "asm.relate",
        "tipo": "align",
        "a": {"ocurrencia": "1", "cara": 1},
        "b": {"ocurrencia": "2", "cara": 1},
        "offset_si": None,
    }
    assert _escrituras(suelto) == []


def test_relate_readonly_es_6(cli, suelto):
    r, sobre = cli.con("--readonly", "asm", "relate", "mate", "--a", "1:1", "--b", "2:1")

    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert _escrituras(suelto) == []


# --- relate: Solid Edge no la deja resolver ---------------------------------------------------


def test_dos_ocurrencias_fijas_se_borra_y_pide_soltar_una(cli, conjunto):
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1")

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error", sobre
    assert "se asm ground <occ> --release" in sobre["error"]["message"]
    assert sobre["error"]["details"]["relacion_borrada"] is True
    assert len(conjunto.Relations3d.elementos) == 4  # solo las 4 ground, la nueva se borró
    assert ("Relation3d.Delete", "caja.par:1") in conjunto.registro


def test_relacion_insatisfecha_se_borra(cli, suelto):
    suelto.Relations3d.detalle_forzado = 5
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1")

    assert r.exit_code == 4 and "insatisfecha" in sobre["error"]["message"]
    assert "ground" not in sobre["error"]["message"]
    assert len(suelto.Relations3d.elementos) == 2


def test_solid_edge_rechaza_con_las_dos_fijas_da_la_pista(cli, conjunto):
    conjunto.Relations3d.rechazo = com_error(0x80040225, "Error", "Relación inválida")
    r, sobre = cli("asm", "relate", "axial", "--a", "3:1", "--b", "4:1")

    assert r.exit_code == 4 and "--release" in sobre["error"]["message"]


def test_solid_edge_rechaza_sin_pista_si_alguna_esta_suelta(cli, suelto):
    suelto.Relations3d.rechazo = com_error(0x80040225, "Error", "Relación inválida")
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1")

    assert r.exit_code == 4 and "rechazó" in sobre["error"]["message"]
    assert "--release" not in sobre["error"]["message"]


def test_no_se_creo_la_relacion_es_4(cli, suelto):
    suelto.Relations3d.ignora_escritura = True
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1")

    assert r.exit_code == 4 and sobre["error"]["details"]["antes"] == 2


def test_offset_rechazado_borra_la_relacion(cli, suelto):
    original = suelto.Relations3d._alta_de_dos

    def con_offset_roto(*args, **kwargs):
        relacion = original(*args, **kwargs)
        relacion.rechaza_offset = True
        return relacion

    suelto.Relations3d._alta_de_dos = con_offset_roto
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1", "--offset", "5mm")

    assert r.exit_code == 4 and "offset" in sobre["error"]["message"]
    assert len(suelto.Relations3d.elementos) == 2


def test_offset_que_no_se_aplica_borra_la_relacion(cli, suelto):
    suelto.Relations3d.ignora_offset = True
    r, sobre = cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1", "--offset", "5mm")

    assert r.exit_code == 4 and sobre["error"]["details"]["relacion_borrada"] is True
    assert len(suelto.Relations3d.elementos) == 2


# --- relations list / delete ------------------------------------------------------------------


def test_list_con_grounds_y_relaciones(cli, suelto):
    cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1", "--offset", "5mm")
    cli("asm", "relate", "axial", "--a", "3:1", "--b", "4:1")
    r, sobre = cli("asm", "relations", "list", "--units", "mm")

    assert r.exit_code == 0, sobre
    data = sobre["data"]
    assert data["cantidad"] == 4 and data["unidades"] == {"longitud": "mm"}
    primera, segunda, mate, axial = data["relaciones"]
    assert primera["tipo"] == "ground" and primera["ocurrencias"] == [
        {"indice": 1, "nombre": "caja.par:1"}
    ]
    assert primera["offset"] is None and primera["estado"] == "resuelta"
    assert segunda["indice"] == 2 and segunda["ocurrencias"][0]["indice"] == 3
    assert mate["tipo"] == "mate" and mate["offset"] == pytest.approx(5.0)
    assert [o["nombre"] for o in mate["ocurrencias"]] == ["caja.par:1", "caja.par:2"]
    assert axial["tipo"] == "axial" and axial["offset"] is None
    assert axial["ocurrencias"][1] == {"indice": 4, "nombre": "cil.par:2"}


def test_list_distingue_align_de_mate(cli, suelto):
    cli("asm", "relate", "align", "--a", "1:2", "--b", "2:2")
    r, sobre = cli("asm", "relations", "list")

    assert sobre["data"]["relaciones"][-1]["tipo"] == "align"


def test_list_estado_y_tipo_desconocido(cli, suelto):
    suelto.Relations3d.elementos[0].Type = 12345
    suelto.Relations3d.elementos[1].DetailedStatus = 4
    r, sobre = cli("asm", "relations", "list")

    primera, segunda = sobre["data"]["relaciones"]
    assert primera["tipo"] == "otro" and primera["tipo_codigo"] == 12345
    assert segunda["estado"] == "entre_fijas"


def test_list_no_ensamble_es_2(cli, app_falsa):
    app_falsa.agregar_documento("Pieza.par", tipo=1)
    r, sobre = cli("asm", "relations", "list")

    assert r.exit_code == 2 and sobre["error"]["details"]["tipo"] == "part"


def test_list_units_invalidas_es_2(cli, suelto):
    r, sobre = cli("asm", "relations", "list", "--units", "parsec")
    assert r.exit_code == 2


def test_delete_borra_la_relacion(cli, suelto):
    cli("asm", "relate", "mate", "--a", "1:3", "--b", "2:1")
    suelto.registro.clear()
    r, sobre = cli("asm", "relations", "delete", "3")

    assert r.exit_code == 0, sobre
    assert sobre["data"] == {
        "indice": 3,
        "tipo": "mate",
        "ocurrencias": [
            {"indice": 1, "nombre": "caja.par:1"},
            {"indice": 2, "nombre": "caja.par:2"},
        ],
        "removed": True,
        "restantes": 2,
    }
    assert _tipos(suelto) == [1959028688, 1959028688]


def test_delete_inexistente_es_5(cli, suelto):
    r, sobre = cli("asm", "relations", "delete", "7")

    assert r.exit_code == 5 and sobre["error"]["details"] == {"indice": 7, "cantidad": 2}
    assert _escrituras(suelto) == []


@pytest.mark.parametrize("indice", ["0", "x", " "])
def test_delete_indice_invalido_es_2(cli, suelto, indice):
    r, sobre = cli("asm", "relations", "delete", indice)

    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert _escrituras(suelto) == []


def test_delete_que_no_borra_es_4(cli, suelto):
    suelto.Relations3d.ignora_borrado = True
    r, sobre = cli("asm", "relations", "delete", "1")

    assert r.exit_code == 4


def test_delete_dry_run_y_readonly(cli, suelto):
    r, sobre = cli.con("--dry-run", "asm", "relations", "delete", "1")
    assert r.exit_code == 0 and sobre["data"] == {
        "dry_run": True,
        "accion": "asm.relations.delete",
        "indice": 1,
    }
    r, sobre = cli.con("--readonly", "asm", "relations", "delete", "1")
    assert r.exit_code == 6
    assert _escrituras(suelto) == []
