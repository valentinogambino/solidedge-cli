"""Reintento ante llamadas COM rechazadas porque Solid Edge está ocupado."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from se_cli.core import plazo
from se_cli.core.errors import (
    HRESULTS_CANCELADO,
    HRESULTS_OCUPADO,
    Ocupado,
    TiempoAgotado,
    hresult_de,
)

T = TypeVar("T")

INTENTOS_POR_DEFECTO = 10
ESPERA_POR_DEFECTO = 0.5


def reintentar(
    fn: Callable[[], T],
    intentos: int = INTENTOS_POR_DEFECTO,
    espera: float = ESPERA_POR_DEFECTO,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Llamá `fn()` hasta `intentos` veces mientras falle con RPC_E_CALL_REJECTED
    (`0x80010001`) o RPC_E_SERVERCALL_RETRYLATER (`0x8001010A`).

    El HRESULT se compara sin signo, así que sirve el valor con o sin signo. Cualquier otro
    error se relanza tal cual, sin reintentar. Al agotar los intentos levanta `Ocupado`
    (exit 7) con el HRESULT del último rechazo. `sleep` es inyectable para los tests.
    """
    if intentos < 1:
        raise ValueError("Tiene que haber al menos un intento.")
    for intento in range(1, intentos + 1):
        plazo.antes_de_llamar()
        try:
            return fn()
        except Exception as error:
            hresult = hresult_de(error)
            if plazo.cancelada() and not isinstance(error, TiempoAgotado):
                cancelado = hresult if hresult in HRESULTS_CANCELADO else None
                raise plazo.error_cancelado(cancelado) from error
            if hresult not in HRESULTS_OCUPADO:
                raise
            if intento == intentos:
                raise Ocupado(
                    f"Solid Edge sigue ocupado tras {intentos} intentos.",
                    hresult=hresult,
                    details={"intentos": intentos, "motivo": "rechazado"},
                ) from error
            sleep(espera)
    raise AssertionError("inalcanzable")  # pragma: no cover
