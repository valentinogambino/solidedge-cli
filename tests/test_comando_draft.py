"""`se draft from-part` sobre el COM falso."""

import pytest
from com_falso import ColeccionFalsa, ModeloFalso, OcurrenciaFalsa, com_error

CAJA_CHICA = ((0.0, 0.0, 0.0), (0.02, 0.015, 0.01))


def _modelo(tmp_path, nombre="Pieza.par"):
    ruta = tmp_path / nombre
    ruta.write_bytes(b"modelo")
    return ruta


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


def _vistas(app, metodo="AddPartView"):
    return _llamadas(app, f"DrawingViews.{metodo}")


def test_vistas_por_defecto_con_escala_dada(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1:2")

    assert r.exit_code == 0, r.output
    data = sobre["data"]
    draft = tmp_path / "Pieza.dft"
    assert draft.exists()
    assert data["draft"] == str(draft) and data["modelo"] == str(modelo)
    assert data["escala"] == "1:2" and "escala_auto" not in data and "pdf" not in data
    assert data["marca_de_agua"] == "sin verificar" and "marca de agua" in data["nota"]
    assert data["hoja"] == {"nombre": None, "ancho": 0.297, "alto": 0.21, "origen": "plantilla"}
    assert [v["nombre"] for v in data["vistas"]] == ["front", "top", "right", "iso"]
    assert [v["orientacion"] for v in data["vistas"]] == [
        "igFrontView",
        "igTopView",
        "igRightView",
        "igTopFrontRightView",
    ]
    llamadas = _vistas(app_falsa)
    assert [c[2] for c in llamadas] == [4, 1, 2, 9]
    assert {c[1] for c in llamadas} == {str(modelo)} and {c[3] for c in llamadas} == {0.5}
    assert {c[6] for c in llamadas} == {0}
    for llamada, vista in zip(llamadas, data["vistas"], strict=True):
        assert (llamada[4], llamada[5]) == pytest.approx((vista["x"], vista["y"]))
        assert 0 < vista["x"] < 0.297 and 0 < vista["y"] < 0.21
    assert len({(v["x"], v["y"]) for v in data["vistas"]}) == 4
    # Con escala dada el modelo no se abre; el Draft guardado se cierra.
    assert _llamadas(app_falsa, "Documents.Open") == []
    assert _llamadas(app_falsa, "ModelLinks.Add") == [("ModelLinks.Add", str(modelo))]
    assert _llamadas(app_falsa, "SaveAs") == [("SaveAs", "Document1", str(draft))]
    assert _llamadas(app_falsa, "Close") == [("Close", "Pieza.dft", False)]


def test_vistas_elegidas_y_hoja(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)

    r, sobre = cli(
        "draft", "from-part", str(modelo), "--views", "front,iso", "--scale", "2:1", "--sheet", "a3"
    )

    assert r.exit_code == 0, r.output
    assert [c[2] for c in _vistas(app_falsa)] == [4, 9]
    assert [c[3] for c in _vistas(app_falsa)] == [2.0, 2.0]
    assert _llamadas(app_falsa, "SheetSetup.SheetSizeOption=") == [
        ("SheetSetup.SheetSizeOption=", 31)
    ]
    assert sobre["data"]["hoja"] == {
        "nombre": "A3",
        "ancho": 0.42,
        "alto": 0.297,
        "origen": "solicitada",
        "fondo": "A3-Sheet",
    }
    assert _llamadas(app_falsa, "Sheet.Background=") == [("Sheet.Background=", "A3-Sheet")]
    assert sobre["data"]["escala"] == "2:1"


@pytest.mark.parametrize("hoja", ["A5", "A0"])
def test_hoja_sin_fondo_en_la_plantilla_sigue_sin_fondo(cli, app_falsa, tmp_path, hoja):
    modelo = _modelo(tmp_path)

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1:1", "--sheet", hoja)

    assert r.exit_code == 0, r.output
    assert sobre["data"]["hoja"]["fondo"] is None
    assert _llamadas(app_falsa, "Sheet.Background=") == []


@pytest.mark.parametrize(
    ("nombre", "metodo"),
    [("Chapa.psm", "AddSheetMetalView"), ("Conj.asm", "AddAssemblyView"), ("P.par", "AddPartView")],
)
def test_metodo_de_vista_segun_el_tipo(cli, app_falsa, tmp_path, nombre, metodo):
    modelo = _modelo(tmp_path, nombre)
    r, _ = cli("draft", "from-part", str(modelo), "--views", "front", "--scale", "1")
    assert r.exit_code == 0, r.output
    assert len(_vistas(app_falsa, metodo)) == 1


def test_vista_invalida_da_exit_2_sin_com(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    r, sobre = cli("draft", "from-part", str(modelo), "--views", "front,frente")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.registro == []


@pytest.mark.parametrize("opcion", [["--scale", "0"], ["--scale", "x"], ["--sheet", "B9"]])
def test_escala_u_hoja_invalidas_dan_exit_2(cli, app_falsa, tmp_path, opcion):
    modelo = _modelo(tmp_path)
    r, _ = cli("draft", "from-part", str(modelo), *opcion)
    assert r.exit_code == 2 and app_falsa.registro == []


def test_modelo_inexistente_da_exit_5(cli, app_falsa, tmp_path):
    r, sobre = cli("draft", "from-part", str(tmp_path / "No.par"))
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert app_falsa.registro == []


def test_modelo_con_otra_extension_da_exit_2(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path, "Plano.dft")
    r, _ = cli("draft", "from-part", str(modelo))
    assert r.exit_code == 2 and app_falsa.registro == []


def test_plantilla_inexistente_da_exit_5(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    r, _ = cli("draft", "from-part", str(modelo), "--template", str(tmp_path / "t.dft"))
    assert r.exit_code == 5 and app_falsa.registro == []


def test_out_y_plantilla(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    plantilla = _modelo(tmp_path, "base.dft")
    destino = tmp_path / "planos"
    destino.mkdir()

    r, sobre = cli(
        "draft",
        "from-part",
        str(modelo),
        "--out",
        str(destino / "uno"),
        "--template",
        str(plantilla),
        "--scale",
        "1:5",
    )

    assert r.exit_code == 0, r.output
    assert sobre["data"]["draft"] == str(destino / "uno.dft") and (destino / "uno.dft").exists()
    assert ("Documents.Add", str(plantilla)) in app_falsa.registro


def test_pdf(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1:2", "--pdf")

    assert r.exit_code == 0, r.output
    pdf = tmp_path / "Pieza.pdf"
    assert pdf.exists() and sobre["data"]["pdf"] == str(pdf) and sobre["data"]["pdf_bytes"] == 9
    assert _llamadas(app_falsa, "SaveCopyAs") == [("SaveCopyAs", "Pieza.dft", str(pdf))]
    # El PDF se exporta antes de cerrar el Draft.
    nombres = [c[0] for c in app_falsa.registro]
    assert nombres.index("SaveCopyAs") < nombres.index("Close")


def test_keep_open_deja_el_draft_abierto_y_activo(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    previo = app_falsa.agregar_documento("Otro.par", ruta=str(tmp_path / "Otro.par"), tipo=1)

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1", "--keep-open")

    assert r.exit_code == 0 and sobre["data"]["abierto"] is True
    assert _llamadas(app_falsa, "Close") == []
    assert app_falsa.ActiveDocument.Name == "Pieza.dft" and previo.cerrado is False


def test_por_defecto_cierra_el_draft_y_restaura_el_activo(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    a = app_falsa.agregar_documento("A.par", ruta=str(tmp_path / "A.par"), tipo=1)
    app_falsa.agregar_documento("B.par", ruta=str(tmp_path / "B.par"), tipo=1)
    app_falsa._documentos.activo = a

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1")

    assert r.exit_code == 0 and sobre["data"]["abierto"] is False
    assert app_falsa.ActiveDocument.Name == "A.par"


def test_modelo_ya_abierto_no_se_cierra_ni_se_modifica(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    abierto = app_falsa.agregar_documento("Pieza.par", ruta=str(modelo), tipo=1)
    abierto.Models = ColeccionFalsa([ModeloFalso(abierto, caja=CAJA_CHICA)])

    r, sobre = cli("draft", "from-part", str(modelo), "--pdf")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["escala_auto"] is True
    assert abierto.cerrado is False and abierto.Dirty is False
    assert _llamadas(app_falsa, "Documents.Open") == []
    assert all(c[1] != "Pieza.par" for c in _llamadas(app_falsa, "Close"))
    for que in ("Save", "SaveAs", "SaveCopyAs", "Dirty="):
        assert all(c[1] != "Pieza.par" for c in _llamadas(app_falsa, que))
    assert app_falsa.ActiveDocument.Name == "Pieza.par"


def test_auto_abre_el_modelo_para_medirlo_y_lo_cierra_sin_guardar(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    app_falsa._documentos.al_abrir["Pieza.par"] = {"caja": CAJA_CHICA}

    r, sobre = cli("draft", "from-part", str(modelo))

    assert r.exit_code == 0, r.output
    data = sobre["data"]
    assert data["escala_auto"] is True and data["escala"] == "2:1"  # 20 x 15 x 10 mm en A4
    assert {c[3] for c in _vistas(app_falsa)} == {2.0}
    assert ("Close", "Pieza.par", False) in app_falsa.registro
    assert _llamadas(app_falsa, "Save") == []


def test_auto_elige_una_escala_que_entra(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    app_falsa._documentos.al_abrir["Pieza.par"] = {"caja": ((0, 0, 0), (0.5, 0.4, 0.3))}
    r, sobre = cli("draft", "from-part", str(modelo), "--views", "front,top")
    assert r.exit_code == 0
    assert sobre["data"]["escala"] in {"1:2", "1:5"}


def test_auto_sin_caja_usa_1_a_1_e_informa(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)

    r, sobre = cli("draft", "from-part", str(modelo))

    assert r.exit_code == 0, r.output
    assert sobre["data"]["escala"] == "1:1" and sobre["data"]["escala_auto"] is False
    assert {c[3] for c in _vistas(app_falsa)} == {1.0}


def test_auto_en_ensamble_une_las_ocurrencias(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path, "Conj.asm")
    abierto = app_falsa.agregar_documento("Conj.asm", ruta=str(modelo), tipo=3)
    abierto.Occurrences = ColeccionFalsa(
        [
            OcurrenciaFalsa("a", "a.par", caja=((0, 0, 0), (0.01, 0.01, 0.01))),
            OcurrenciaFalsa("b", "b.par", caja=((0.02, 0, 0), (0.04, 0.03, 0.02))),
        ]
    )
    r, sobre = cli("draft", "from-part", str(modelo), "--views", "front")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["escala_auto"] is True
    assert len(_vistas(app_falsa, "AddAssemblyView")) == 1


def test_no_pisa_sin_overwrite_y_pisa_con_overwrite(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    existente = tmp_path / "Pieza.dft"
    existente.write_bytes(b"viejo")

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert existente.read_bytes() == b"viejo" and app_falsa.registro == []

    r, _ = cli("draft", "from-part", str(modelo), "--scale", "1", "--overwrite")
    assert r.exit_code == 0
    assert existente.read_bytes() == b"falso"


def test_pdf_existente_sin_overwrite_da_exit_6_antes_de_crear(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    (tmp_path / "Pieza.pdf").write_bytes(b"viejo")
    r, _ = cli("draft", "from-part", str(modelo), "--scale", "1", "--pdf")
    assert r.exit_code == 6 and app_falsa.registro == []


def test_si_falla_una_vista_el_draft_se_descarta(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    original = app_falsa._documentos.Add

    def agregar_con_fallo(prog_id):
        draft = original(prog_id)
        draft.ActiveSheet.DrawingViews.fallar(
            "AddPartView", com_error(0x80004005, "Error", "Vista inválida")
        )
        return draft

    app_falsa._documentos.Add = agregar_con_fallo

    r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1")

    assert r.exit_code == 4 and sobre["error"]["message"] == "Vista inválida"
    assert not (tmp_path / "Pieza.dft").exists()
    assert _llamadas(app_falsa, "SaveAs") == []
    assert _llamadas(app_falsa, "Close") == [("Close", "Document1", False)]
    assert app_falsa.historial_alertas == [False, True]


def test_readonly_y_dry_run_no_tocan_com(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)

    r, sobre = cli.con("--readonly", "draft", "from-part", str(modelo))
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con("--dry-run", "draft", "from-part", str(modelo), "--pdf", "--sheet", "A4")
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "draft.from-part",
        "modelo": str(modelo),
        "draft": str(tmp_path / "Pieza.dft"),
        "pdf": str(tmp_path / "Pieza.pdf"),
        "vistas": ["front", "top", "right", "iso"],
        "escala": "auto",
        "hoja": "A4",
        "plantilla": None,
        "overwrite": False,
        "keep_open": False,
    }
    assert app_falsa.registro == [] and [p.name for p in tmp_path.iterdir()] == ["Pieza.par"]


def test_display_alerts_se_restaura(cli, app_falsa, tmp_path):
    modelo = _modelo(tmp_path)
    cli("draft", "from-part", str(modelo), "--scale", "1")
    assert app_falsa.historial_alertas == [False, True]


def test_sin_instancia_da_exit_3(cli_sin_instancia, tmp_path):
    modelo = _modelo(tmp_path)
    r, sobre = cli_sin_instancia("draft", "from-part", str(modelo), "--scale", "1")
    assert r.exit_code == 3 and sobre["ok"] is False and sobre["error"]["code"] == "no_conectado"
