"""Pruebas del smoke que no requieren una sesión COM."""

import importlib.util
import sys
import zlib
from pathlib import Path
from types import ModuleType

import pytest

RUTA_SMOKE = Path(__file__).resolve().parents[1] / "scripts" / "smoke.py"
SPEC = importlib.util.spec_from_file_location("smoke", RUTA_SMOKE)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


@pytest.mark.parametrize(
    ("contenido", "estado", "halladas"),
    [
        (
            b"1 0 obj\n<< /Filter /FlateDecode >>\nstream\n"
            + zlib.compress(b"BT (cOmMuNiTy) Tj ET")
            + b"\nendstream\nendobj\n",
            "detectada",
            ["Community"],
        ),
        (b"BT (Plano de prueba) Tj ET\n", "no detectada", []),
        (
            b"1 0 obj\n<< /Filter /FlateDecode >>\nstream\nroto\nendstream\nendobj\n",
            "indeterminada",
            [],
        ),
    ],
)
def test_detectar_marca_de_agua(contenido, estado, halladas):
    resultado = smoke.detectar_marca_de_agua(b"%PDF-1.4\n" + contenido + b"%%EOF\n")
    assert resultado["estado"] == estado
    assert resultado["cadenas"] == halladas
    assert "abriendo el PDF" in resultado["mensaje"]


def test_reintentar_ante_rechazo_y_servidor_ocupado(monkeypatch):
    class ErrorComFalso(Exception):
        def __init__(self, hresult):
            self.hresult = hresult
            super().__init__(hresult)

    pywintypes_falso = ModuleType("pywintypes")
    pywintypes_falso.com_error = ErrorComFalso
    monkeypatch.setitem(sys.modules, "pywintypes", pywintypes_falso)

    errores = iter([0x80010001 - 2**32, 0x8001010A])
    esperas = []
    monkeypatch.setattr(smoke.time, "sleep", esperas.append)

    def llamada():
        hresult = next(errores, None)
        if hresult is not None:
            raise ErrorComFalso(hresult)
        return "listo"

    assert smoke.reintentar(llamada) == "listo"
    assert esperas == [0.5, 0.5]

    def error_permanente():
        raise ErrorComFalso(0x80004005)

    with pytest.raises(ErrorComFalso):
        smoke.reintentar(error_permanente)
    assert esperas == [0.5, 0.5]
