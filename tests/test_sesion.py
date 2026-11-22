import threading

import pytest
from com_falso import AplicacionFalsa, FabricaApp, com_error

from se_cli.core.errors import ErrorCom, NoConectado, Ocupado, SeError
from se_cli.core.session import Sesion


def test_sin_instancia_da_no_conectado_y_no_lanza(sta):
    proveedor, lanzador = FabricaApp(), FabricaApp(AplicacionFalsa())
    sesion = Sesion(sta=sta, proveedor=proveedor, lanzador=lanzador)

    with pytest.raises(NoConectado) as info:
        sesion.conectar()

    assert info.value.exit_code == 3
    assert info.value.a_dict()["hresult"] == "0x800401E3"
    assert proveedor.llamadas == 1
    assert lanzador.llamadas == 0


def test_conectar_a_instancia_abierta(sesion, fabrica):
    datos = sesion.conectar()

    assert datos == {"version": "226.00.00.00", "nombre": "Solid Edge", "lanzada": False}
    assert fabrica.llamadas == 1


def test_lanzar_usa_la_factory_de_lanzamiento_solo_si_no_hay_instancia(sta):
    nueva = AplicacionFalsa(version="226.99")
    lanzador = FabricaApp(nueva)
    sesion = Sesion(sta=sta, proveedor=FabricaApp(), lanzador=lanzador)

    datos = sesion.conectar(lanzar=True)

    assert datos["lanzada"] is True
    assert datos["version"] == "226.99"
    assert lanzador.llamadas == 1


def test_lanzar_no_lanza_si_ya_hay_instancia(sta, app_falsa):
    lanzador = FabricaApp(AplicacionFalsa())
    sesion = Sesion(sta=sta, proveedor=FabricaApp(app_falsa), lanzador=lanzador)

    assert sesion.conectar(lanzar=True)["lanzada"] is False
    assert lanzador.llamadas == 0


def test_falla_el_lanzamiento(sta):
    sesion = Sesion(sta=sta, proveedor=FabricaApp(), lanzador=FabricaApp())
    with pytest.raises(NoConectado, match="lanzar"):
        sesion.conectar(lanzar=True)


def test_llamar_sin_conectar_da_no_conectado(sesion):
    with pytest.raises(NoConectado):
        sesion.llamar(lambda app: app.Version)


def test_llamar_corre_en_el_hilo_sta(sesion, sta):
    sesion.conectar()
    assert sesion.llamar(lambda app: threading.get_ident()) == sta.ident


def test_app_fuera_del_hilo_sta_se_rechaza(sesion):
    sesion.conectar()
    with pytest.raises(SeError, match="llamar"):
        sesion.app  # noqa: B018


def test_reconecta_una_vez_cuando_version_falla(sta):
    muerta = AplicacionFalsa()
    viva = AplicacionFalsa(version="226.01")
    fabrica = FabricaApp(muerta, viva)
    sesion = Sesion(sta=sta, proveedor=fabrica, sleep=lambda _: None)
    sesion.conectar()
    muerta.fallar("Version", com_error(0x800706BA, "El servidor RPC no está disponible"))

    assert sesion.llamar(lambda app: app.Version) == "226.01"
    assert fabrica.llamadas == 2


def test_si_no_puede_reconectar_da_no_conectado(sta):
    app = AplicacionFalsa()
    fabrica = FabricaApp(app, com_error(0x800401E3))
    sesion = Sesion(sta=sta, proveedor=fabrica, sleep=lambda _: None)
    sesion.conectar()
    app.fallar("Version", com_error(0x80010108))

    with pytest.raises(NoConectado):
        sesion.llamar(lambda app: app.Version)
    with pytest.raises(NoConectado):
        sesion.llamar(lambda app: app.Version)


def test_reintenta_llamada_rechazada(sesion, app_falsa):
    sesion.conectar()
    app_falsa.fallar("Name", com_error(0x8001010A), com_error(0x8001010A))

    assert sesion.llamar(lambda app: app.Name) == "Solid Edge"


def test_ocupado_persistente_da_exit_7(sta, app_falsa):
    sesion = Sesion(sta=sta, proveedor=FabricaApp(app_falsa), intentos=3, sleep=lambda _: None)
    sesion.conectar()
    app_falsa.fallar("Name", *[com_error(0x80010001)] * 3)

    with pytest.raises(Ocupado) as info:
        sesion.llamar(lambda app: app.Name)
    assert info.value.exit_code == 7


def test_llamar_traduce_errores(sesion, app_falsa):
    sesion.conectar()
    app_falsa.fallar("Name", com_error(0x80020009, "Excepción", "Algo salió mal"))

    with pytest.raises(ErrorCom) as info:
        sesion.llamar(lambda app: app.Name, reintentar_todo=False)
    assert info.value.mensaje == "Algo salió mal"

    with pytest.raises(SeError) as interno:
        sesion.llamar(lambda app: 1 / 0)
    assert interno.value.exit_code == 1


def test_sin_reintentar_todo_no_repite_fn(sesion, app_falsa):
    sesion.conectar()
    app_falsa.fallar("Name", com_error(0x8001010A))
    llamadas = []

    def fn(app):
        llamadas.append(1)
        return app.Name

    with pytest.raises(Ocupado):
        sesion.llamar(fn, reintentar_todo=False)
    assert len(llamadas) == 1


def test_sin_alertas_restaura_el_valor(sesion, app_falsa):
    sesion.conectar()
    app_falsa.DisplayAlerts = True
    app_falsa.historial_alertas.clear()

    with sesion.sin_alertas():
        assert app_falsa.DisplayAlerts is False

    assert app_falsa.DisplayAlerts is True
    assert app_falsa.historial_alertas == [False, True]


def test_sin_alertas_restaura_aun_con_excepcion(sesion, app_falsa):
    sesion.conectar()
    app_falsa.DisplayAlerts = True

    with pytest.raises(RuntimeError, match="boom"), sesion.sin_alertas():
        raise RuntimeError("boom")

    assert app_falsa.DisplayAlerts is True


def test_sin_alertas_respeta_valor_previo_falso(sesion, app_falsa):
    sesion.conectar()
    app_falsa.DisplayAlerts = False

    with sesion.sin_alertas():
        pass

    assert app_falsa.DisplayAlerts is False


def test_cerrar_suelta_la_app(sesion):
    sesion.conectar()
    sesion.cerrar()
    with pytest.raises(NoConectado):
        sesion.llamar(lambda app: app.Version)
