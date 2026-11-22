"""`se sheetmetal flat-dxf` sobre el COM falso."""

import pytest
from com_falso import con_chapa


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
    assert data["marca_de_agua"] == "sin verificar" and data.pop("nota")
    assert data == {
        "entrada": str(tmp_path / "Chapa.psm"),
        "documento": "Chapa.psm",
        "tipo": "sheetmetal",
        "formato": "dxf",
        "salida": str(salida),
        "ok": True,
        "bytes": 9,
        "marca_de_agua": "sin verificar",
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
