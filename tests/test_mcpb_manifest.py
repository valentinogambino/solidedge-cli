"""El manifest del paquete MCPB: codificación sana y sin `runtimes`."""

import json
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "mcpb" / "manifest.json"


def _bytes() -> bytes:
    return MANIFEST.read_bytes()


def test_sin_bom_y_utf8_estricto():
    datos = _bytes()
    assert not datos.startswith(b"\xef\xbb\xbf")
    datos.decode("utf-8")  # estricto: falla con bytes inválidos


def test_sin_mojibake_ni_reemplazo():
    texto = _bytes().decode("utf-8")
    for malo in ("Ã", "Â", "�"):
        assert malo not in texto


def test_compatibility_sin_runtimes():
    compat = json.loads(_bytes().decode("utf-8"))["compatibility"]
    assert "runtimes" not in compat
    assert compat["platforms"] == ["win32"]


def test_python_exe_dice_3_11():
    cfg = json.loads(_bytes().decode("utf-8"))["user_config"]["python_exe"]
    assert "3.11" in cfg["title"]
    assert "3.11" in cfg["description"]
