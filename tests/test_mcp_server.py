"""Llamadas directas a las herramientas sobre el COM falso, sin transporte."""

import asyncio

import pytest
from com_falso import (
    ColeccionFalsa,
    FabricaApp,
    ModeloFalso,
    VariableFalsa,
    com_error,
    con_armado,
    con_modelado,
)
from mcp.server.fastmcp.exceptions import ToolError

from se_cli import mcp_server as servidor
from se_cli.core.session import Sesion


@pytest.fixture(autouse=True)
def usar_com_falso(monkeypatch, sesion):
    monkeypatch.setattr(servidor, "Sesion", lambda: sesion)


def datos(sobre):
    assert sobre == {"ok": True, "data": sobre["data"], "error": None}, sobre
    return sobre["data"]


def error(sobre, codigo):
    assert sobre == {"ok": False, "data": None, "error": sobre["error"]}
    assert sobre["error"]["code"] == codigo


def test_registro_de_herramientas():
    herramientas = asyncio.run(servidor.mcp.list_tools())
    assert {herramienta.name for herramienta in herramientas} == {
        "status",
        "connect",
        "docs_list",
        "docs_open",
        "docs_save",
        "vars_get",
        "vars_set",
        "mass",
        "export",
        "features_list",
        "sketch_profile",
        "extrude",
        "sheetmetal_tab",
        "asm_add",
        "asm_tree",
    }
    for herramienta in herramientas:
        assert set(herramienta.outputSchema["required"]) == {"ok", "data", "error"}


def test_status_y_connect(app_falsa):
    app_falsa.agregar_documento("Pieza.par")
    assert datos(servidor.status())["conectado"] is True
    assert datos(servidor.connect())["lanzada"] is False


def test_sin_instancia(monkeypatch, sta):
    lanzador = FabricaApp()
    sesion = Sesion(sta=sta, proveedor=FabricaApp(), lanzador=lanzador, sleep=lambda _: None)
    monkeypatch.setattr(servidor, "Sesion", lambda: sesion)

    assert datos(servidor.status())["conectado"] is False
    error(servidor.connect(), "no_conectado")
    assert lanzador.llamadas == 0


def test_documentos(app_falsa, tmp_path):
    ruta = tmp_path / "Pieza.par"
    ruta.touch()
    assert datos(servidor.docs_open(str(ruta)))["ruta"] == str(ruta)
    lista = datos(servidor.docs_list())
    assert lista["cantidad"] == 1
    assert lista["documentos"][0]["nombre"] == ruta.name
    assert datos(servidor.docs_save("1"))["guardado"] is True
    assert ("Save", ruta.name) in app_falsa.escrituras


def test_error_com_restaura_alertas(app_falsa, tmp_path):
    doc = app_falsa.agregar_documento("Pieza.par", ruta=str(tmp_path / "Pieza.par"))
    doc.fallar("Save", com_error(0x80020009, "Excepción", "Disco lleno"))

    error(servidor.docs_save(), "com_error")
    assert app_falsa.historial_alertas == [False, True]


def test_variables(app_falsa):
    doc = app_falsa.agregar_documento("Pieza.par")
    largo = VariableFalsa("Largo", 0.1, unidad=1)
    doc.Variables.agregar(largo)

    assert datos(servidor.vars_get("Largo"))["valor_si"] == pytest.approx(0.1)
    cambio = datos(servidor.vars_set("Largo", "120mm"))
    assert cambio["despues"]["valor_si"] == pytest.approx(0.12)
    assert datos(servidor.vars_get("Largo"))["valor_si"] == pytest.approx(0.12)
    error(servidor.vars_set("Largo", "120mm", formula="Ancho*2"), "argumento_invalido")


def test_masa(app_falsa):
    doc = app_falsa.agregar_documento("Pieza.par")
    doc.Models = ColeccionFalsa([ModeloFalso(doc)])
    masa = datos(servidor.mass(density=2700))
    assert masa["actualizado"] is True
    assert masa["densidad"] == 2700
    assert isinstance(masa["centro_de_masa"], list)


@pytest.mark.parametrize(
    ("formato", "nombre", "tipo", "extension"),
    [
        ("step", "Pieza.par", 1, "stp"),
        ("stl", "Pieza.par", 1, "stl"),
        ("pdf", "Plano.dft", 2, "pdf"),
        ("dxf", "Plano.dft", 2, "dxf"),
    ],
)
def test_exportar(app_falsa, tmp_path, formato, nombre, tipo, extension):
    app_falsa.agregar_documento(nombre, ruta=str(tmp_path / nombre), tipo=tipo)
    ruta = tmp_path / f"salida.{extension}"
    informe = datos(servidor.export(formato, out=str(ruta)))
    assert informe["formato"] == formato
    assert informe["salida"] == str(ruta)
    assert ruta.stat().st_size > 0


def test_perfil_extrusion_y_features(app_falsa):
    con_modelado(app_falsa.agregar_documento("Pieza.par"))
    perfil = datos(
        servidor.sketch_profile(
            {
                "version": 1,
                "units": "mm",
                "entities": [
                    {"id": "p", "type": "polyline", "points": [[0, 0], [20, 0], [20, 10], [0, 0]]}
                ],
            }
        )
    )
    extrusion = datos(servidor.extrude("5mm", profile=str(perfil["perfil"])))
    assert extrusion["modelo_base"] is True
    assert datos(servidor.features_list())["cantidad"] == 1


def test_ensamble(app_falsa, tmp_path):
    pieza = tmp_path / "Pieza.par"
    pieza.touch()
    con_armado(app_falsa.agregar_documento("Conj.asm", tipo=3))

    ocurrencia = datos(servidor.asm_add(str(pieza)))
    arbol = datos(servidor.asm_tree(depth=1))
    assert ocurrencia["indice"] == 1
    assert arbol["arbol"][0]["nombre"] == ocurrencia["nombre"]


def _rectangulo():
    return {
        "version": 1,
        "units": "mm",
        "entities": [
            {
                "id": "r",
                "type": "polyline",
                "points": [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]],
            }
        ],
    }


def test_sheetmetal_tab_crea_la_base(app_falsa):
    con_modelado(app_falsa.agregar_documento("Chapa.psm", tipo=4))
    perfil = datos(servidor.sketch_profile(_rectangulo()))

    tab = datos(servidor.sheetmetal_tab(profile=str(perfil["perfil"]), direction="reverse"))

    assert tab["operacion"] == "tab"
    assert tab["modelo_base"] is True
    assert tab["direccion"] == "reverse"
    assert [c for c in app_falsa.registro if c[0] == "Models.AddBaseTab"] == [
        ("Models.AddBaseTab", 1)
    ]
    assert app_falsa.historial_alertas[-2:] == [False, True]


def test_extrude_en_chapa_sin_base_y_despues_tab(app_falsa):
    con_modelado(app_falsa.agregar_documento("Chapa.psm", tipo=4))
    datos(servidor.sketch_profile(_rectangulo()))

    sobre = servidor.extrude("1mm")
    error(sobre, "no_soportado")
    assert "sheetmetal tab" in sobre["error"]["details"]["hint"]
    assert datos(servidor.sheetmetal_tab())["modelo_base"] is True


def test_sheetmetal_tab_valida_antes_de_com(app_falsa):
    con_modelado(app_falsa.agregar_documento("Pieza.par"))
    error(servidor.sheetmetal_tab(), "argumento_invalido")  # no es chapa
    assert not [c for c in app_falsa.registro if c[0] == "Models.AddBaseTab"]


def test_sheetmetal_tab_rechaza_symmetric_por_esquema(monkeypatch):
    def inesperada():
        pytest.fail("Los argumentos inválidos no deben llegar a COM")

    monkeypatch.setattr(servidor, "Sesion", inesperada)
    with pytest.raises(ToolError, match="Argumentos inválidos"):
        asyncio.run(servidor.mcp.call_tool("sheetmetal_tab", {"direction": "symmetric"}))
