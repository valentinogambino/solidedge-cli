"""`se asm add|ground|move|remove` sobre el COM falso."""

import math

import pytest
from com_falso import OcurrenciaFalsa, con_armado

MM = 0.001
GRADOS = math.pi / 180


@pytest.fixture
def pieza(tmp_path):
    ruta = tmp_path / "caja.par"
    ruta.write_text("x")
    return str(ruta)


@pytest.fixture
def ensamble(app_falsa, tmp_path):
    """Conj.asm vacío y armable, activo."""
    doc = app_falsa.agregar_documento("Conj.asm", ruta=str(tmp_path / "Conj.asm"), tipo=3)
    return con_armado(doc)


@pytest.fixture
def con_dos(ensamble, pieza):
    """Conj.asm con caja.par:1 (en el origen) y caja.par:2 (en 100 mm, girada 90 grados en Z)."""
    primera = OcurrenciaFalsa("caja.par:1", pieza)
    segunda = OcurrenciaFalsa("caja.par:2", pieza)
    segunda.pose = [0.1, 0.0, 0.0, 0.0, 0.0, math.pi / 2]
    con_armado(ensamble, [primera, segunda])
    ensamble.registro.clear()
    return ensamble


def _escrituras(doc):
    return [llamada for llamada in doc.registro if llamada[0] != "Documents.Add"]


# --- add --------------------------------------------------------------------------------------


def test_add_en_el_origen(cli, ensamble, pieza, app_falsa):
    r, sobre = cli("asm", "add", pieza)

    assert r.exit_code == 0, sobre
    assert sobre["data"] == {
        "indice": 1,
        "nombre": "caja.par:1",
        "archivo": pieza,
        "visible": True,
        "ensamble": False,
        "fija": True,
        "posicion": [0.0, 0.0, 0.0],
        "rotacion": [0.0, 0.0, 0.0],
        "unidades": {"longitud": "m", "angulo": "rad"},
    }
    assert [e[0] for e in app_falsa.escrituras] == ["Occurrences.AddByFilename"]


def test_add_con_posicion_y_rotacion(cli, ensamble, pieza, app_falsa):
    cli("asm", "add", pieza)
    r, sobre = cli("asm", "add", pieza, "--at", "10mm,0,5mm", "--rot", "0,0,90deg")

    assert r.exit_code == 0, sobre
    data = sobre["data"]
    assert data["indice"] == 2 and data["nombre"] == "caja.par:2"
    assert data["posicion"] == pytest.approx([0.01, 0.0, 0.005])
    assert data["rotacion"] == pytest.approx([0.0, 0.0, math.pi / 2])
    alta = [e for e in app_falsa.escrituras if e[0] == "Occurrences.AddWithTransform"][0]
    assert alta[2:5] == pytest.approx((0.01, 0.0, 0.005))
    assert alta[5:] == pytest.approx((0.0, 0.0, math.pi / 2))


def test_add_solo_posicion_sin_unidad_son_metros(cli, ensamble, pieza):
    r, sobre = cli("asm", "add", pieza, "--at", "0.5,0,0")
    assert r.exit_code == 0 and sobre["data"]["posicion"] == [0.5, 0.0, 0.0]


def test_add_units_para_mostrar(cli, ensamble, pieza):
    r, sobre = cli(
        "asm", "add", pieza, "--at", "10mm,0,5mm", "--rot", "0,0,90deg", "--units", "mm,deg"
    )

    assert r.exit_code == 0
    assert sobre["data"]["posicion"] == pytest.approx([10.0, 0.0, 5.0])
    assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, 90.0])
    assert sobre["data"]["unidades"] == {"longitud": "mm", "angulo": "deg"}


def test_add_por_doc(cli, ensamble, pieza, app_falsa):
    app_falsa.agregar_documento("Otra.par", tipo=1)  # el activo ya no es el ensamble
    r, sobre = cli("asm", "add", pieza, "--doc", "Conj.asm")
    assert r.exit_code == 0 and sobre["data"]["indice"] == 1


def test_add_archivo_inexistente_es_5(cli, ensamble, tmp_path, app_falsa):
    r, sobre = cli("asm", "add", str(tmp_path / "nada.par"))

    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert app_falsa.escrituras == []


def test_add_extension_no_soportada_es_2(cli, ensamble, tmp_path, app_falsa):
    ruta = tmp_path / "plano.dft"
    ruta.write_text("x")
    r, sobre = cli("asm", "add", str(ruta))

    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_add_no_ensamble_es_2(cli, app_falsa, pieza):
    app_falsa.agregar_documento("Pieza.par", tipo=1)
    r, sobre = cli("asm", "add", pieza)

    assert r.exit_code == 2 and sobre["error"]["details"]["tipo"] == "part"
    assert app_falsa.escrituras == []


def test_add_un_ensamble_dentro_de_si_mismo_es_2(cli, ensamble, tmp_path, app_falsa):
    # El ensamble activo y el archivo a insertar son el mismo.
    (tmp_path / "Conj.asm").write_text("x")
    r, sobre = cli("asm", "add", str(tmp_path / "Conj.asm"))

    assert r.exit_code == 2 and "sí mismo" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


@pytest.mark.parametrize(
    ("opcion", "valor"),
    [
        ("--at", "1mm,2mm"),
        ("--at", "1mm,2mm,3mm,4mm"),
        ("--at", "1mm,,3mm"),
        ("--at", "45deg,0,0"),
        ("--at", "1,5mm,0,0"),
        ("--at", "abc,0,0"),
        ("--at", "nan,0,0"),
        ("--rot", "0,0"),
        ("--rot", "0,0,10mm"),
    ],
)
def test_add_ternas_invalidas_son_2(cli, ensamble, pieza, app_falsa, opcion, valor):
    r, sobre = cli("asm", "add", pieza, opcion, valor)

    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_add_que_solid_edge_no_agrega_es_4(cli, ensamble, pieza):
    ensamble.Occurrences.ignora_alta = True
    r, sobre = cli("asm", "add", pieza)

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_add_readonly_bloquea(cli, ensamble, pieza, app_falsa):
    r, sobre = cli.con("--readonly", "asm", "add", pieza)

    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.escrituras == []


def test_add_dry_run_informa_el_plan(cli, ensamble, pieza, app_falsa):
    r, sobre = cli.con("--dry-run", "asm", "add", pieza, "--at", "10mm,0,0")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "asm.add",
        "archivo": pieza,
        "posicion_si": pytest.approx([0.01, 0.0, 0.0]),
        "rotacion_si": [0.0, 0.0, 0.0],
    }
    assert app_falsa.escrituras == []


def test_add_dry_run_valida_el_archivo(cli, ensamble, tmp_path):
    r, _ = cli.con("--dry-run", "asm", "add", str(tmp_path / "nada.par"))
    assert r.exit_code == 5


# --- ground -----------------------------------------------------------------------------------


def test_ground_ya_fija_no_escribe(cli, con_dos, app_falsa):
    r, sobre = cli("asm", "ground", "2")

    assert r.exit_code == 0, sobre
    assert sobre["data"]["fija"] is True and sobre["data"]["changed"] is False
    assert sobre["data"]["indice"] == 2 and sobre["data"]["nombre"] == "caja.par:2"
    assert app_falsa.escrituras == []


def test_release_y_ground_de_nuevo(cli, con_dos, app_falsa):
    r, sobre = cli("asm", "ground", "caja.par:2", "--release")
    assert r.exit_code == 0 and sobre["data"]["fija"] is False and sobre["data"]["changed"] is True
    assert [e[0] for e in app_falsa.escrituras] == ["Relation3d.Delete"]

    r, sobre = cli("asm", "ground", "caja.par:2", "--release")
    assert r.exit_code == 0 and sobre["data"]["changed"] is False

    r, sobre = cli("asm", "ground", "2")
    assert r.exit_code == 0 and sobre["data"]["fija"] is True and sobre["data"]["changed"] is True
    assert [e[0] for e in app_falsa.escrituras][-1] == "Relations3d.AddGround"


def test_ground_por_nombre_sin_distinguir_mayusculas(cli, con_dos):
    r, sobre = cli("asm", "ground", "CAJA.PAR:1")
    assert r.exit_code == 0 and sobre["data"]["indice"] == 1


def test_ground_incluye_pose_en_units(cli, con_dos):
    r, sobre = cli("asm", "ground", "2", "--units", "mm,deg")

    assert sobre["data"]["posicion"] == pytest.approx([100.0, 0.0, 0.0])
    assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, 90.0])


@pytest.mark.parametrize("selector", ["9", "0", "tornillo.par:1"])
def test_ground_no_encontrada_es_5(cli, con_dos, selector):
    r, sobre = cli("asm", "ground", selector)
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"


def test_ground_que_solid_edge_no_aplica_es_4(cli, con_dos):
    cli("asm", "ground", "2", "--release")
    con_dos.Relations3d.ignora_escritura = True
    r, sobre = cli("asm", "ground", "2")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_release_que_solid_edge_no_aplica_es_4(cli, con_dos):
    con_dos.Relations3d.ignora_borrado = True
    r, sobre = cli("asm", "ground", "2", "--release")
    assert r.exit_code == 4


def test_ground_no_ensamble_es_2(cli, app_falsa):
    app_falsa.agregar_documento("Pieza.par", tipo=1)
    r, _ = cli("asm", "ground", "1")
    assert r.exit_code == 2


def test_ground_readonly_y_dry_run(cli, con_dos, app_falsa):
    r, sobre = cli.con("--readonly", "asm", "ground", "2")
    assert r.exit_code == 6

    r, sobre = cli.con("--dry-run", "asm", "ground", "2", "--release")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "asm.ground",
        "ocurrencia": "2",
        "fija": False,
    }
    assert app_falsa.escrituras == []


# --- move -------------------------------------------------------------------------------------


def test_move_by_usa_move_y_no_toca_los_angulos(cli, con_dos, app_falsa):
    r, sobre = cli("asm", "move", "2", "--by", "5mm,-10mm,0")

    assert r.exit_code == 0, sobre
    assert sobre["data"]["posicion"] == pytest.approx([0.105, -0.01, 0.0])
    assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, math.pi / 2])
    assert [e[0] for e in app_falsa.escrituras] == ["Occurrence.Move"]
    assert app_falsa.escrituras[0][2:] == pytest.approx((0.005, -0.01, 0.0))


def test_move_at_es_absoluto_y_conserva_los_angulos(cli, con_dos, app_falsa):
    r, sobre = cli("asm", "move", "caja.par:2", "--at", "10mm,20mm,30mm", "--units", "mm,deg")

    assert r.exit_code == 0, sobre
    assert sobre["data"]["posicion"] == pytest.approx([10.0, 20.0, 30.0])
    assert sobre["data"]["rotacion"] == pytest.approx([0.0, 0.0, 90.0])
    assert [e[0] for e in app_falsa.escrituras] == ["Occurrence.PutTransform"]


def test_move_rot_conserva_la_posicion(cli, con_dos):
    r, sobre = cli("asm", "move", "2", "--rot", "90deg,0,0", "--units", "mm,deg")

    assert r.exit_code == 0, sobre
    assert sobre["data"]["posicion"] == pytest.approx([100.0, 0.0, 0.0])
    assert sobre["data"]["rotacion"] == pytest.approx([90.0, 0.0, 0.0])


def test_move_by_con_rot(cli, con_dos, app_falsa):
    r, sobre = cli("asm", "move", "2", "--by", "0,0,5mm", "--rot", "0,0,0")

    assert r.exit_code == 0, sobre
    assert sobre["data"]["posicion"] == pytest.approx([0.1, 0.0, 0.005])
    assert sobre["data"]["rotacion"] == [0.0, 0.0, 0.0]
    assert [e[0] for e in app_falsa.escrituras] == ["Occurrence.PutTransform"]


def test_move_con_ocurrencia_fija_se_informa_igual(cli, con_dos):
    r, sobre = cli("asm", "move", "1", "--by", "1mm,0,0")
    assert r.exit_code == 0 and sobre["data"]["fija"] is True


@pytest.mark.parametrize(
    "argumentos",
    [
        [],
        ["--at", "0,0,0", "--by", "1mm,0,0"],
        ["--by", "1mm,0"],
        ["--by", "90deg,0,0"],
        ["--rot", "1mm,0,0"],
    ],
)
def test_move_argumentos_invalidos_son_2(cli, con_dos, app_falsa, argumentos):
    r, sobre = cli("asm", "move", "2", *argumentos)

    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_move_no_encontrada_es_5(cli, con_dos):
    r, _ = cli("asm", "move", "7", "--by", "1mm,0,0")
    assert r.exit_code == 5


def test_move_que_solid_edge_no_aplica_es_4(cli, con_dos):
    con_dos.Occurrences.elementos[1].ignora_escritura = True
    r, sobre = cli("asm", "move", "2", "--by", "1mm,0,0")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_move_no_ensamble_es_2(cli, app_falsa):
    app_falsa.agregar_documento("Pieza.par", tipo=1)
    r, _ = cli("asm", "move", "1", "--by", "1mm,0,0")
    assert r.exit_code == 2


def test_move_readonly_y_dry_run(cli, con_dos, app_falsa):
    r, _ = cli.con("--readonly", "asm", "move", "2", "--by", "1mm,0,0")
    assert r.exit_code == 6

    r, sobre = cli.con("--dry-run", "asm", "move", "2", "--by", "1mm,0,0", "--rot", "0,0,90deg")
    assert r.exit_code == 0
    assert sobre["data"]["dry_run"] is True and sobre["data"]["accion"] == "asm.move"
    assert sobre["data"]["desplazamiento_si"] == pytest.approx([0.001, 0.0, 0.0])
    assert sobre["data"]["rotacion_si"] == pytest.approx([0.0, 0.0, 90 * GRADOS])
    assert app_falsa.escrituras == []


# --- remove -----------------------------------------------------------------------------------


def test_remove_por_indice(cli, con_dos, pieza, app_falsa):
    r, sobre = cli("asm", "remove", "1")

    assert r.exit_code == 0, sobre
    assert sobre["data"] == {
        "indice": 1,
        "nombre": "caja.par:1",
        "archivo": pieza,
        "removed": True,
        "restantes": 1,
    }
    assert [e[0] for e in app_falsa.escrituras] == ["Occurrence.Delete"]
    assert [o.Name for o in con_dos.Occurrences.elementos] == ["caja.par:2"]
    assert len(con_dos.Relations3d.elementos) == 1


def test_remove_por_nombre_sin_distinguir_mayusculas(cli, con_dos):
    r, sobre = cli("asm", "remove", "CAJA.par:2")
    assert r.exit_code == 0 and sobre["data"]["indice"] == 2 and sobre["data"]["restantes"] == 1


@pytest.mark.parametrize("selector", ["3", "nada"])
def test_remove_no_encontrada_es_5(cli, con_dos, app_falsa, selector):
    r, sobre = cli("asm", "remove", selector)

    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert app_falsa.escrituras == []


def test_remove_que_solid_edge_no_aplica_es_4(cli, con_dos):
    con_dos.Occurrences.elementos[0].ignora_escritura = True
    r, sobre = cli("asm", "remove", "1")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"


def test_remove_no_ensamble_es_2(cli, app_falsa):
    app_falsa.agregar_documento("Pieza.par", tipo=1)
    r, _ = cli("asm", "remove", "1")
    assert r.exit_code == 2


def test_remove_readonly_y_dry_run(cli, con_dos, app_falsa):
    r, _ = cli.con("--readonly", "asm", "remove", "1")
    assert r.exit_code == 6

    r, sobre = cli.con("--dry-run", "asm", "remove", "1")
    assert r.exit_code == 0
    assert sobre["data"] == {"dry_run": True, "accion": "asm.remove", "ocurrencia": "1"}
    assert app_falsa.escrituras == []


# --- asm tree: índices ------------------------------------------------------------------------


def test_tree_informa_el_indice_de_primer_nivel(cli, con_dos, pieza):
    con_dos.Occurrences.elementos.append(OcurrenciaFalsa("otra.par:1", pieza + "2"))
    r, sobre = cli("asm", "tree")

    caja, otra = sobre["data"]["arbol"]
    assert caja["cantidad"] == 2 and caja["indice"] == 1 and caja["indices"] == [1, 2]
    assert otra["indice"] == 3 and "indices" not in otra
