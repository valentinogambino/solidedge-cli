"""Todo acceso COM pasa por `se_cli/core/`: ningún otro módulo de `src` importa pywin32."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
PATRON = re.compile(r"win32com|pythoncom|pywintypes")


def test_solo_core_toca_pywin32():
    fuera = [
        str(ruta.relative_to(SRC))
        for ruta in SRC.rglob("*.py")
        if "core" not in ruta.relative_to(SRC).parts[:2] and PATRON.search(ruta.read_text("utf-8"))
    ]
    assert fuera == []
