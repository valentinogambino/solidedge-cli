"""Arranque del paquete con sus dependencias locales."""

import site
import sys
import sysconfig
from pathlib import Path


def main() -> None:
    if sys.version_info[:2] != (3, 11) or sysconfig.get_platform() != "win-amd64":
        raise SystemExit("Seleccioná Python 3.11 x64 en la configuración de la extensión.")
    site.addsitedir(str(Path(__file__).resolve().parent / "lib"))
    from se_cli.mcp_server import main as servir

    servir()


if __name__ == "__main__":
    main()
