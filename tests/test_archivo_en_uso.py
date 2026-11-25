"""Reemplazar (`--overwrite`) un archivo que otro programa tiene abierto da exit 6, no `interno`.

En Windows un archivo abierto por Python no se puede renombrar (WinError 32), igual que uno
abierto por Solid Edge (verificado en vivo con `docs save-as --overwrite`).
"""

import sys
from contextlib import contextmanager

import pytest

from se_cli.core import documentos

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="bloqueo de archivos de Windows")


@contextmanager
def _bloqueado(ruta):
    with open(ruta, "rb"):
        yield


def _baks(carpeta):
    return [p.name for p in carpeta.iterdir() if ".bak" in p.name]


def _escrituras(app, que):
    return [c for c in app.registro if c[0] == que]


def _en_uso(sobre, ruta):
    assert sobre["ok"] is False and sobre["error"]["code"] == "solo_lectura", sobre
    detalles = sobre["error"]["details"]
    assert detalles["ruta"] == str(ruta)
    assert detalles["motivo"] == "archivo_en_uso"
    assert detalles["winerror"] == 32
    assert detalles["original_intacto"] is True
    assert "se docs close" in detalles["hint"]
    assert "en uso" in sobre["error"]["message"]


def test_save_as_overwrite_sobre_archivo_bloqueado(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("A.par", ruta=str(tmp_path / "A.par"))
    destino = tmp_path / "B.par"
    destino.write_bytes(b"original")

    with _bloqueado(destino):
        r, sobre = cli("docs", "save-as", str(destino), "--overwrite")

    assert r.exit_code == 6
    _en_uso(sobre, destino)
    assert destino.read_bytes() == b"original"
    assert _baks(tmp_path) == []
    assert _escrituras(app_falsa, "SaveAs") == []


def test_save_as_sobre_otro_documento_abierto_en_solid_edge(cli, app_falsa, tmp_path):
    destino = tmp_path / "B.par"
    destino.write_bytes(b"original")
    app_falsa.agregar_documento("B.par", ruta=str(destino))
    app_falsa.agregar_documento("A.par", ruta=str(tmp_path / "A.par"))  # activo

    r, sobre = cli("docs", "save-as", str(destino), "--overwrite")

    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    detalles = sobre["error"]["details"]
    assert detalles["abierto_en_solid_edge"] == {"indice": 1, "nombre": "B.par"}
    assert detalles["motivo"] == "archivo_en_uso" and detalles["original_intacto"] is True
    assert "se docs close B.par" in detalles["hint"]
    assert destino.read_bytes() == b"original"
    assert _baks(tmp_path) == [] and app_falsa.escrituras == []


def test_save_as_sobre_si_mismo_sigue_guardando(cli, app_falsa, tmp_path):
    propia = tmp_path / "A.par"
    propia.write_bytes(b"x")
    app_falsa.agregar_documento("A.par", ruta=str(propia))

    r, _ = cli("docs", "save-as", str(propia), "--overwrite")

    assert r.exit_code == 0
    assert _escrituras(app_falsa, "Save") == [("Save", "A.par")]


def test_export_overwrite_sobre_archivo_bloqueado(cli, app_falsa, tmp_path):
    app_falsa.agregar_documento("Pieza.par", ruta=str(tmp_path / "Pieza.par"))
    salida = tmp_path / "Pieza.stp"
    salida.write_bytes(b"viejo")

    with _bloqueado(salida):
        r, sobre = cli("export", "--format", "step", "--overwrite")

    assert r.exit_code == 6
    _en_uso(sobre, salida)
    assert salida.read_bytes() == b"viejo" and _baks(tmp_path) == []
    assert _escrituras(app_falsa, "SaveCopyAs") == []


def test_lote_con_salida_bloqueada_marca_ese_archivo(cli, app_falsa, tmp_path):
    for nombre in ("A.par", "B.par"):
        (tmp_path / nombre).write_bytes(b"pieza")
    salida = tmp_path / "out"
    salida.mkdir()
    (salida / "A.stp").write_bytes(b"viejo")

    with _bloqueado(salida / "A.stp"):
        r, sobre = cli(
            "export",
            str(tmp_path / "*.par"),
            "--format",
            "step",
            "--out",
            str(salida),
            "--overwrite",
        )

    assert r.exit_code == 1 and sobre["error"]["code"] == "lote_con_fallos"
    a, b = sobre["error"]["details"]["resultados"]
    assert a["ok"] is False and a["error"]["code"] == "solo_lectura"
    assert a["error"]["details"]["motivo"] == "archivo_en_uso"
    assert b["ok"] is True
    assert (salida / "A.stp").read_bytes() == b"viejo" and _baks(salida) == []


def test_draft_overwrite_sobre_dft_bloqueado(cli, app_falsa, tmp_path):
    modelo = tmp_path / "Pieza.par"
    modelo.write_bytes(b"pieza")
    dft = tmp_path / "Pieza.dft"
    dft.write_bytes(b"plano viejo")

    with _bloqueado(dft):
        r, sobre = cli("draft", "from-part", str(modelo), "--scale", "1:1", "--overwrite")

    assert r.exit_code == 6
    _en_uso(sobre, dft)
    assert dft.read_bytes() == b"plano viejo" and _baks(tmp_path) == []
    assert app_falsa.Documents.Count == 0  # el Draft a medio armar se descartó


def test_acceso_denegado_tambien_es_exit_6(monkeypatch, tmp_path):
    ruta = tmp_path / "X.stp"
    ruta.write_bytes(b"x")

    def negar(origen, destino):
        raise PermissionError(13, "Acceso denegado", origen, 5)

    monkeypatch.setattr(documentos.os, "replace", negar)
    with pytest.raises(documentos.SoloLectura) as error:
        documentos.apartar(str(ruta))
    assert error.value.details["motivo"] == "acceso_denegado"
    assert error.value.details["winerror"] == 5
    assert error.value.exit_code == 6
