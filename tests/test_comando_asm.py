"""`se asm tree` sobre el COM falso."""

import pytest
from com_falso import ColeccionFalsa, OcurrenciaFalsa


def _ensamble(app, ocurrencias, nombre="Conj.asm", tipo=3):
    doc = app.agregar_documento(nombre, ruta=f"C:\\p\\{nombre}", tipo=tipo)
    doc.Occurrences = ColeccionFalsa(ocurrencias)
    return doc


def _tornillo(n):
    return OcurrenciaFalsa(f"tornillo.par:{n}", "C:\\p\\tornillo.par")


@pytest.fixture
def anidado(app_falsa):
    """Conj.asm: 2 x Sub.asm (cada uno con 1 base y 3 tornillos), 1 tornillo suelto, 1 oculta."""

    def sub(n):
        return OcurrenciaFalsa(
            f"Sub.asm:{n}",
            "C:\\p\\Sub.asm",
            hijos=[
                OcurrenciaFalsa("base.par:1", "C:\\p\\base.par"),
                _tornillo(1),
                _tornillo(2),
                _tornillo(3),
            ],
        )

    _ensamble(
        app_falsa,
        [
            sub(1),
            sub(2),
            _tornillo(9),
            OcurrenciaFalsa("tapa.par:1", "C:\\p\\tapa.par", visible=False),
        ],
    )
    return app_falsa


def test_tree_anidado_camino_feliz(cli, anidado):
    r, sobre = cli("asm", "tree")

    assert r.exit_code == 0
    assert sobre["ok"] is True
    data = sobre["data"]
    assert data["documento"] == "Conj.asm" and data["profundidad"] == 10
    sub, tornillo, tapa = data["arbol"]
    assert sub == {
        "nombre": "Sub.asm:1",
        "archivo": "C:\\p\\Sub.asm",
        "cantidad": 2,
        "visible": True,
        "ensamble": True,
        "indice": 1,
        "indices": [1, 2],
        "hijos": [
            {
                "nombre": "base.par:1",
                "archivo": "C:\\p\\base.par",
                "cantidad": 1,
                "visible": True,
                "ensamble": False,
                "hijos": [],
            },
            {
                "nombre": "tornillo.par:1",
                "archivo": "C:\\p\\tornillo.par",
                "cantidad": 3,
                "visible": True,
                "ensamble": False,
                "hijos": [],
            },
        ],
    }
    assert tornillo["cantidad"] == 1 and tornillo["hijos"] == []
    assert tapa["visible"] is False
    assert anidado.escrituras == []


def test_tree_depth_limita_los_niveles(cli, anidado):
    r, sobre = cli("asm", "tree", "--depth", "1")

    assert r.exit_code == 0
    sub = sobre["data"]["arbol"][0]
    assert sub["hijos"] == [] and sub["truncado"] is True
    assert "truncado" not in sobre["data"]["arbol"][1]

    _, sobre = cli("asm", "tree", "--depth", "2")
    assert len(sobre["data"]["arbol"][0]["hijos"]) == 2
    assert "truncado" not in sobre["data"]["arbol"][0]


def test_tree_depth_invalida_da_exit_2(cli, anidado):
    r, sobre = cli("asm", "tree", "--depth", "0")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_tree_flat_agrega_cantidades_por_archivo(cli, anidado):
    r, sobre = cli("asm", "tree", "--flat")

    assert r.exit_code == 0
    data = sobre["data"]
    assert data["documento"] == "Conj.asm"
    por_archivo = {m["archivo"]: m for m in data["materiales"]}
    assert por_archivo["C:\\p\\Sub.asm"] == {
        "archivo": "C:\\p\\Sub.asm",
        "cantidad": 2,
        "ensamble": True,
    }
    assert por_archivo["C:\\p\\base.par"]["cantidad"] == 2  # 1 por sub x 2 subs
    assert por_archivo["C:\\p\\tornillo.par"]["cantidad"] == 7  # 3 x 2 + 1 suelto
    assert por_archivo["C:\\p\\tapa.par"]["cantidad"] == 1
    assert data["cantidad"] == 4


def test_tree_corta_ciclos(cli, app_falsa):
    a = OcurrenciaFalsa("A.asm:1", "C:\\p\\A.asm", hijos=[_tornillo(1)])
    # A contiene a B, que vuelve a contener a A.
    b = OcurrenciaFalsa("B.asm:1", "C:\\p\\B.asm", hijos=[a])
    a.SubOccurrences.elementos.append(b)
    _ensamble(app_falsa, [a])

    r, sobre = cli("asm", "tree")

    assert r.exit_code == 0
    nodo_a = sobre["data"]["arbol"][0]
    nodo_b = next(h for h in nodo_a["hijos"] if h["nombre"] == "B.asm:1")
    nodo_a2 = nodo_b["hijos"][0]
    assert nodo_a2["ciclo"] is True and nodo_a2["hijos"] == []


def test_tree_con_el_propio_ensamble_como_ocurrencia_no_se_cuelga(cli, app_falsa):
    yo = OcurrenciaFalsa("Conj.asm:1", "C:\\p\\Conj.asm", hijos=[_tornillo(1)])
    _ensamble(app_falsa, [yo])
    r, sobre = cli("asm", "tree")
    assert r.exit_code == 0 and sobre["data"]["arbol"][0]["ciclo"] is True


def test_tree_hijos_por_el_documento_de_la_ocurrencia(cli, app_falsa):
    """Si `SubOccurrences` no existe, se usa `OccurrenceDocument.Occurrences`."""

    class SinSubOcurrencias:
        Name = "Sub.asm:1"
        OccurrenceFileName = "C:\\p\\Sub.asm"
        Visible = True
        Subassembly = True

        class OccurrenceDocument:
            Occurrences = ColeccionFalsa([_tornillo(1)])

    _ensamble(app_falsa, [SinSubOcurrencias()])
    r, sobre = cli("asm", "tree")
    assert r.exit_code == 0
    assert sobre["data"]["arbol"][0]["hijos"][0]["nombre"] == "tornillo.par:1"


@pytest.mark.parametrize("tipo", [1, 2, 4])
def test_documento_que_no_es_ensamble_da_exit_2(cli, app_falsa, tipo):
    app_falsa.agregar_documento("Otro", ruta="C:\\p\\Otro", tipo=tipo)
    r, sobre = cli("asm", "tree")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"


def test_tree_modo_humano_dibuja_el_arbol(cli, anidado):
    r, _ = cli("asm", "tree", como_json=False)
    assert r.exit_code == 0
    assert "Conj.asm" in r.stdout
    assert "Sub.asm:1 x2" in r.stdout and "tornillo.par:1 x3" in r.stdout
    assert "[oculto]" in r.stdout


def test_flat_modo_humano(cli, anidado):
    r, _ = cli("asm", "tree", "--flat", como_json=False)
    assert r.exit_code == 0 and "tornillo.par" in r.stdout


def test_funciona_con_readonly_y_dry_run(cli, anidado):
    assert cli("--readonly", "asm", "tree")[0].exit_code == 0
    assert cli("--dry-run", "asm", "tree")[0].exit_code == 0


def test_doc_inexistente_da_exit_5(cli, anidado):
    r, _ = cli("asm", "tree", "--doc", "NoExiste.asm")
    assert r.exit_code == 5


def test_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("asm", "tree")
    assert r.exit_code == 3 and sobre["ok"] is False
