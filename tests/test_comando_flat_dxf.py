"""`se sheetmetal flat-dxf` sobre el COM falso."""

import pytest
from com_falso import (
    CILINDRO_GEOMETRIA,
    DXF_CON_ENTIDADES,
    DXF_VACIO,
    AristaFalsa,
    CaraFalsa,
    ColeccionFalsa,
    ComErrorFalso,
    FeatureFalsa,
    con_chapa,
    con_chapa_creable,
)

from se_cli.core import chapa


def _chapa(app, tmp_path, nombre="Chapa.psm", **opciones):
    return app.agregar_documento(nombre, ruta=str(tmp_path / nombre), tipo=4, **opciones)


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


def test_camino_feliz_con_el_documento_activo(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path)

    r, sobre = cli("sheetmetal", "flat-dxf")

    salida = tmp_path / "Chapa.dxf"
    assert r.exit_code == 0, r.output
    assert salida.read_bytes() == b"dxf-plano"
    assert _llamadas(app_falsa, "SaveAsFlatDXFEx") == [
        ("SaveAsFlatDXFEx", "Chapa.psm", str(salida), None, None, None, True)
    ]
    data = sobre["data"]
    assert isinstance(data.pop("duracion_s"), float)
    assert data["marca_de_agua"] == "ausente" and data.pop("nota")
    assert data == {
        "entrada": str(tmp_path / "Chapa.psm"),
        "documento": "Chapa.psm",
        "tipo": "sheetmetal",
        "formato": "dxf",
        "salida": str(salida),
        "ok": True,
        "bytes": 9,
        "marca_de_agua": "ausente",
    }
    assert _llamadas(app_falsa, "Close") == [] and _llamadas(app_falsa, "Save") == []


def test_out_archivo_y_carpeta(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path)
    carpeta = tmp_path / "dxf"
    carpeta.mkdir()

    r, sobre = cli("sheetmetal", "flat-dxf", "--out", str(carpeta))
    assert r.exit_code == 0 and sobre["data"]["salida"] == str(carpeta / "Chapa.dxf")

    r, sobre = cli("sheetmetal", "flat-dxf", "--out", str(tmp_path / "otra.dxf"))
    assert r.exit_code == 0 and (tmp_path / "otra.dxf").exists()

    r, _ = cli("sheetmetal", "flat-dxf", "--out", str(tmp_path / "otra.stp"))
    assert r.exit_code == 2


def test_documento_que_no_es_chapa_da_exit_2(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("Pieza.par", ruta=str(tmp_path / "Pieza.par"), tipo=1)
    r, sobre = cli("sheetmetal", "flat-dxf")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert app_falsa.escrituras == []


def test_chapa_sin_desarrollo_da_exit_5_con_explicacion(cli, app_falsa, tmp_path):
    con_chapa(_chapa(app_falsa, tmp_path), con_desarrollo=False)

    r, sobre = cli("sheetmetal", "flat-dxf")

    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert "flat pattern" in sobre["error"]["message"] and "Solid Edge" in sobre["error"]["message"]
    assert app_falsa.escrituras == [] and list(tmp_path.iterdir()) == []
    detalles = sobre["error"]["details"]
    assert detalles["documento"] == "Chapa.psm" and detalles["cambios_pendientes"] is False
    assert "--create" in detalles["hint"] and "guarda la chapa" in detalles["hint"]
    assert "cambio pendiente" in detalles["hint"]


def test_sin_desarrollo_avisa_si_create_guardaria_cambios_pendientes(cli, app_falsa, tmp_path):
    con_chapa(_chapa(app_falsa, tmp_path, sucio=True), con_desarrollo=False)

    r, sobre = cli("sheetmetal", "flat-dxf")

    assert r.exit_code == 5 and sobre["error"]["details"]["cambios_pendientes"] is True
    assert app_falsa.escrituras == []


def test_sin_desarrollo_con_dirty_ilegible_no_cambia_el_codigo(cli, app_falsa, tmp_path):
    doc = _chapa(app_falsa, tmp_path)
    con_chapa(doc, con_desarrollo=False)
    doc.fallar("Dirty", RuntimeError("sin Dirty"))

    r, sobre = cli("sheetmetal", "flat-dxf")

    assert r.exit_code == 5 and sobre["error"]["details"]["cambios_pendientes"] is None
    assert "--create" in sobre["error"]["details"]["hint"]


def test_doc_elige_la_chapa(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path, "A.psm")
    _chapa(app_falsa, tmp_path, "B.psm")
    r, sobre = cli("sheetmetal", "flat-dxf", "--doc", "A.psm")
    assert r.exit_code == 0 and sobre["data"]["documento"] == "A.psm"


def test_archivo_no_abierto_se_abre_y_se_cierra_sin_guardar(cli, app_falsa, tmp_path):
    ruta = tmp_path / "Pieza.psm"
    ruta.write_bytes(b"x")

    r, sobre = cli("sheetmetal", "flat-dxf", str(ruta))

    assert r.exit_code == 0, r.output
    assert _llamadas(app_falsa, "Documents.Open")[0][1] == str(ruta)
    assert _llamadas(app_falsa, "Close") == [("Close", "Pieza.psm", False)]
    assert _llamadas(app_falsa, "Save") == []
    assert (tmp_path / "Pieza.dxf").exists()


def test_archivo_ya_abierto_no_se_cierra(cli, app_falsa, tmp_path):
    ruta = tmp_path / "Pieza.psm"
    ruta.write_bytes(b"x")
    abierto = _chapa(app_falsa, tmp_path, "Pieza.psm")

    r, _ = cli("sheetmetal", "flat-dxf", str(ruta))

    assert r.exit_code == 0
    assert abierto.cerrado is False and _llamadas(app_falsa, "Documents.Open") == []


def test_archivo_sin_desarrollo_se_cierra_igual(cli, app_falsa, tmp_path):
    ruta = tmp_path / "Pieza.psm"
    ruta.write_bytes(b"x")
    app_falsa._documentos.al_abrir["Pieza.psm"] = {"desarrollo": False}

    r, _ = cli("sheetmetal", "flat-dxf", str(ruta))

    assert r.exit_code == 5
    assert _llamadas(app_falsa, "Close") == [("Close", "Pieza.psm", False)]


def test_archivos_invalidos(cli, app_falsa, tmp_path):
    r, _ = cli("sheetmetal", "flat-dxf", str(tmp_path / "No.psm"))
    assert r.exit_code == 5

    pieza = tmp_path / "P.par"
    pieza.write_bytes(b"x")
    r, _ = cli("sheetmetal", "flat-dxf", str(pieza))
    assert r.exit_code == 2

    chapa = tmp_path / "C.psm"
    chapa.write_bytes(b"x")
    r, _ = cli("sheetmetal", "flat-dxf", str(chapa), "--doc", "1")
    assert r.exit_code == 2
    assert app_falsa.registro == []


def test_no_pisa_sin_overwrite_y_pisa_con_overwrite(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path)
    existente = tmp_path / "Chapa.dxf"
    existente.write_bytes(b"viejo")

    r, sobre = cli("sheetmetal", "flat-dxf")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert existente.read_bytes() == b"viejo" and _llamadas(app_falsa, "SaveAsFlatDXFEx") == []

    r, _ = cli("sheetmetal", "flat-dxf", "--overwrite")
    assert r.exit_code == 0 and existente.read_bytes() == b"dxf-plano"


@pytest.mark.parametrize("modo", ["nada", "vacio"])
def test_sin_contenido_es_error(cli, app_falsa, tmp_path, modo):
    _chapa(app_falsa, tmp_path).modo_exportacion = modo
    r, _ = cli("sheetmetal", "flat-dxf")
    assert r.exit_code == 4 and not (tmp_path / "Chapa.dxf").exists()


def test_readonly_y_dry_run(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path)

    r, sobre = cli.con("--readonly", "sheetmetal", "flat-dxf")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con("--dry-run", "sheetmetal", "flat-dxf", "--out", str(tmp_path / "x.dxf"))
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "sheetmetal.flat-dxf",
        "entrada": "activo",
        "salida": str(tmp_path / "x.dxf"),
        "overwrite": False,
    }
    assert app_falsa.registro == [] and list(tmp_path.iterdir()) == []


def test_display_alerts_se_restaura(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path).modo_exportacion = "nada"
    cli("sheetmetal", "flat-dxf")
    assert app_falsa.historial_alertas == [False, True]


def test_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("sheetmetal", "flat-dxf")
    assert r.exit_code == 3 and sobre["ok"] is False and sobre["error"]["code"] == "no_conectado"


# --- --create -------------------------------------------------------------------------------


def _creable(app, tmp_path, nombre="Chapa.psm", **opciones):
    doc = app.agregar_documento(nombre, ruta=str(tmp_path / nombre), tipo=4, **opciones)
    (tmp_path / nombre).write_bytes(b"psm")
    return con_chapa_creable(doc)


def test_create_arma_el_desarrollo_guarda_reabre_y_exporta(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path)

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 0, r.output
    data = sobre["data"]
    assert data["desarrollo_creado"] is True and data["documento_guardado"] is True
    assert data["cara"] == {
        "indice": 2,
        "area_si": 0.0048,
        "criterio": "cara plana de mayor area",
        "arista": 1,
        "desarrollo_reutilizado": False,
    }
    assert data["entidades_dxf"] == 2 and data["bytes"] > 0
    assert [c[0] for c in app_falsa.escrituras] == [
        "FlatPatternModels.Add",
        "FlatPatterns.Add",
        "Save",
        "Close",
        "Documents.Open",
        "Activate",
        "SaveAsFlatDXFEx",
    ]
    assert _llamadas(app_falsa, "Documents.Open") == [
        ("Documents.Open", str(tmp_path / "Chapa.psm"))
    ]
    assert (tmp_path / "Chapa.dxf").read_bytes() == DXF_CON_ENTIDADES
    # El documento queda abierto y activo, y se restauran las alertas.
    assert app_falsa.ActiveDocument.Name == "Chapa.psm"
    assert app_falsa.Documents.Count == 1
    assert app_falsa.historial_alertas == [False, True]


def test_create_elige_la_cara_plana_de_mayor_area(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.Models.Item(1).Body.caras[:] = [
        CaraFalsa(0.5, CILINDRO_GEOMETRIA),
        CaraFalsa(0.002),
        CaraFalsa(0.004),
        CaraFalsa(0.004),
    ]

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["cara"]["indice"] == 3  # empate: la de menor índice; el cilindro no
    assert _llamadas(app_falsa, "FlatPatterns.Add") == [("FlatPatterns.Add", 0.004)]


def test_create_sin_efecto_si_ya_tiene_desarrollo(cli, app_falsa, tmp_path):
    _chapa(app_falsa, tmp_path).dxf_con_entidades = True

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["desarrollo_creado"] is False
    assert sobre["data"]["documento_guardado"] is False and sobre["data"]["cara"] is None
    assert [c[0] for c in app_falsa.escrituras] == ["SaveAsFlatDXFEx"]


def test_create_no_guardada_da_exit_2_sin_tocar_nada(cli, app_falsa):
    con_chapa_creable(app_falsa.agregar_documento("Nueva.psm", tipo=4))

    r, sobre = cli("sheetmetal", "flat-dxf", "--create", "--out", "x.dxf")

    assert r.exit_code == 2 and "save-as" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_create_solo_lectura_da_exit_6_sin_tocar_nada(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path, solo_lectura=True)

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.escrituras == []


def test_create_con_destino_ocupado_no_toca_la_chapa(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path)
    (tmp_path / "Chapa.dxf").write_bytes(b"viejo")

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 6 and "--overwrite" in sobre["error"]["message"]
    assert app_falsa.escrituras == []
    assert (tmp_path / "Chapa.dxf").read_bytes() == b"viejo"


def test_create_con_dxf_vacio_es_error_y_no_deja_archivo(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path).dxf_siempre_vacio = True

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 4 and "sin entidades" in sobre["error"]["message"]
    assert not (tmp_path / "Chapa.dxf").exists()


def test_create_con_dxf_vacio_conserva_el_dxf_previo_con_overwrite(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path).dxf_siempre_vacio = True
    (tmp_path / "Chapa.dxf").write_bytes(b"viejo")

    r, _ = cli("sheetmetal", "flat-dxf", "--create", "--overwrite")

    assert r.exit_code == 4
    assert (tmp_path / "Chapa.dxf").read_bytes() == b"viejo"


def test_create_con_archivo_no_abierto_lo_cierra_al_terminar(cli, app_falsa, tmp_path):
    ruta = tmp_path / "Pieza.psm"
    ruta.write_bytes(b"psm")
    abrir = app_falsa._documentos.Open
    abiertos = []

    def abrir_creable(ruta_):
        doc = abrir(ruta_)
        if not abiertos:  # solo la primera apertura es la chapa sin desarrollo
            con_chapa_creable(doc)
        abiertos.append(doc)
        return doc

    app_falsa._documentos.Open = abrir_creable

    r, sobre = cli("sheetmetal", "flat-dxf", str(ruta), "--create")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["desarrollo_creado"] is True
    assert len(abiertos) == 2 and app_falsa.Documents.Count == 0
    assert (tmp_path / "Pieza.dxf").read_bytes() == DXF_CON_ENTIDADES


def test_create_reactiva_el_documento_que_estaba_activo(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path, "A.psm")
    otro = app_falsa.agregar_documento("B.par", ruta=str(tmp_path / "B.par"), tipo=1)

    r, sobre = cli("sheetmetal", "flat-dxf", "--create", "--doc", "A.psm")

    assert r.exit_code == 0, r.output
    assert app_falsa.ActiveDocument is otro


def test_create_documento_que_no_es_chapa_da_exit_2(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("P.par", ruta=str(tmp_path / "P.par"), tipo=1)
    r, _ = cli("sheetmetal", "flat-dxf", "--create")
    assert r.exit_code == 2
    assert app_falsa.escrituras == []


def test_create_readonly_y_dry_run(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path)

    r, sobre = cli.con("--readonly", "sheetmetal", "flat-dxf", "--create")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con("--dry-run", "sheetmetal", "flat-dxf", "--create", "--out", "x.dxf")
    assert r.exit_code == 0
    assert sobre["data"]["create"] is True and sobre["data"]["dry_run"] is True
    assert app_falsa.registro == []


def test_create_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("sheetmetal", "flat-dxf", "--create")
    assert r.exit_code == 3 and sobre["error"]["code"] == "no_conectado"


def test_sin_create_una_chapa_creable_sigue_dando_exit_5(cli, app_falsa, tmp_path):
    _creable(app_falsa, tmp_path)
    r, sobre = cli("sheetmetal", "flat-dxf")
    assert r.exit_code == 5 and "--create" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


# --- --create en chapas con cortes o que no se pueden desarrollar ----------------------------

TAB = -1470838992
EXTRUSION = 462094706
CORTE = 462094714


def _con_agujero(doc, aristas=None):
    """La cara grande con el círculo del agujero como arista 1 (como en Solid Edge)."""
    doc.Models.Item(1).Body.caras[1] = CaraFalsa(
        0.0048, aristas=aristas or [AristaFalsa(cerrada=True), AristaFalsa(), AristaFalsa()]
    )
    return doc


def _features(doc, *features):
    doc.Models.Item(1).Features = ColeccionFalsa(list(features))


def test_create_con_agujero_saltea_la_arista_cerrada(cli, app_falsa, tmp_path):
    _con_agujero(_creable(app_falsa, tmp_path))

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["cara"]["arista"] == 2
    assert sobre["data"]["desarrollo_creado"] is True


def test_create_sin_arista_con_vertice_es_error_sin_tocar_nada(cli, app_falsa, tmp_path):
    _con_agujero(_creable(app_falsa, tmp_path), [AristaFalsa(cerrada=True)])

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 4 and "arista" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_create_no_desarrollable_da_exit_6_clasificado_y_no_guarda(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True
    _features(doc, FeatureFalsa("Tab_1", TAB), FeatureFalsa("ExtrudedCutout_1", CORTE))

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 6, r.output
    error = sobre["error"]
    assert error["code"] == "no_soportado" and error["hresult"] == "0x80020009"
    assert "Exception occurred" not in error["message"] and "desarrollar" in error["message"]
    detalles = error["details"]
    assert detalles["base"] == {"nombre": "Tab_1", "tipo": "Tab"}
    assert "rechazó el desarrollo" in detalles["causa_probable"]
    assert detalles["documento_guardado"] is False
    assert detalles["desarrollo_vacio_limpiado"] is True
    assert detalles["desarrollo_vacio_en_sesion"] is False and "Undo" in detalles["hint"]
    assert [c[0] for c in app_falsa.escrituras] == [
        "FlatPatternModels.Add",
        "FlatPatterns.Add",
        "Undo",
    ]
    assert doc.FlatPatternModels.Count == 0
    assert not (tmp_path / "Chapa.dxf").exists()


def test_create_fallido_hace_un_solo_undo_y_el_reintento_vuelve_a_crear(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True

    r, _ = cli("sheetmetal", "flat-dxf", "--create")
    assert r.exit_code == 6 and len(_llamadas(app_falsa, "Undo")) == 1
    assert doc.FlatPatternModels.Count == 0

    doc.no_desarrollable = False
    r, sobre = cli("sheetmetal", "flat-dxf", "--create")
    assert r.exit_code == 0, r.output
    assert sobre["data"]["cara"]["desarrollo_reutilizado"] is False
    assert len(_llamadas(app_falsa, "Undo")) == 1


def test_create_fallido_si_el_undo_no_baja_la_cuenta_informa_que_no_se_limpio(
    cli, app_falsa, tmp_path
):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True
    doc.undo_deshace_el_desarrollo = False

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    detalles = sobre["error"]["details"]
    assert r.exit_code == 6 and detalles["desarrollo_vacio_limpiado"] is False
    assert detalles["desarrollo_vacio_en_sesion"] is True and "--discard" in detalles["hint"]
    assert len(_llamadas(app_falsa, "Undo")) == 1 and doc.FlatPatternModels.Count == 1


def test_create_fallido_con_undo_que_falla_no_tapa_el_error_original(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True
    doc.fallar("Undo", ComErrorFalso(0x80020009, "Exception occurred."))

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 6 and sobre["error"]["code"] == "no_soportado"
    assert sobre["error"]["details"]["desarrollo_vacio_limpiado"] is False


def test_create_con_base_de_pieza_explica_la_causa(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True
    _features(doc, FeatureFalsa("ExtrudedProtrusion_1", EXTRUSION))

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 6
    detalles = sobre["error"]["details"]
    assert detalles["base"] == {"nombre": "ExtrudedProtrusion_1", "tipo": "ExtrudedProtrusion"}
    assert "operación de pieza" in detalles["causa_probable"]


def test_reintento_reutiliza_el_desarrollo_vacio(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True
    doc.undo_deshace_el_desarrollo = False  # el Undo no limpia: queda un modelo vacío
    r, _ = cli("sheetmetal", "flat-dxf", "--create")
    assert r.exit_code == 6 and doc.FlatPatternModels.Count == 1

    # Sin --create, el desarrollo vacío no cuenta: exit 5, no un DXF vacío.
    r, sobre = cli("sheetmetal", "flat-dxf")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"
    assert _llamadas(app_falsa, "SaveAsFlatDXFEx") == []

    doc.no_desarrollable = False
    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 0, r.output
    assert sobre["data"]["cara"]["desarrollo_reutilizado"] is True
    assert len(_llamadas(app_falsa, "FlatPatternModels.Add")) == 1
    assert (tmp_path / "Chapa.dxf").read_bytes() == DXF_CON_ENTIDADES


def test_create_fallido_sobre_un_modelo_vacio_reutilizado_no_hace_undo(cli, app_falsa, tmp_path):
    doc = _creable(app_falsa, tmp_path)
    doc.no_desarrollable = True
    doc.undo_deshace_el_desarrollo = False
    cli("sheetmetal", "flat-dxf", "--create")  # deja un modelo vacío (el Undo no lo limpió)
    assert doc.FlatPatternModels.Count == 1 and len(_llamadas(app_falsa, "Undo")) == 1

    r, sobre = cli("sheetmetal", "flat-dxf", "--create")

    assert r.exit_code == 6 and sobre["error"]["details"]["desarrollo_vacio_limpiado"] is False
    assert len(_llamadas(app_falsa, "Undo")) == 1 and doc.FlatPatternModels.Count == 1


def test_create_no_desarrollable_abierto_por_ruta_se_cierra_sin_guardar(cli, app_falsa, tmp_path):
    ruta = tmp_path / "Pieza.psm"
    ruta.write_bytes(b"psm")
    abrir = app_falsa._documentos.Open

    def abrir_no_desarrollable(ruta_):
        doc = con_chapa_creable(abrir(ruta_))
        doc.no_desarrollable = True
        return doc

    app_falsa._documentos.Open = abrir_no_desarrollable

    r, sobre = cli("sheetmetal", "flat-dxf", str(ruta), "--create")

    assert r.exit_code == 6
    assert sobre["error"]["details"]["desarrollo_vacio_en_sesion"] is False
    assert "no cambió" in sobre["error"]["details"]["hint"]
    assert _llamadas(app_falsa, "Close") == [("Close", "Pieza.psm", False)]
    assert _llamadas(app_falsa, "Save") == [] and app_falsa.Documents.Count == 0


def test_contar_entidades_dxf(tmp_path):
    vacio = tmp_path / "v.dxf"
    vacio.write_bytes(DXF_VACIO)
    lleno = tmp_path / "l.dxf"
    lleno.write_bytes(DXF_CON_ENTIDADES)
    assert chapa.contar_entidades_dxf(str(vacio)) == 0
    assert chapa.contar_entidades_dxf(str(lleno)) == 2
    assert chapa.contar_entidades_dxf(str(tmp_path / "no.dxf")) == 0
