"""`se export` por lotes (archivos, carpetas y globs) sobre el COM falso."""

import pytest
from com_falso import com_error


def _tocar(carpeta, *nombres):
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre in nombres:
        (carpeta / nombre).write_bytes(b"x")
    return [str(carpeta / n) for n in nombres]


def _llamadas(app, que):
    return [c for c in app.registro if c[0] == que]


def test_glob_exporta_solo_lo_que_coincide(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par", "B.par", "C.psm")

    r, sobre = cli("export", str(tmp_path / "*.par"), "--format", "step")

    assert r.exit_code == 0, r.output
    data = sobre["data"]
    assert data["resumen"] == {"total": 2, "ok": 2, "fallidos": 0}
    assert [x["salida"] for x in data["resultados"]] == [
        str(tmp_path / "A.stp"),
        str(tmp_path / "B.stp"),
    ]
    for resultado in data["resultados"]:
        assert resultado["ok"] is True and resultado["bytes"] == 9
        assert isinstance(resultado["duracion_s"], float)
        assert set(resultado) == {"entrada", "salida", "ok", "bytes", "duracion_s"}
    assert (tmp_path / "A.stp").exists() and not (tmp_path / "C.stp").exists()
    assert data["formato"] == "step"


def test_carpeta_toma_los_compatibles_con_el_formato(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par", "B.psm", "C.asm", "D.dft", "nota.txt")

    r, sobre = cli("export", str(tmp_path), "--format", "step")
    assert r.exit_code == 0
    assert [x["entrada"] for x in sobre["data"]["resultados"]] == [
        str(tmp_path / "A.par"),
        str(tmp_path / "B.psm"),
        str(tmp_path / "C.asm"),
    ]

    r, sobre = cli("export", str(tmp_path), "--format", "pdf")
    assert r.exit_code == 0
    assert [x["entrada"] for x in sobre["data"]["resultados"]] == [str(tmp_path / "D.dft")]
    assert sobre["data"]["marca_de_agua"] == "presente"


def test_recursive_baja_por_subcarpetas(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par")
    _tocar(tmp_path / "sub", "B.par")

    r, sobre = cli("export", str(tmp_path), "--format", "step")
    assert [x["entrada"] for x in sobre["data"]["resultados"]] == [str(tmp_path / "A.par")]

    r, sobre = cli("export", str(tmp_path), "--format", "stl", "--recursive")
    assert sorted(x["entrada"] for x in sobre["data"]["resultados"]) == sorted(
        [str(tmp_path / "A.par"), str(tmp_path / "sub" / "B.par")]
    )

    r, sobre = cli("export", str(tmp_path / "**" / "*.par"), "--format", "igs", "--recursive")
    assert sobre["data"]["resumen"]["total"] == 2


def test_entradas_invalidas_no_tocan_com(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "D.dft", "A.par")

    r, sobre = cli("export", str(tmp_path / "D.dft"), "--format", "step")
    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"

    r, _ = cli("export", str(tmp_path / "no_esta.par"), "--format", "step")
    assert r.exit_code == 5

    r, _ = cli("export", str(tmp_path / "*.xyz"), "--format", "step")
    assert r.exit_code == 5

    r, _ = cli("export", str(tmp_path / "A.par"), "--format", "step", "--doc", "1")
    assert r.exit_code == 2

    assert app_falsa.registro == []


def test_salidas_repetidas_dan_exit_2(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par", "A.psm")
    r, sobre = cli("export", str(tmp_path), "--format", "step")
    assert r.exit_code == 2 and "misma salida" in sobre["error"]["message"]

    _tocar(tmp_path / "sub", "A.par")
    r, _ = cli(
        "export", str(tmp_path / "A.par"), str(tmp_path / "sub" / "A.par"),
        "--format", "step", "--out", str(tmp_path / "out"),
    )  # fmt: skip
    assert r.exit_code == 2
    assert app_falsa.registro == []


def test_mezcla_de_ok_y_fallidos_da_exit_1_con_resultados_parciales(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par", "B.par", "C.par", "D.par")
    app_falsa._documentos.al_abrir["B.par"] = {"error": com_error(0x80004005, "x", "No abre")}
    app_falsa._documentos.al_abrir["C.par"] = {"modo_exportacion": "nada"}

    r, sobre = cli("export", str(tmp_path / "*.par"), "--format", "step")

    assert r.exit_code == 1
    assert sobre["ok"] is False and sobre["data"] is None
    assert sobre["error"]["code"] == "lote_con_fallos"
    assert "Fallaron 2 de 4" in sobre["error"]["message"]
    detalles = sobre["error"]["details"]
    assert detalles["resumen"] == {"total": 4, "ok": 2, "fallidos": 2}
    por_nombre = {x["entrada"].rsplit("\\", 1)[-1]: x for x in detalles["resultados"]}
    assert por_nombre["A.par"]["ok"] and por_nombre["D.par"]["ok"]
    assert por_nombre["B.par"]["ok"] is False
    assert por_nombre["B.par"]["error"]["message"] == "No abre"
    assert por_nombre["C.par"]["error"]["code"] == "com_error"
    assert "bytes" not in por_nombre["B.par"]
    assert (tmp_path / "D.stp").exists() and not (tmp_path / "C.stp").exists()
    # C se abrió: se cierra igual aunque su exportación falló. B nunca se abrió.
    cerrados = [c[1] for c in _llamadas(app_falsa, "Close")]
    assert sorted(cerrados) == ["A.par", "C.par", "D.par"]


def test_salida_existente_sin_overwrite_falla_solo_ese_archivo(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par", "B.par")
    (tmp_path / "A.stp").write_bytes(b"viejo")

    r, sobre = cli("export", str(tmp_path / "*.par"), "--format", "step")

    assert r.exit_code == 1
    resultados = sobre["error"]["details"]["resultados"]
    assert resultados[0]["ok"] is False and resultados[0]["error"]["code"] == "solo_lectura"
    assert resultados[1]["ok"] is True
    assert (tmp_path / "A.stp").read_bytes() == b"viejo"
    assert len(_llamadas(app_falsa, "Documents.Open")) == 1  # solo B

    r, sobre = cli("export", str(tmp_path / "*.par"), "--format", "step", "--overwrite")
    assert r.exit_code == 0
    assert (tmp_path / "A.stp").read_bytes() == b"exportado"


def test_documento_ya_abierto_no_se_cierra_y_los_del_lote_si(cli, app_falsa, tmp_path):
    rutas = _tocar(tmp_path, "A.par", "B.par")
    abierto = app_falsa.agregar_documento("A.par", ruta=rutas[0], tipo=1, sucio=True)

    r, sobre = cli("export", str(tmp_path / "*.par"), "--format", "step")

    assert r.exit_code == 0, r.output
    assert abierto.cerrado is False and abierto.Dirty is True
    # Solo se abrió y se cerró B, sin guardar.
    assert [c[1] for c in _llamadas(app_falsa, "Documents.Open")] == [rutas[1]]
    assert _llamadas(app_falsa, "Close") == [("Close", "B.par", False)]
    assert _llamadas(app_falsa, "Save") == [] and _llamadas(app_falsa, "SaveAs") == []
    assert [c[1] for c in _llamadas(app_falsa, "SaveCopyAs")] == ["A.par", "B.par"]


def test_documento_activo_se_restaura(cli, app_falsa, tmp_path):
    rutas = _tocar(tmp_path, "A.par")
    z = app_falsa.agregar_documento("Z.par", ruta=str(tmp_path / "Z.par"), tipo=1)
    app_falsa.agregar_documento("Y.par", ruta=str(tmp_path / "Y.par"), tipo=1)
    app_falsa._documentos.activo = z  # sin la restauración quedaría activo Y, el último

    r, _ = cli("export", rutas[0], "--format", "step")

    assert r.exit_code == 0
    assert app_falsa.ActiveDocument.Name == "Z.par"
    assert ("Activate", "Z.par") in app_falsa.registro


def test_out_carpeta_se_crea(cli, app_falsa, tmp_path):
    rutas = _tocar(tmp_path / "src", "A.par", "B.psm")
    destino = tmp_path / "nueva" / "salida"

    r, sobre = cli("export", *rutas, "--format", "x_t", "--out", str(destino))

    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in destino.iterdir()) == ["A.x_t", "B.x_t"]
    assert sobre["data"]["salida"] == str(destino)


def test_out_archivo_en_lote_da_exit_2(cli, app_falsa, tmp_path):
    rutas = _tocar(tmp_path, "A.par")
    r, _ = cli("export", *rutas, "--format", "step", "--out", str(tmp_path / "x.stp"))
    assert r.exit_code == 2 and app_falsa.registro == []


def test_tipo_real_incompatible_falla_ese_archivo(cli, app_falsa, tmp_path):
    rutas = _tocar(tmp_path, "A.par")
    abierto = app_falsa.agregar_documento("A.par", ruta=rutas[0], tipo=2)  # no es una pieza

    r, sobre = cli("export", *rutas, "--format", "step")

    assert r.exit_code == 1
    assert sobre["error"]["details"]["resultados"][0]["error"]["code"] == "argumento_invalido"
    assert abierto.cerrado is False and _llamadas(app_falsa, "SaveCopyAs") == []


def test_readonly_y_dry_run_no_tocan_nada(cli, app_falsa, tmp_path):
    rutas = _tocar(tmp_path, "A.par", "B.par")
    destino = tmp_path / "out"

    r, sobre = cli.con("--readonly", "export", *rutas, "--format", "step")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con(
        "--dry-run", "export", str(tmp_path / "*.par"), "--format", "step", "--out", str(destino)
    )
    assert r.exit_code == 0
    assert sobre["data"] == {
        "dry_run": True,
        "accion": "export",
        "formato": "step",
        "entradas": [
            {"entrada": rutas[0], "salida": str(destino / "A.stp")},
            {"entrada": rutas[1], "salida": str(destino / "B.stp")},
        ],
        "overwrite": False,
    }
    assert app_falsa.registro == []
    assert not destino.exists() and sorted(p.name for p in tmp_path.iterdir()) == ["A.par", "B.par"]


def test_display_alerts_se_restaura_en_lote(cli, app_falsa, tmp_path):
    _tocar(tmp_path, "A.par")
    app_falsa._documentos.al_abrir["A.par"] = {"modo_exportacion": "nada"}
    cli("export", str(tmp_path / "*.par"), "--format", "step")
    assert app_falsa.historial_alertas == [False, True]


def test_sin_instancia_en_lote_da_exit_3(cli_sin_instancia, tmp_path):
    rutas = _tocar(tmp_path, "A.par")
    r, sobre = cli_sin_instancia("export", *rutas, "--format", "step")
    assert r.exit_code == 3 and sobre["error"]["code"] == "no_conectado"


@pytest.mark.parametrize("formato", ["png"])
def test_png_en_lote_activa_cada_documento(cli, app_falsa, tmp_path, formato):
    rutas = _tocar(tmp_path, "A.par", "D.dft")
    r, sobre = cli("export", str(tmp_path), "--format", formato)
    assert r.exit_code == 0, r.output
    assert sobre["data"]["resumen"]["ok"] == 2
    assert [c[1] for c in _llamadas(app_falsa, "View.SaveAsImage")] == ["A.par", "D.dft"]
    assert rutas


def test_timeout_en_un_item_corta_el_lote_y_deja_el_resto_sin_intentar(
    cli, app_falsa, sta, monkeypatch, tmp_path
):
    from com_falso import BloqueoFalso

    _tocar(tmp_path, "A.par", "B.par", "C.par")
    bloqueo = BloqueoFalso()
    bloqueo.bloquear("SaveCopyAs")
    app_falsa._documentos.al_abrir["B.par"] = {"bloqueo": bloqueo}
    monkeypatch.setattr(sta, "_cancelar", lambda _: bloqueo.cancelar())

    r, sobre = cli("--timeout", "0.3", "export", str(tmp_path / "*.par"), "--format", "step")

    assert r.exit_code == 7 and sobre["error"]["code"] == "ocupado"
    detalles = sobre["error"]["details"]
    assert detalles["motivo"] == "timeout" and detalles["cancelacion"] == "cancelada"
    por_nombre = {x["entrada"].rsplit("\\", 1)[-1]: x for x in detalles["resultados"]}
    assert por_nombre["A.par"]["ok"] is True
    assert por_nombre["B.par"]["ok"] is False
    assert por_nombre["B.par"]["error"]["code"] == "ocupado"
    assert por_nombre["C.par"]["ok"] is False
    assert por_nombre["C.par"]["error"]["message"] == (
        "No se intentó: Solid Edge no respondió a tiempo."
    )
    assert _llamadas(app_falsa, "SaveCopyAs")[-1][1] == "B.par"
    assert all(c[1] != "C.par" for c in app_falsa.registro if len(c) > 1)
