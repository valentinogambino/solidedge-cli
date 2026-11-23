"""`se export` de un documento (activo o `--doc`) sobre el COM falso."""

import pytest
from com_falso import com_error


def _doc(app, tmp_path, nombre="Pieza.par", tipo=1, **opciones):
    return app.agregar_documento(nombre, ruta=str(tmp_path / nombre), tipo=tipo, **opciones)


def _copias(app):
    return [llamada for llamada in app.registro if llamada[0] == "SaveCopyAs"]


@pytest.mark.parametrize(
    ("formato", "extension"),
    [("step", ".stp"), ("stl", ".stl"), ("x_t", ".x_t"), ("igs", ".igs")],
)
def test_export_individual_por_formato(cli, app_falsa, tmp_path, formato, extension):
    _doc(app_falsa, tmp_path)

    r, sobre = cli("export", "--format", formato)

    salida = tmp_path / f"Pieza{extension}"
    assert r.exit_code == 0, r.output
    assert _copias(app_falsa) == [("SaveCopyAs", "Pieza.par", str(salida))]
    assert salida.read_bytes() == b"exportado"
    data = sobre["data"]
    assert isinstance(data.pop("duracion_s"), float)
    assert data == {
        "entrada": str(tmp_path / "Pieza.par"),
        "documento": "Pieza.par",
        "tipo": "part",
        "formato": formato,
        "salida": str(salida),
        "ok": True,
        "bytes": 9,
    }
    assert sobre["ok"] is True and sobre["error"] is None


@pytest.mark.parametrize(
    ("alias", "extension"), [("stp", ".stp"), ("IGES", ".igs"), ("parasolid", ".x_t")]
)
def test_alias_de_formato(cli, app_falsa, tmp_path, alias, extension):
    _doc(app_falsa, tmp_path)
    r, sobre = cli("export", "--format", alias)
    assert r.exit_code == 0
    assert sobre["data"]["salida"].endswith(extension)


def test_formato_invalido_da_exit_2_sin_tocar_com(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    r, sobre = cli("export", "--format", "obj")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.registro == []


def test_tipo_incompatible_da_exit_2_sin_escribir(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)
    r, sobre = cli("export", "--format", "step")
    assert r.exit_code == 2
    assert "draft" in sobre["error"]["message"]
    assert _copias(app_falsa) == [] and app_falsa.escrituras == []


def test_documento_sincrono_se_trata_como_pieza(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path, tipo=8)
    r, _ = cli("export", "--format", "step")
    assert r.exit_code == 0


def test_doc_elige_otro_documento_sin_activarlo(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path, "A.par")
    _doc(app_falsa, tmp_path, "B.par")
    r, sobre = cli("export", "--format", "step", "--doc", "A.par")
    assert r.exit_code == 0
    assert sobre["data"]["documento"] == "A.par"
    assert (tmp_path / "A.stp").exists() and not (tmp_path / "B.stp").exists()


def test_out_archivo_y_carpeta(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    destino = tmp_path / "salida"
    destino.mkdir()

    r, sobre = cli("export", "--format", "step", "--out", str(destino))
    assert r.exit_code == 0
    assert sobre["data"]["salida"] == str(destino / "Pieza.stp")

    r, sobre = cli("export", "--format", "stl", "--out", str(tmp_path / "otro"))
    assert r.exit_code == 0
    assert sobre["data"]["salida"] == str(tmp_path / "otro.stl")


def test_out_con_extension_de_otro_formato_da_exit_2(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    r, _ = cli("export", "--format", "step", "--out", str(tmp_path / "x.stl"))
    assert r.exit_code == 2 and app_falsa.registro == []


def test_documento_sin_guardar_exige_out(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("Document1", tipo=1)
    r, sobre = cli("export", "--format", "step")
    assert r.exit_code == 2 and "--out" in sobre["error"]["message"]
    assert _copias(app_falsa) == []

    r, sobre = cli("export", "--format", "step", "--out", str(tmp_path / "nuevo.stp"))
    assert r.exit_code == 0
    assert (tmp_path / "nuevo.stp").exists()


def test_no_pisa_sin_overwrite_y_pisa_con_overwrite(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    existente = tmp_path / "Pieza.stp"
    existente.write_bytes(b"viejo")

    r, sobre = cli("export", "--format", "step")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert existente.read_bytes() == b"viejo" and _copias(app_falsa) == []

    r, _ = cli("export", "--format", "step", "--overwrite")
    assert r.exit_code == 0
    assert existente.read_bytes() == b"exportado"
    # Solid Edge nunca recibe una ruta que ya existe: el archivo previo se aparta antes.
    assert [p.name for p in tmp_path.iterdir() if ".bak" in p.name] == []


def test_overwrite_apartado_y_restaurado_si_falla(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    doc.modo_exportacion = "nada"
    existente = tmp_path / "Pieza.stp"
    existente.write_bytes(b"viejo")

    r, _ = cli("export", "--format", "step", "--overwrite")

    assert r.exit_code == 4
    assert existente.read_bytes() == b"viejo"


@pytest.mark.parametrize("modo", ["nada", "vacio"])
def test_exportacion_sin_contenido_es_error(cli, app_falsa, tmp_path, modo):
    doc = _doc(app_falsa, tmp_path)
    doc.modo_exportacion = modo

    r, sobre = cli("export", "--format", "step")

    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
    assert not (tmp_path / "Pieza.stp").exists()


def test_error_com_de_la_exportacion(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    doc.fallar("SaveCopyAs", com_error(0x80004005, "Error", "No se pudo exportar"))
    r, sobre = cli("export", "--format", "step")
    assert r.exit_code == 4 and sobre["error"]["message"] == "No se pudo exportar"


def test_display_alerts_se_restaura_siempre(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    cli("export", "--format", "step")
    assert app_falsa.historial_alertas == [False, True]

    doc.modo_exportacion = "nada"
    app_falsa.historial_alertas.clear()
    cli("export", "--format", "stl")
    assert app_falsa.historial_alertas == [False, True]


def test_readonly_bloquea_sin_tocar_com(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    r, sobre = cli.con("--readonly", "export", "--format", "step")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.registro == [] and list(tmp_path.iterdir()) == []


def test_dry_run_lista_entradas_y_salidas(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    destino = tmp_path / "x.stp"
    r, sobre = cli.con("--dry-run", "export", "--format", "step", "--out", str(destino))
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "export",
        "formato": "step",
        "entradas": [{"entrada": "activo", "salida": str(destino)}],
        "overwrite": False,
    }
    assert app_falsa.registro == [] and not destino.exists()


def test_sin_instancia_da_exit_3_con_sobre_valido(cli_sin_instancia):
    r, sobre = cli_sin_instancia("export", "--format", "step")
    assert r.exit_code == 3
    assert sobre["ok"] is False and sobre["error"]["code"] == "no_conectado"


# --- PDF, DXF y PNG ---------------------------------------------------------------------------


@pytest.mark.parametrize("formato", ["pdf", "dxf"])
def test_export_de_draft_a_pdf_y_dxf(cli, app_falsa, tmp_path, formato):
    _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)

    r, sobre = cli("export", "--format", formato)

    salida = tmp_path / f"Plano.{formato}"
    assert r.exit_code == 0, r.output
    assert _copias(app_falsa) == [("SaveCopyAs", "Plano.dft", str(salida))]
    data = sobre["data"]
    assert data["formato"] == formato and data["tipo"] == "draft" and data["bytes"] == 9
    assert data["marca_de_agua"] == {"pdf": "presente", "dxf": "ausente"}[formato]
    assert "Community Edition" in data["nota"]


@pytest.mark.parametrize(("nombre", "tipo"), [("P.par", 1), ("C.psm", 4), ("E.asm", 3)])
@pytest.mark.parametrize("formato", ["pdf", "dxf"])
def test_pdf_y_dxf_solo_de_draft(cli, app_falsa, tmp_path, nombre, tipo, formato):
    _doc(app_falsa, tmp_path, nombre, tipo=tipo)
    r, sobre = cli("export", "--format", formato)
    assert r.exit_code == 2 and "draft" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


@pytest.mark.parametrize(
    ("nombre", "tipo"), [("P.par", 1), ("C.psm", 4), ("E.asm", 3), ("D.dft", 2)]
)
def test_png_de_la_vista_de_cualquier_tipo(cli, app_falsa, tmp_path, nombre, tipo):
    _doc(app_falsa, tmp_path, nombre, tipo=tipo)

    r, sobre = cli("export", "--format", "png")

    salida = tmp_path / f"{nombre.split('.')[0]}.png"
    assert r.exit_code == 0, r.output
    assert ("View.SaveAsImage", nombre, str(salida), 1920, 1080) in app_falsa.registro
    llamadas = [c[0] for c in app_falsa.registro]
    assert llamadas.index("View.Fit") < llamadas.index("View.SaveAsImage")
    assert _copias(app_falsa) == []
    assert salida.read_bytes() == b"imagen"
    assert "marca_de_agua" not in sobre["data"]


def test_png_activa_el_documento_y_restaura_el_activo(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path, "A.par")
    _doc(app_falsa, tmp_path, "B.par")  # queda activo

    r, _ = cli("export", "--format", "png", "--doc", "A.par")

    assert r.exit_code == 0
    activaciones = [c[1] for c in app_falsa.registro if c[0] == "Activate"]
    assert activaciones == ["A.par", "B.par"]
    assert app_falsa.ActiveDocument.Name == "B.par"


def test_png_sin_contenido_es_error(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    doc.modo_exportacion = "vacio"
    r, _ = cli("export", "--format", "png")
    assert r.exit_code == 4 and not (tmp_path / "Pieza.png").exists()
