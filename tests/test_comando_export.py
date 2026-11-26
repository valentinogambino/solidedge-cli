"""`se export` de un documento (activo o `--doc`) sobre el COM falso."""

import pytest
from com_falso import ColeccionFalsa, ComErrorFalso, com_error, ruta_de_largo


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


def _acceso_denegado():
    """Lo que dio Solid Edge en vivo: `DISP_E_EXCEPTION` con scode E_ACCESSDENIED."""
    return ComErrorFalso(
        0x80020009, "Exception occurred.", (0, None, None, None, 0, 0x80070005 - 2**32)
    )


def test_dxf_de_draft_reintenta_una_vez_si_falla_con_acceso_denegado(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)
    doc.fallar("SaveCopyAs", _acceso_denegado())

    r, sobre = cli("export", "--format", "dxf")

    assert r.exit_code == 0, r.output
    salida = tmp_path / "Plano.dxf"
    assert len(_copias(app_falsa)) == 2 and salida.read_bytes() == b"exportado"
    assert sobre["data"]["reintento"] is True and sobre["data"]["bytes"] == 9


def test_dxf_sin_fallo_no_informa_reintento(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)
    r, sobre = cli("export", "--format", "dxf")
    assert r.exit_code == 0 and "reintento" not in sobre["data"]
    assert len(_copias(app_falsa)) == 1


def test_dxf_con_acceso_denegado_persistente_es_exit_6_y_no_deja_archivo(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)
    salida = tmp_path / "Plano.dxf"
    original = doc.SaveCopyAs

    def a_medias(ruta):
        salida.write_bytes(b"parcial")
        original(ruta)

    doc.SaveCopyAs = a_medias
    doc.fallar("SaveCopyAs", _acceso_denegado(), _acceso_denegado())

    r, sobre = cli("export", "--format", "dxf")

    error = sobre["error"]
    assert r.exit_code == 6 and error["code"] == "no_soportado"
    assert error["hresult"] == "0x80020009"
    assert error["details"]["causa"] == "acceso_denegado"
    assert error["details"]["scode"] == "0x80070005" and error["details"]["reintentos"] == 1
    assert (
        "rechazó la escritura" in error["message"] and "reintentar el comando" in error["message"]
    )
    assert len(_copias(app_falsa)) == 2
    assert not salida.exists()


def test_dxf_con_otro_error_no_reintenta(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)
    doc.fallar("SaveCopyAs", _dce_sin_detalles())

    r, _ = cli("export", "--format", "dxf")

    assert r.exit_code == 4 and len(_copias(app_falsa)) == 1


def test_dxf_de_draft_si_el_reintento_falla_distinto_no_se_reclasifica(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path, "Plano.dft", tipo=2)
    doc.fallar("SaveCopyAs", _acceso_denegado(), _dce_sin_detalles())

    r, sobre = cli("export", "--format", "dxf")

    assert r.exit_code == 4 and "causa" not in (sobre["error"].get("details") or {})


@pytest.mark.parametrize(
    ("nombre", "tipo", "tamano"),
    [
        ("P.par", 1, (1920, 1080)),
        ("C.psm", 4, (1920, 1080)),
        ("E.asm", 3, (1920, 1080)),
        # Draft: la proporción sigue a la hoja (A4 apaisada por defecto), no 16:9.
        ("D.dft", 2, (1920, 1358)),
    ],
)
def test_png_de_la_vista_de_cualquier_tipo(cli, app_falsa, tmp_path, nombre, tipo, tamano):
    _doc(app_falsa, tmp_path, nombre, tipo=tipo)

    r, sobre = cli("export", "--format", "png")

    salida = tmp_path / f"{nombre.split('.')[0]}.png"
    assert r.exit_code == 0, r.output
    assert ("View.SaveAsImage", nombre, str(salida), *tamano) in app_falsa.registro
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


@pytest.mark.parametrize("formato", ["pdf", "dxf"])
def test_pdf_y_dxf_de_un_draft_no_activo_lo_activan_y_restauran_el_activo(
    cli, app_falsa, tmp_path, formato
):
    # Con otro Draft activo, SaveCopyAs exporta el contenido del activo: hay que activar el pedido.
    _doc(app_falsa, tmp_path, "A.dft", tipo=2)
    _doc(app_falsa, tmp_path, "B.dft", tipo=2)  # queda activo

    r, _ = cli("export", "--format", formato, "--doc", "A.dft")

    assert r.exit_code == 0
    activaciones = [c[1] for c in app_falsa.registro if c[0] == "Activate"]
    assert activaciones == ["A.dft", "B.dft"]
    assert _copias(app_falsa) == [("SaveCopyAs", "A.dft", str(tmp_path / f"A.{formato}"))]
    assert app_falsa.ActiveDocument.Name == "B.dft"


def test_png_sin_contenido_es_error(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    doc.modo_exportacion = "vacio"
    r, _ = cli("export", "--format", "png")
    assert r.exit_code == 4 and not (tmp_path / "Pieza.png").exists()


@pytest.mark.parametrize(
    ("ancho", "alto", "tamano"),
    [(0.420, 0.297, (1920, 1358)), (0.297, 0.420, (1358, 1920)), (0.0, 0.0, (1920, 1080))],
)
def test_png_de_draft_conserva_la_proporcion_de_la_hoja(
    cli, app_falsa, tmp_path, ancho, alto, tamano
):
    doc = _doc(app_falsa, tmp_path, "D.dft", tipo=2)
    doc.ActiveSheet.SheetSetup.SheetWidth = ancho
    doc.ActiveSheet.SheetSetup.SheetHeight = alto

    r, _ = cli("export", "--format", "png")

    assert r.exit_code == 0, r.output
    salida = tmp_path / "D.png"
    assert ("View.SaveAsImage", "D.dft", str(salida), *tamano) in app_falsa.registro


def test_overwrite_con_timeout_conserva_el_apartado(cli, app_falsa, sta, monkeypatch, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    doc.bloqueo.bloquear("SaveCopyAs")
    monkeypatch.setattr(sta, "_cancelar", lambda _: doc.bloqueo.cancelar())
    existente = tmp_path / "Pieza.stp"
    existente.write_bytes(b"viejo")

    r, sobre = cli("--timeout", "0.3", "export", "--format", "step", "--overwrite")

    assert r.exit_code == 7 and sobre["error"]["code"] == "ocupado"
    apartado = sobre["error"]["details"]["apartado"]
    # Solid Edge podría seguir escribiendo el destino: no se restaura ni se borra el apartado.
    assert [p.name for p in tmp_path.iterdir() if ".bak" in p.name] == [
        apartado.rsplit("\\", 1)[-1]
    ]
    with open(apartado, "rb") as archivo:
        assert archivo.read() == b"viejo"
    assert not existente.exists()


# --- Causas de un fallo de SaveCopyAs (verificadas en vivo, 2026-11-25) -------------------------


def _dce_sin_detalles(scode=0x80004005):
    """Lo que da Solid Edge: `DISP_E_EXCEPTION` sin descripción y con el error real en el scode."""
    return ComErrorFalso(0x80020009, "Exception occurred.", (0, None, None, None, 0, scode - 2**32))


@pytest.mark.parametrize("formato", ["stl", "x_t", "igs"])
def test_pieza_sin_geometria_a_formato_que_la_exige_es_exit_6_claro(
    cli, app_falsa, tmp_path, formato
):
    doc = _doc(app_falsa, tmp_path)
    doc.fallar("SaveCopyAs", _dce_sin_detalles())

    r, sobre = cli("export", "--format", formato)

    error = sobre["error"]
    assert r.exit_code == 6 and error["code"] == "no_soportado"
    assert "no tiene geometría" in error["message"] and formato in error["message"]
    assert error["hresult"] == "0x80020009"
    assert error["details"]["causa"] == "documento_vacio"
    assert error["details"]["scode"] == "0x80004005"
    assert not (tmp_path / f"Pieza.{formato}").exists()


def test_ensamble_sin_ocurrencias_a_stl_es_exit_6(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path, nombre="Conj.asm", tipo=3)
    doc.fallar("SaveCopyAs", _dce_sin_detalles())

    r, sobre = cli("export", "--format", "stl")

    assert r.exit_code == 6 and sobre["error"]["details"]["causa"] == "documento_vacio"


def test_pieza_con_geometria_que_falla_no_se_acusa_de_vacia(cli, app_falsa, tmp_path):
    doc = _doc(app_falsa, tmp_path)
    doc.Models = ColeccionFalsa([object()])
    doc.fallar("SaveCopyAs", _dce_sin_detalles())

    r, sobre = cli("export", "--format", "stl")

    error = sobre["error"]
    assert r.exit_code == 4 and error["code"] == "com_error"
    assert "no dio detalles" in error["message"] and "260" in error["message"]
    assert error["hresult"] == "0x80020009" and error["details"]["scode"] == "0x80004005"
    assert "causa" not in error["details"]


def test_step_de_pieza_vacia_no_se_diagnostica_como_vacia(cli, app_falsa, tmp_path):
    # STEP se escribe aunque no haya geometría: un fallo ahí es otra cosa.
    doc = _doc(app_falsa, tmp_path)
    doc.fallar("SaveCopyAs", _dce_sin_detalles())

    r, sobre = cli("export", "--format", "step")

    assert r.exit_code == 4 and "causa" not in sobre["error"]["details"]


def test_export_con_ruta_de_260_caracteres_es_exit_2_sin_tocar_com(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    salida = ruta_de_largo(tmp_path, 260, ".stp")
    assert len(str(salida)) == 260

    r, sobre = cli("export", "--format", "step", "--out", str(salida))

    error = sobre["error"]
    assert r.exit_code == 2 and error["code"] == "argumento_invalido"
    assert error["details"]["largo"] == 260 and error["details"]["maximo"] == 259
    assert _copias(app_falsa) == []


def test_export_con_ruta_de_259_caracteres_llega_a_solid_edge(cli, app_falsa, tmp_path):
    _doc(app_falsa, tmp_path)
    salida = ruta_de_largo(tmp_path, 259, ".stp")
    salida.parent.mkdir(parents=True)
    assert len(str(salida)) == 259

    r, _ = cli("export", "--format", "step", "--out", str(salida))

    assert r.exit_code == 0 and len(_copias(app_falsa)) == 1


def test_lote_con_ruta_de_salida_larga_falla_ese_archivo_con_exit_2(tmp_path):
    # El lote no pasa por `validar_destino`: lo cubre `escribir`.
    from se_cli.core import exportar
    from se_cli.core.errors import ArgumentoInvalido

    with pytest.raises(ArgumentoInvalido, match="260"):
        exportar.escribir(
            object(), exportar.FORMATOS["step"], str(ruta_de_largo(tmp_path, 262, ".stp")), False
        )
