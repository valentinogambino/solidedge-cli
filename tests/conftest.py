import pytest
from com_falso import AplicacionFalsa, FabricaApp

from se_cli.core.session import Sesion
from se_cli.core.sta import HiloSta


@pytest.fixture
def app_falsa():
    return AplicacionFalsa()


@pytest.fixture
def sta():
    """Hilo STA con init/uninit falsos (no toca pywin32)."""
    hilo = HiloSta(lambda: None, lambda: None)
    yield hilo
    hilo.cerrar()


@pytest.fixture
def fabrica(app_falsa):
    return FabricaApp(app_falsa)


@pytest.fixture
def sesion(sta, fabrica):
    """Sesión sobre el COM falso, sin esperas reales."""
    return Sesion(sta=sta, proveedor=fabrica, lanzador=FabricaApp(), sleep=lambda _: None)
