"""`se run`: ejecutar un script del usuario con la `Application` (solo con `--allow-scripts`).

El script define `main(app, args)`. Se carga por ruta y `main` corre dentro del hilo STA, con la
`Application` de late binding; lo que devuelve (datos planos) va en `data.resultado`. El script
corre con los permisos del usuario y puede hacer cualquier cosa: por eso el flag explícito.
"""

from __future__ import annotations

import importlib.util
import os
import traceback
from typing import Any

from se_cli.core import documentos
from se_cli.core.errors import ArgumentoInvalido, DocNoEncontrado, SeError, SoloLectura
from se_cli.core.result import a_serializable

MAX_LINEAS_TRACEBACK = 12


def planificar(archivo: str, args: list[str], permitido: bool) -> dict[str, Any]:
    """Sin el flag siempre falla (exit 6) sin mirar el archivo; con él, tiene que existir."""
    if not permitido:
        raise SoloLectura(
            "`se run` ejecuta código arbitrario con tus permisos y está bloqueado: "
            "repetí con --allow-scripts si confiás en el script.",
            details={"flag": "--allow-scripts"},
        )
    ruta = documentos.ruta_absoluta(archivo)
    if not os.path.isfile(ruta):
        raise DocNoEncontrado(f"No existe el script: {ruta}", details={"ruta": ruta})
    return {"accion": "run", "script": ruta, "args": list(args)}


def _resumir(error: BaseException) -> str:
    lineas = traceback.format_exception(error)
    texto = "".join(lineas).strip().splitlines()
    if len(texto) > MAX_LINEAS_TRACEBACK:
        texto = [*texto[:2], "...", *texto[-(MAX_LINEAS_TRACEBACK - 3) :]]
    return "\n".join(texto)


def _cargar(ruta: str) -> Any:
    especificacion = importlib.util.spec_from_file_location("se_script_usuario", ruta)
    if especificacion is None or especificacion.loader is None:
        raise ArgumentoInvalido(f"No se puede cargar como módulo de Python: {ruta}")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def ejecutar(app: Any, archivo: str, args: list[str]) -> dict[str, Any]:
    """Cargá el script y corré `main(app, args)`. Va dentro del hilo STA (vía `Sesion.llamar`).

    Una excepción del script es exit 1 con el traceback resumido en `error.details`. Un script sin
    `main` es exit 2.
    """
    ruta = documentos.ruta_absoluta(archivo)
    try:
        modulo = _cargar(ruta)
    except SeError:
        raise
    except BaseException as error:
        raise SeError(
            f"El script falló al cargarse: {type(error).__name__}: {error}",
            details={"script": ruta, "traceback": _resumir(error)},
        ) from error
    principal = getattr(modulo, "main", None)
    if not callable(principal):
        raise ArgumentoInvalido("El script no define main(app, args).", details={"script": ruta})
    try:
        resultado = principal(app, list(args))
    except SeError:
        raise
    except Exception as error:
        raise SeError(
            f"El script falló: {type(error).__name__}: {error}",
            details={"script": ruta, "traceback": _resumir(error)},
        ) from error
    return {"script": ruta, "resultado": a_serializable(resultado)}


__all__ = ["ejecutar", "planificar"]
