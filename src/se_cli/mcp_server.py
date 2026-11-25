"""Servidor MCP de Solid Edge sobre las operaciones del CLI."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from threading import Lock
from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from typing_extensions import TypedDict

from se_cli.core import (
    acceso,
    croquis,
    documentos,
    ensamble,
    exportar,
    fisica,
    modelado,
    operaciones,
    result,
    unidades,
    variables,
)
from se_cli.core.errors import SeError, hresult_de, traducir
from se_cli.core.session import Sesion


class ServidorSe(FastMCP):
    """FastMCP que rechaza argumentos fuera del esquema (claves de más, tipos que no coinciden).

    FastMCP ignora las claves extra y convierte tipos; acá se valida el JSON crudo contra el
    esquema publicado, que declara `additionalProperties: false`.
    """

    async def list_tools(self):
        herramientas = await super().list_tools()
        for herramienta in herramientas:
            herramienta.inputSchema = {**herramienta.inputSchema, "additionalProperties": False}
        return herramientas

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        herramienta = self._tool_manager.get_tool(name)
        if herramienta is None:
            raise ToolError(f"Herramienta desconocida: {name}.")
        esquema = {**herramienta.parameters, "additionalProperties": False}
        error = best_match(Draft202012Validator(esquema).iter_errors(arguments))
        if error is not None:
            raise ToolError(f"Argumentos inválidos: {error.message}")
        return await super().call_tool(name, arguments)


mcp = ServidorSe("Solid Edge")
_candado = Lock()
Doc = Annotated[
    str | None, Field(description="Índice desde 1, nombre o ruta. Por defecto, activo.")
]
Units = Annotated[str | None, Field(description="Unidades de salida, ej. mm,deg. Por defecto, SI.")]


class Sobre(TypedDict):
    ok: bool
    data: Any
    error: dict[str, Any] | None


@contextlib.contextmanager
def _respuesta():
    """Traducí errores y serializá los datos igual que el CLI."""
    sobre: Sobre = {"ok": False, "data": None, "error": None}

    def completar(data: Any) -> None:
        sobre.update(result.ok(result.a_serializable(data)))

    try:
        yield sobre, completar
    except Exception as error:
        traducido = traducir(error)
        sobre.update(result.fallo(traducido))
        if not isinstance(error, SeError) and hresult_de(error) is None:
            # Excepción no prevista (`interno`): su texto puede traer rutas u otros datos locales.
            sobre["error"]["message"] = "Solid Edge no pudo completar la operación."
            sobre["error"].pop("details", None)


def _sesion(fn: Callable[[Sesion], Any]) -> Any:
    # La supresión de alertas abarca varias llamadas al STA. Serializá la operación completa.
    with _candado:
        sesion = Sesion()
        try:
            return fn(sesion)
        finally:
            with contextlib.suppress(Exception):
                sesion.cerrar()


def _llamar(fn: Callable[[Any], Any], *, sin_alertas: bool = False) -> Any:
    def correr(sesion: Sesion) -> Any:
        sesion.conectar()
        if sin_alertas:
            with sesion.sin_alertas():
                return sesion.llamar(fn, reintentar_todo=False)
        return sesion.llamar(fn)

    return _sesion(correr)


@mcp.tool()
def status() -> Sobre:
    """Consultá si Solid Edge está abierto y qué documento está activo."""
    with _respuesta() as (sobre, completar):
        completar(_sesion(lambda sesion: sesion.estado()))
    return sobre


@mcp.tool()
def connect() -> Sobre:
    """Conectate con una instancia de Solid Edge que ya esté abierta."""
    with _respuesta() as (sobre, completar):
        completar(_sesion(lambda sesion: sesion.conectar()))
    return sobre


@mcp.tool()
def docs_list() -> Sobre:
    """Listá los documentos abiertos con sus índices, tipos y rutas."""
    with _respuesta() as (sobre, completar):
        lista = _llamar(documentos.listar)
        completar({"cantidad": len(lista), "documentos": lista})
    return sobre


@mcp.tool()
def docs_open(path: str) -> Sobre:
    """Abrí un documento CAD desde una ruta local absoluta o activalo si ya está abierto."""
    with _respuesta() as (sobre, completar):
        ruta = documentos.validar_ruta_existente(path)
        completar(_llamar(lambda app: documentos.abrir(app, ruta), sin_alertas=True))
    return sobre


@mcp.tool()
def docs_save(doc: Doc = None) -> Sobre:
    """Guardá los cambios del documento en su ruta actual."""
    with _respuesta() as (sobre, completar):
        completar(_llamar(lambda app: documentos.guardar(app, doc), sin_alertas=True))
    return sobre


@mcp.tool()
def vars_get(name: str, units: Units = None, doc: Doc = None) -> Sobre:
    """Leé una variable o cota por nombre."""
    with _respuesta() as (sobre, completar):
        elegidas = unidades.parsear_unidades(units)
        completar(
            _llamar(lambda app: variables.obtener(acceso.documento(app, doc), name, elegidas))
        )
    return sobre


@mcp.tool()
def vars_set(
    name: str,
    value: str | None = None,
    formula: str | None = None,
    units: Units = None,
    doc: Doc = None,
) -> Sobre:
    """Cambiá una variable. Indicá un valor como 120mm o una fórmula como Ancho*2."""
    with _respuesta() as (sobre, completar):
        elegidas = unidades.parsear_unidades(units)
        orden = variables.preparar_set(value, formula)
        completar(
            _llamar(
                lambda app: variables.modificar(
                    acceso.documento(app, doc), name, orden, force=False, elegidas=elegidas
                ),
                sin_alertas=True,
            )
        )
    return sobre


@mcp.tool()
def mass(density: float | None = None, units: Units = None, doc: Doc = None) -> Sobre:
    """Leé masa, volumen e inercia. Si indicás densidad en kg/m³, recalculá y modificá el modelo."""
    with _respuesta() as (sobre, completar):
        elegidas = unidades.parsear_unidades(units)
        valor = fisica.validar_densidad(density)
        completar(
            _llamar(
                lambda app: fisica.propiedades(
                    acceso.documento(app, doc), valor, elegidas, app=app
                ),
                sin_alertas=valor is not None,
            )
        )
    return sobre


@mcp.tool()
def export(
    format: Literal["step", "stl", "pdf", "dxf"],
    out: str | None = None,
    overwrite: bool = False,
    doc: Doc = None,
) -> Sobre:
    """Exportá un modelo a STEP/STL o un plano a PDF/DXF. Usá una ruta absoluta para out."""
    with _respuesta() as (sobre, completar):
        formato = exportar.formato_de(format)
        completar(
            _llamar(
                lambda app: exportar.exportar_individual(app, doc, formato, out, overwrite),
                sin_alertas=True,
            )
        )
    return sobre


@mcp.tool()
def features_list(doc: Doc = None) -> Sobre:
    """Listá las operaciones de modelado de una pieza o chapa."""
    with _respuesta() as (sobre, completar):
        completar(_llamar(lambda app: operaciones.listar(acceso.documento(app, doc))))
    return sobre


@mcp.tool()
def sketch_profile(profile: dict[str, Any], doc: Doc = None) -> Sobre:
    """Creá un perfil cerrado. Enviá el objeto v1 de se sketch profile con plano y entidades."""
    with _respuesta() as (sobre, completar):
        perfil = croquis.validar_perfil(profile)
        completar(
            _llamar(
                lambda app: modelado.crear_perfil(acceso.documento(app, doc), perfil),
                sin_alertas=True,
            )
        )
    return sobre


@mcp.tool()
def extrude(
    distance: str,
    profile: str | None = None,
    direction: Literal["normal", "reverse", "symmetric"] = "normal",
    cut: bool = False,
    doc: Doc = None,
) -> Sobre:
    """Extruí un perfil por una distancia como 10mm. Sin perfil, usá el último."""
    with _respuesta() as (sobre, completar):
        modelado.planificar_extrusion(distance, profile, direction, cut)
        completar(
            _llamar(
                lambda app: modelado.extruir(
                    acceso.documento(app, doc), distance, profile, direction, cut
                ),
                sin_alertas=True,
            )
        )
    return sobre


@mcp.tool()
def asm_add(
    path: str,
    at: str | None = None,
    rot: str | None = None,
    units: Units = None,
    doc: Doc = None,
) -> Sobre:
    """Insertá una .par, .psm o .asm. Indicá posición X,Y,Z y rotación RX,RY,RZ si hace falta."""
    with _respuesta() as (sobre, completar):
        elegidas = unidades.parsear_unidades(units)
        ensamble.planificar_add(path, at, rot)
        completar(
            _llamar(
                lambda app: ensamble.agregar(acceso.documento(app, doc), path, at, rot, elegidas),
                sin_alertas=True,
            )
        )
    return sobre


@mcp.tool()
def asm_tree(
    depth: int = ensamble.PROFUNDIDAD_POR_DEFECTO, flat: bool = False, doc: Doc = None
) -> Sobre:
    """Listá las ocurrencias de un ensamble. Con flat, devolvé la lista de materiales."""
    with _respuesta() as (sobre, completar):
        ensamble.validar_profundidad(depth)
        completar(_llamar(lambda app: ensamble.arbol(acceso.documento(app, doc), depth, flat)))
    return sobre


def main() -> None:
    """Arrancá el servidor MCP por stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
