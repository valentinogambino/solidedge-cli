"""Errores del núcleo y códigos de salida estables de `se`.

Tabla de códigos de salida (no cambia entre versiones; la fija un test):

- 0: ok.
- 1: error interno o no clasificado (`interno`), o un lote en el que falló algún archivo
  (`lote_con_fallos`, con los resultados parciales en `error.details`).
- 2: uso o argumento inválido, coincide con Typer (`argumento_invalido`).
- 3: Solid Edge no disponible o no conectado (`no_conectado`).
- 4: error COM (`com_error`).
- 5: recurso no encontrado, documento o variable (`doc_no_encontrado`).
- 6: operación bloqueada por `--readonly` o `se run` sin flag, o no soportada
  (`solo_lectura`, `no_soportado`).
- 7: Solid Edge ocupado tras agotar los reintentos (`ocupado`).

Este módulo no importa pywin32: un `com_error` se reconoce por duck typing
(atributo `hresult`), así los tests usan un error falso.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

# HRESULT sin signo.
RPC_E_CALL_REJECTED = 0x80010001
RPC_E_SERVERCALL_RETRYLATER = 0x8001010A
RPC_S_SERVER_UNAVAILABLE = 0x800706BA
RPC_E_DISCONNECTED = 0x80010108
# Lo que devuelve la llamada cancelada con CoCancelCall (verificado en vivo: 0x80010002, "Call was
# canceled by the message filter"); 0x8001011F también se trata como cancelación.
RPC_E_CALL_CANCELED = 0x80010002
HRESULTS_CANCELADO = frozenset({RPC_E_CALL_CANCELED, 0x8001011F})
MK_E_UNAVAILABLE = 0x800401E3

# Códigos estándar de un servidor COM que rechaza llamadas. Contra Solid Edge 2026 no se pudieron
# provocar (2026-11-25: con diálogos modales y llamadas largas atiende o encola; ver el README).
HRESULTS_OCUPADO = frozenset({RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER})
HRESULTS_DESCONECTADO = frozenset({RPC_S_SERVER_UNAVAILABLE, RPC_E_DISCONNECTED})


class Salida(IntEnum):
    """Códigos de salida del proceso."""

    OK = 0
    INTERNO = 1
    ARGUMENTO = 2
    NO_CONECTADO = 3
    COM = 4
    NO_ENCONTRADO = 5
    BLOQUEADO = 6
    OCUPADO = 7


CODIGOS_DE_SALIDA: dict[str, int] = {
    "interno": Salida.INTERNO,
    "lote_con_fallos": Salida.INTERNO,
    "argumento_invalido": Salida.ARGUMENTO,
    "no_conectado": Salida.NO_CONECTADO,
    "com_error": Salida.COM,
    "doc_no_encontrado": Salida.NO_ENCONTRADO,
    "solo_lectura": Salida.BLOQUEADO,
    "no_soportado": Salida.BLOQUEADO,
    "ocupado": Salida.OCUPADO,
}


def formatear_hresult(hresult: int) -> str:
    """Devolvé el HRESULT como hex sin signo, ej. `0x8001010A`."""
    return f"0x{hresult & 0xFFFFFFFF:08X}"


def hresult_de(error: BaseException) -> int | None:
    """Devolvé el HRESULT sin signo de un `com_error` (real o falso), o None."""
    valor = getattr(error, "hresult", None)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor & 0xFFFFFFFF
    return None


class SeError(Exception):
    """Error base de `se` con código estable, exit code y datos opcionales."""

    codigo = "interno"

    def __init__(
        self,
        mensaje: str,
        *,
        hresult: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.hresult = None if hresult is None else hresult & 0xFFFFFFFF
        self.details = details

    @property
    def exit_code(self) -> int:
        return CODIGOS_DE_SALIDA[self.codigo]

    def a_dict(self) -> dict[str, Any]:
        """Objeto `error` del sobre JSON: `{code, message, hresult?, details?}`."""
        salida: dict[str, Any] = {"code": self.codigo, "message": self.mensaje}
        if self.hresult is not None:
            salida["hresult"] = formatear_hresult(self.hresult)
        if self.details:
            salida["details"] = self.details
        return salida


class ArgumentoInvalido(SeError):
    codigo = "argumento_invalido"


class NoConectado(SeError):
    codigo = "no_conectado"


class ErrorCom(SeError):
    codigo = "com_error"


class DocNoEncontrado(SeError):
    codigo = "doc_no_encontrado"


class SoloLectura(SeError):
    codigo = "solo_lectura"


class NoSoportado(SeError):
    codigo = "no_soportado"


class Ocupado(SeError):
    codigo = "ocupado"


class TiempoAgotado(Ocupado):
    def __init__(
        self,
        plazo: float,
        esperado: float,
        cancelacion: str = "cancelada",
        *,
        hresult: int | None = None,
    ) -> None:
        super().__init__(
            f"Solid Edge no respondió en {plazo:g} s y se dejó de esperar. Puede haber un "
            "diálogo modal abierto en Solid Edge esperando respuesta: revisalo y cerralo. "
            "Solid Edge no se cerró; la operación pudo completarse igual o quedar a medias. "
            "Si era una operación larga, aumentá el timeout.",
            hresult=hresult,
            details={
                "motivo": "timeout",
                "timeout_s": plazo,
                "esperado_s": round(esperado, 1),
                "cancelacion": cancelacion,
            },
        )


class ErrorLote(SeError):
    """Un lote terminó, pero algún archivo falló; `details` trae todos los resultados."""

    codigo = "lote_con_fallos"


def _leer_excepinfo(error: BaseException) -> tuple[str | None, dict[str, Any]]:
    """Extraé descripción y detalles del `excepinfo` de un com_error, si existe."""
    info = getattr(error, "excepinfo", None)
    if not isinstance(info, (tuple, list)) or len(info) < 3:
        return None, {}
    detalles: dict[str, Any] = {}
    descripcion = info[2] if isinstance(info[2], str) and info[2].strip() else None
    if descripcion:
        detalles["excepinfo"] = descripcion
    if isinstance(info[1], str) and info[1].strip():
        detalles["fuente"] = info[1]
    return descripcion, detalles


def traducir_com_error(error: BaseException) -> SeError:
    """Traducí un `com_error` a `SeError` conservando `hresult` y el texto de `excepinfo`.

    Un HRESULT de "ocupado" da `Ocupado` (7) y uno de servidor caído o desconectado da
    `NoConectado` (3); cualquier otro da `ErrorCom` (4).
    """
    hresult = hresult_de(error)
    descripcion, detalles = _leer_excepinfo(error)
    texto = getattr(error, "strerror", None)
    texto = texto.strip() if isinstance(texto, str) and texto.strip() else None
    mensaje = descripcion or texto or "Error COM."
    if texto and texto != mensaje:
        detalles["strerror"] = texto
    if hresult in HRESULTS_CANCELADO:
        return Ocupado(mensaje, hresult=hresult, details={"motivo": "cancelada"})
    clase = ErrorCom
    if hresult in HRESULTS_OCUPADO:
        clase = Ocupado
    elif hresult in HRESULTS_DESCONECTADO:
        clase = NoConectado
    return clase(mensaje, hresult=hresult, details=detalles or None)


def traducir(error: BaseException) -> SeError:
    """Llevá cualquier excepción a `SeError`; lo no clasificado queda como `interno`."""
    if isinstance(error, SeError):
        return error
    if hresult_de(error) is not None:
        return traducir_com_error(error)
    return SeError(f"{type(error).__name__}: {error}")
