"""`se docs save|save-as|close` sobre el COM falso."""

import pytest
from com_falso import com_error, ruta_de_largo


def nombres(llamadas):
    return [llamada[0] for llamada in llamadas]


# --- save ---------------------------------------------------------------------------------


def test_save_del_activo(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)

    r, sobre = cli("docs", "save")

    assert r.exit_code == 0
    assert sobre["data"]["guardado"] is True
    assert sobre["data"]["modificado"] is False
    assert sobre["data"]["nombre"] == "A.par"
    assert app_falsa.escrituras == [("Save", "A.par")]


def test_save_por_selector(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)
    app_falsa.agregar_documento("B.par", ruta="C:\\p\\B.par", sucio=True)

    r, _ = cli("docs", "save", "1")

    assert r.exit_code == 0
    assert app_falsa.escrituras == [("Save", "A.par")]


def test_save_de_documento_sin_ruta_pide_save_as(cli, app_falsa):
    app_falsa.agregar_documento("Part1.par", sucio=True)

    r, sobre = cli("docs", "save")

    assert r.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert "save-as" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_save_de_documento_solo_lectura(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", solo_lectura=True)
    r, sobre = cli("docs", "save")
    assert r.exit_code == 6
    assert app_falsa.escrituras == []


def test_save_sin_documentos_da_exit_5(cli):
    r, _ = cli("docs", "save")
    assert r.exit_code == 5


def test_save_sin_instancia(cli_sin_instancia):
    r, _ = cli_sin_instancia("docs", "save")
    assert r.exit_code == 3


def test_display_alerts_se_restaura_tras_guardar(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)

    cli("docs", "save")

    assert app_falsa.historial_alertas == [False, True]
    assert app_falsa._alertas is True


def test_display_alerts_se_restaura_si_guardar_falla(cli, app_falsa):
    doc = app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)
    doc.fallar("Save", com_error(0x80020009, "Excepción", "Disco lleno"))

    r, sobre = cli("docs", "save")

    assert r.exit_code == 4
    assert sobre["error"]["code"] == "com_error"
    assert sobre["error"]["message"] == "Disco lleno"
    assert app_falsa.historial_alertas == [False, True]
    assert app_falsa._alertas is True


# --- save-as ------------------------------------------------------------------------------


def test_save_as_destino_nuevo(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("Part1.par")
    destino = tmp_path / "Nueva.par"

    r, sobre = cli("docs", "save-as", str(destino))

    assert r.exit_code == 0
    assert destino.exists()
    assert sobre["data"]["destino"] == str(destino)
    assert sobre["data"]["nombre"] == "Nueva.par"
    assert sobre["data"]["ruta"] == str(destino)
    assert sobre["data"]["existe"] is True
    assert app_falsa.escrituras == [("SaveAs", "Part1.par", str(destino))]
    assert app_falsa._alertas is True


def test_save_as_con_selector(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    app_falsa.agregar_documento("B.par", ruta="C:\\p\\B.par")
    destino = tmp_path / "C.par"

    r, _ = cli("docs", "save-as", str(destino), "A.par")

    assert r.exit_code == 0
    assert app_falsa.escrituras[0][:2] == ("SaveAs", "A.par")


def test_save_as_no_pisa_un_archivo_existente(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    destino = tmp_path / "Existe.par"
    destino.write_bytes(b"original")

    r, sobre = cli("docs", "save-as", str(destino))

    assert r.exit_code == 6
    assert sobre["error"]["code"] == "solo_lectura"
    assert "--overwrite" in sobre["error"]["message"]
    assert destino.read_bytes() == b"original"
    assert app_falsa.escrituras == []


def test_save_as_con_overwrite_reemplaza_sin_dejar_restos(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    destino = tmp_path / "Existe.par"
    destino.write_bytes(b"original")

    r, sobre = cli("docs", "save-as", str(destino), "--overwrite")

    assert r.exit_code == 0
    assert destino.read_bytes() == b"falso"
    assert [p.name for p in tmp_path.iterdir()] == ["Existe.par"]


def test_save_as_con_overwrite_restaura_el_original_si_falla(cli, app_falsa, tmp_path):
    doc = app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    doc.fallar("SaveAs", com_error(0x80020009, "Excepción", "Sin permisos"))
    destino = tmp_path / "Existe.par"
    destino.write_bytes(b"original")

    r, _ = cli("docs", "save-as", str(destino), "--overwrite")

    assert r.exit_code == 4
    assert destino.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["Existe.par"]
    assert app_falsa._alertas is True


def test_save_as_en_carpeta_inexistente(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    r, sobre = cli("docs", "save-as", str(tmp_path / "no" / "X.par"))
    assert r.exit_code == 2
    assert app_falsa.escrituras == []


def test_save_as_sobre_su_propia_ruta_con_overwrite_guarda_en_el_lugar(cli, app_falsa, tmp_path):
    propia = tmp_path / "A.par"
    propia.write_bytes(b"original")
    app_falsa.agregar_documento("A.par", ruta=str(propia), sucio=True)

    r, _ = cli("docs", "save-as", str(propia), "--overwrite")

    assert r.exit_code == 0
    assert app_falsa.escrituras == [("Save", "A.par")]
    assert propia.read_bytes() == b"original"


# --- close --------------------------------------------------------------------------------


@pytest.fixture
def sucio(app_falsa):
    return app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)


def test_close_de_documento_limpio(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")

    r, sobre = cli("docs", "close")

    assert r.exit_code == 0
    assert sobre["data"] == {
        "cerrado": True,
        "documento": "A.par",
        "guardado": False,
        "descartado": False,
    }
    assert app_falsa.escrituras == [("Close", "A.par", False)]


def test_close_sucio_sin_flags_se_niega_y_no_cierra(cli, app_falsa, sucio):
    r, sobre = cli("docs", "close")

    assert r.exit_code == 6
    assert sobre["error"]["code"] == "solo_lectura"
    assert "--save" in sobre["error"]["message"]
    assert app_falsa.escrituras == []
    assert sucio.cerrado is False


def test_close_con_save_guarda_y_cierra(cli, app_falsa, sucio):
    r, sobre = cli("docs", "close", "--save")

    assert r.exit_code == 0
    assert sobre["data"]["guardado"] is True
    assert nombres(app_falsa.escrituras) == ["Save", "Close"]
    assert sucio.cerrado is True


def test_close_con_discard_no_guarda(cli, app_falsa, sucio):
    r, sobre = cli("docs", "close", "--discard")

    assert r.exit_code == 0
    assert sobre["data"]["descartado"] is True
    assert "Save" not in nombres(app_falsa.escrituras)
    assert nombres(app_falsa.escrituras) == ["Dirty=", "Close"]
    assert app_falsa.escrituras[-1] == ("Close", "A.par", False)


def test_close_save_y_discard_son_excluyentes(cli, app_falsa, sucio):
    r, _ = cli("docs", "close", "--save", "--discard")
    assert r.exit_code == 2
    assert app_falsa.escrituras == []


def test_close_save_de_documento_sin_ruta_pide_save_as(cli, app_falsa):
    app_falsa.agregar_documento("Part1.par", sucio=True)

    r, sobre = cli("docs", "close", "--save")

    assert r.exit_code == 2
    assert "save-as" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_close_por_selector(cli, app_falsa):
    a = app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    b = app_falsa.agregar_documento("B.par", ruta="C:\\p\\B.par")

    r, _ = cli("docs", "close", "A.par")

    assert r.exit_code == 0
    assert a.cerrado and not b.cerrado


def test_close_selector_inexistente(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    r, _ = cli("docs", "close", "Z.par")
    assert r.exit_code == 5
    assert app_falsa.escrituras == []


def test_close_all_sin_yes(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")

    r, sobre = cli("docs", "close", "--all")

    assert r.exit_code == 2
    assert "--yes" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_close_all_con_yes_cierra_todo(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    app_falsa.agregar_documento("B.par", ruta="C:\\p\\B.par")

    r, sobre = cli("docs", "close", "--all", "--yes")

    assert r.exit_code == 0
    assert sobre["data"]["cantidad"] == 2
    assert sorted(sobre["data"]["cerrados"]) == ["A.par", "B.par"]
    assert app_falsa._documentos.Count == 0


def test_close_all_con_un_sucio_no_cierra_ninguno(cli, app_falsa, sucio):
    app_falsa.agregar_documento("B.par", ruta="C:\\p\\B.par")

    r, sobre = cli("docs", "close", "--all", "--yes")

    assert r.exit_code == 6
    assert app_falsa.escrituras == []
    assert app_falsa._documentos.Count == 2


def test_close_all_con_discard(cli, app_falsa, sucio):
    app_falsa.agregar_documento("B.par", ruta="C:\\p\\B.par")

    r, _ = cli("docs", "close", "--all", "--yes", "--discard")

    assert r.exit_code == 0
    assert app_falsa._documentos.Count == 0


def test_close_all_no_se_combina_con_documento(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    r, _ = cli("docs", "close", "A.par", "--all", "--yes")
    assert r.exit_code == 2


def test_display_alerts_se_restaura_si_cerrar_falla(cli, app_falsa):
    doc = app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    doc.fallar("Close", com_error(0x80020009, "Excepción", "No se pudo cerrar"))

    r, sobre = cli("docs", "close")

    assert r.exit_code == 4
    assert app_falsa.historial_alertas == [False, True]
    assert app_falsa._alertas is True


def test_display_alerts_se_restaura_tras_cerrar(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par")
    cli("docs", "close")
    assert app_falsa.historial_alertas == [False, True]


# --- readonly / dry-run -------------------------------------------------------------------

COMANDOS = [
    ["docs", "save"],
    ["docs", "save-as", "{tmp}/X.par"],
    ["docs", "close"],
    ["docs", "close", "--all", "--yes"],
]


@pytest.mark.parametrize("comando", COMANDOS)
def test_readonly_bloquea_sin_tocar_com(cli, app_falsa, sucio, tmp_path, comando):
    argumentos = [parte.replace("{tmp}", str(tmp_path)) for parte in comando]

    r, sobre = cli("--readonly", *argumentos)

    assert r.exit_code == 6
    assert sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.registro == []
    assert app_falsa.historial_alertas == []
    assert not (tmp_path / "X.par").exists()


@pytest.mark.parametrize("comando", COMANDOS)
def test_dry_run_describe_sin_tocar_com(cli, app_falsa, sucio, tmp_path, comando):
    argumentos = [parte.replace("{tmp}", str(tmp_path)) for parte in comando]

    r, sobre = cli("--dry-run", *argumentos)

    assert r.exit_code == 0
    assert sobre["data"]["dry_run"] is True
    assert sobre["data"]["accion"].startswith("docs.")
    assert app_falsa.registro == []
    assert app_falsa.historial_alertas == []
    assert not (tmp_path / "X.par").exists()


def test_dry_run_de_save_as_valida_el_destino_existente(cli, app_falsa, tmp_path):
    destino = tmp_path / "X.par"
    destino.write_bytes(b"x")
    r, _ = cli("--dry-run", "docs", "save-as", str(destino))
    assert r.exit_code == 6


def test_dry_run_de_close_all_exige_yes(cli):
    r, _ = cli("--dry-run", "docs", "close", "--all")
    assert r.exit_code == 2


def test_modo_humano_de_escritura(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)
    r, _ = cli("docs", "save", como_json=False)
    assert r.exit_code == 0
    assert "A.par" in r.stdout


def test_modo_humano_de_error_va_a_stderr(cli, app_falsa):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)
    r, _ = cli("docs", "close", como_json=False)
    assert r.exit_code == 6
    assert "cambios sin guardar" in r.stderr
    assert r.stdout.strip() == ""


def test_save_as_con_overwrite_y_timeout_conserva_el_apartado(
    cli, app_falsa, sta, monkeypatch, tmp_path
):
    doc = app_falsa.agregar_documento("A.par", ruta="C:\p\A.par")
    doc.bloqueo.bloquear("SaveAs")
    monkeypatch.setattr(sta, "_cancelar", lambda _: doc.bloqueo.cancelar())
    destino = tmp_path / "Existe.par"
    destino.write_bytes(b"original")

    r, sobre = cli("--timeout", "0.3", "docs", "save-as", str(destino), "--overwrite")

    assert r.exit_code == 7 and sobre["error"]["code"] == "ocupado"
    apartado = sobre["error"]["details"]["apartado"]
    with open(apartado, "rb") as archivo:
        assert archivo.read() == b"original"
    assert not destino.exists()
    assert app_falsa._alertas is True


def test_save_as_con_ruta_de_260_caracteres_es_exit_2_sin_tocar_com(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("A.par", ruta="C:\\p\\A.par", sucio=True)
    destino = ruta_de_largo(tmp_path, 260, ".par")
    assert len(str(destino)) == 260

    r, sobre = cli("docs", "save-as", str(destino))

    assert r.exit_code == 2 and sobre["error"]["code"] == "argumento_invalido"
    assert "260" in sobre["error"]["message"]
    assert sobre["error"]["details"]["largo"] == 260
    assert app_falsa.escrituras == []
