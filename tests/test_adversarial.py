import asyncio
from dataclasses import replace

import pytest
from com_falso import com_error
from mcp.server.fastmcp.exceptions import ToolError

from se_cli import ejecucion, mcp_server
from se_cli.core import documentos, exportar, lote
from se_cli.core.errors import ArgumentoInvalido, SoloLectura


@pytest.mark.parametrize("distancia", ["1e999mm", "NaN", "inf", "-1mm", "2kg", "1,5mm"])
def test_extrusion_rechaza_distancia_invalida(cli, fabrica, distancia):
    respuesta, sobre = cli("extrude", f"--distance={distancia}")
    assert respuesta.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert fabrica.llamadas == 0


@pytest.mark.parametrize(
    "contenido",
    ["[" * 1500 + "]" * 1500, '{"version":' + "9" * 4500 + "}", '{"version":1,"entities":[]}'],
)
def test_perfil_invalido_devuelve_error_de_uso(cli, fabrica, tmp_path, contenido):
    archivo = tmp_path / "perfil.json"
    archivo.write_text(contenido, encoding="utf-8")
    respuesta, sobre = cli("sketch", "profile", str(archivo))
    assert respuesta.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert fabrica.llamadas == 0


@pytest.mark.parametrize("nombre", ["CON.par", "NUL.txt", "x" * 256 + ".par"])
def test_destino_windows_invalido(cli, fabrica, tmp_path, nombre):
    respuesta, sobre = cli("docs", "save-as", str(tmp_path / nombre))
    assert respuesta.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert fabrica.llamadas == 0


def test_guardar_como_revalida_destino_tras_resolver(monkeypatch, app_falsa, tmp_path):
    doc = app_falsa.agregar_documento("Pieza.par")
    ruta = tmp_path / "Ñandú.par"

    def resolver(*_):
        ruta.write_bytes(b"original")
        return 1, doc

    monkeypatch.setattr(documentos, "resolver", resolver)
    with pytest.raises(SoloLectura):
        documentos.guardar_como(app_falsa, str(ruta))
    assert ruta.read_bytes() == b"original"


def test_exportar_restaura_original_si_com_falla_despues_de_escribir(app_falsa, tmp_path):
    doc = app_falsa.agregar_documento("Pieza.par")
    ruta = tmp_path / "salida.stp"
    ruta.write_bytes(b"original")

    def exportar_parcial(*_):
        ruta.write_bytes(b"parcial")
        raise com_error(0x80010108, "Desconectado")

    formato = replace(exportar.formato_de("step"), exportar=exportar_parcial)
    with pytest.raises(Exception, match="Desconectado"):
        exportar.escribir(doc, formato, str(ruta), True)
    assert ruta.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [ruta]


def test_error_al_renderizar_sigue_siendo_json(cli, monkeypatch):
    def emitir(*_, **__):
        raise RuntimeError("falló el render")

    monkeypatch.setattr(ejecucion.salida, "emitir_ok", emitir)
    respuesta, sobre = cli("status")
    assert respuesta.exit_code == 1
    assert sobre["error"]["code"] == "interno"
    assert respuesta.stderr == ""


@pytest.mark.parametrize(
    ("nombre", "argumentos"),
    [("status", {"extra": True}), ("asm_tree", {"depth": "3"}), ("inexistente", {})],
)
def test_mcp_rechaza_argumentos_fuera_de_esquema(nombre, argumentos, monkeypatch):
    def inesperada():
        pytest.fail("Los argumentos inválidos no deben llegar a COM")

    monkeypatch.setattr(mcp_server, "Sesion", inesperada)
    with pytest.raises(ToolError, match="Herramienta desconocida|Argumentos inválidos"):
        asyncio.run(mcp_server.mcp.call_tool(nombre, argumentos))


def test_mcp_oculta_rutas_de_excepciones(monkeypatch):
    def fallar():
        raise RuntimeError(r"C:\privado\Pieza.par")

    monkeypatch.setattr(mcp_server, "Sesion", fallar)
    sobre = mcp_server.status()
    assert sobre["error"]["code"] == "interno"
    assert "privado" not in str(sobre)


@pytest.mark.parametrize(
    "ruta",
    [
        r"C:\proyectos\.venv\Pieza.par",
        r"C:\proyectos\v1.2\Ñandú ñ.par",
        r"\\servidor\recurso\carpeta\Pieza.par",
        r"\\?\C:\proyectos\Pieza.par",
        r"\\?\UNC\servidor\recurso\Pieza.par",
        r"D:\Pieza.par",
        r"..\x.par",
        r"sub\..\x.par",
        r"C:\tmp\..\x.par",
        r"..\..\x.par",
        r".\x.par",
        "../x.par",
        "sub/../x.par",
    ],
)
def test_nombres_windows_aceptan_rutas_legitimas(ruta):
    documentos.validar_nombres_windows(ruta)


@pytest.mark.parametrize(
    "ruta",
    [
        "NUL",
        r"x\NUL",
        r"\\.\COM1",
        r"C:\x\CON\a.par",
        r"C:\x\a.par.",
        r"C:\x\a b .par ",
        r"C:\x\a?.par",
        r"C:\x\a.par:s",
        r"..\CON.par",
        r"..\NUL",
        r"sub\...\x.par",
        r"..\x.",
    ],
)
def test_nombres_windows_rechazan_nombres_invalidos(ruta):
    with pytest.raises(ArgumentoInvalido):
        documentos.validar_nombres_windows(ruta)


@pytest.mark.parametrize("destino", [r"..\Nueva.par", "../Nueva.par", r"..\sub\..\Nueva.par"])
def test_save_as_acepta_destino_relativo_con_puntos(cli, app_falsa, tmp_path, monkeypatch, destino):
    app_falsa.agregar_documento("Part1.par")
    (tmp_path / "sub").mkdir()
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()
    monkeypatch.chdir(trabajo)
    respuesta, _ = cli("docs", "save-as", destino)
    assert respuesta.exit_code == 0
    assert (tmp_path / "Nueva.par").exists()


@pytest.mark.parametrize("destino", [r"..\CON.par", r"..\NUL", r"sub\...\x.par"])
def test_save_as_rechaza_destino_relativo_invalido(cli, fabrica, destino):
    respuesta, sobre = cli("docs", "save-as", destino)
    assert respuesta.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert fabrica.llamadas == 0


def test_lote_acepta_carpeta_de_salida_con_puntos(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lote.planificar([], exportar.formato_de("step"), r"..\salida", False)


def test_lote_rechaza_carpeta_de_salida_reservada(tmp_path):
    with pytest.raises(ArgumentoInvalido):
        lote.planificar([], exportar.formato_de("step"), str(tmp_path / "NUL"), False)


def test_mcp_conserva_mensaje_de_errores_propios(monkeypatch):
    def fallar():
        raise ArgumentoInvalido("Argumento de prueba inválido.", details={"campo": "x"})

    monkeypatch.setattr(mcp_server, "Sesion", fallar)
    error = mcp_server.status()["error"]
    assert error["code"] == "argumento_invalido"
    assert error["message"] == "Argumento de prueba inválido."
    assert error["details"] == {"campo": "x"}


def test_json_errores_de_uso_salen_con_exit_del_sobre(cli):
    respuesta, sobre = cli("docs", "no-existe")
    assert respuesta.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
