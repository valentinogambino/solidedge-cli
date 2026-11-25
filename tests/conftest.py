import json

import pytest
from com_falso import AplicacionFalsa, FabricaApp
from typer.testing import CliRunner

from se_cli import ejecucion
from se_cli.cli import app
from se_cli.core.session import Sesion
from se_cli.core.sta import HiloSta


@pytest.fixture
def app_falsa():
    return AplicacionFalsa()


@pytest.fixture
def sta():
    """Hilo STA con init/uninit falsos (no toca pywin32)."""
    hilo = HiloSta(lambda: None, lambda: None, habilitar=lambda: None, cancelar=lambda _: None)
    yield hilo
    hilo.cerrar()


@pytest.fixture
def fabrica(app_falsa):
    return FabricaApp(app_falsa)


@pytest.fixture
def sesion(sta, fabrica):
    """Sesión sobre el COM falso, sin esperas reales."""
    return Sesion(sta=sta, proveedor=fabrica, lanzador=FabricaApp(), sleep=lambda _: None)


class Cli:
    """Invoca `se` con `CliRunner`; por defecto agrega `--json` y decodifica el sobre."""

    def __init__(self) -> None:
        self.runner = CliRunner()

    def __call__(self, *args: str, como_json: bool = True):
        globales = ["--json"] if como_json else []
        resultado = self.runner.invoke(app, [*globales, *args])
        sobre = None
        if como_json and resultado.stdout.strip():
            sobre = json.loads(resultado.stdout)
        return resultado, sobre

    def con(self, opcion_global: str, *args: str):
        """Como `__call__`, con una opción global más (`--readonly`, `--dry-run`)."""
        resultado = self.runner.invoke(app, ["--json", opcion_global, *args])
        return resultado, json.loads(resultado.stdout)


@pytest.fixture
def cli(monkeypatch, sesion):
    """CLI sobre el COM falso (`app_falsa`): inyecta la sesión en `se_cli.ejecucion`."""
    monkeypatch.setattr(ejecucion, "crear_sesion", lambda: sesion)
    return Cli()


@pytest.fixture
def cli_sin_instancia(monkeypatch, sta):
    """CLI con Solid Edge cerrado: ni enganchar ni lanzar encuentran nada."""
    lanzador = FabricaApp()
    proveedor = FabricaApp()
    sesion = Sesion(sta=sta, proveedor=proveedor, lanzador=lanzador, sleep=lambda _: None)
    monkeypatch.setattr(ejecucion, "crear_sesion", lambda: sesion)
    herramienta = Cli()
    herramienta.proveedor = proveedor
    herramienta.lanzador = lanzador
    return herramienta
