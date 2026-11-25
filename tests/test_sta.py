import threading
import time

import pytest
from com_falso import BloqueoFalso

from se_cli.core import plazo
from se_cli.core import sta as modulo_sta
from se_cli.core.errors import SeError, TiempoAgotado
from se_cli.core.retry import reintentar
from se_cli.core.sta import HiloSta


class Registro:
    """init/uninit falsos que guardan en qué hilo se llamaron."""

    def __init__(self):
        self.eventos = []

    def init(self):
        self.eventos.append(("init", threading.get_ident()))

    def uninit(self):
        self.eventos.append(("uninit", threading.get_ident()))


@pytest.fixture
def registro():
    return Registro()


@pytest.fixture
def sta(registro):
    hilo = HiloSta(registro.init, registro.uninit, habilitar=lambda: None)
    yield hilo
    hilo.cerrar()


def test_todo_corre_en_el_mismo_hilo_distinto_del_llamador(sta):
    ids = [sta.ejecutar(threading.get_ident) for _ in range(5)]

    assert len(set(ids)) == 1
    assert ids[0] != threading.get_ident()
    assert ids[0] == sta.ident


def test_llamadas_desde_otros_hilos_van_al_mismo_worker(sta):
    resultados = []
    hilos = [
        threading.Thread(target=lambda: resultados.append(sta.ejecutar(threading.get_ident)))
        for _ in range(4)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert set(resultados) == {sta.ident}


def test_pasa_argumentos_y_devuelve_resultado(sta):
    assert sta.ejecutar(lambda a, b=0: a + b, 2, b=3) == 5


def test_propaga_excepciones_y_sigue_vivo(sta):
    def explota():
        raise ValueError("roto")

    with pytest.raises(ValueError, match="roto"):
        sta.ejecutar(explota)
    assert sta.ejecutar(lambda: "sigue") == "sigue"


def test_init_y_uninit_una_sola_vez_en_el_worker(sta, registro):
    sta.ejecutar(lambda: None)
    sta.ejecutar(lambda: None)
    sta.cerrar()
    sta.cerrar()

    assert [nombre for nombre, _ in registro.eventos] == ["init", "uninit"]
    assert {ident for _, ident in registro.eventos} == {sta.ident}


def test_no_arranca_hasta_el_primer_uso(registro):
    hilo = HiloSta(registro.init, registro.uninit)
    hilo.cerrar()

    assert registro.eventos == []
    assert hilo.ident is None


def test_cierre_limpio_y_rechaza_trabajo_nuevo(sta, registro):
    sta.ejecutar(lambda: None)
    sta.cerrar()

    assert registro.eventos[-1][0] == "uninit"
    with pytest.raises(SeError, match="cerrado"):
        sta.ejecutar(lambda: None)


def test_context_manager_cierra(registro):
    with HiloSta(registro.init, registro.uninit) as hilo:
        hilo.ejecutar(lambda: None)

    assert registro.eventos[-1][0] == "uninit"


def test_llamada_reentrante_no_hace_deadlock(sta):
    def externa():
        return sta.ejecutar(threading.get_ident), threading.get_ident()

    interno, externo = sta.ejecutar(externa)
    assert interno == externo == sta.ident


def test_falla_de_init_se_informa(registro):
    def mal_init():
        raise OSError("sin COM")

    hilo = HiloSta(mal_init, registro.uninit)
    with pytest.raises(SeError, match="sin COM"):
        hilo.ejecutar(lambda: None)
    hilo.cerrar()
    assert registro.eventos == []


def test_timeout_cancelado_reutiliza_hilo():
    bloqueo = BloqueoFalso()
    bloqueo.bloquear("Version")
    with HiloSta(
        lambda: None, lambda: None, habilitar=lambda: None, cancelar=lambda _: bloqueo.cancelar()
    ) as hilo:
        anterior = hilo.ejecutar(threading.get_ident)
        inicio = time.monotonic()
        with pytest.raises(TiempoAgotado) as info:
            hilo.ejecutar_con_plazo(0.3, bloqueo.tocar, "Version")

        assert time.monotonic() - inicio < 1
        assert info.value.details["cancelacion"] == "cancelada"
        assert info.value.hresult == 0x8001011F
        assert hilo.ejecutar(threading.get_ident) == anterior
        assert hilo.generacion == 0


def test_abandona_y_uninicializa_solo_al_volver(registro):
    bloqueo = BloqueoFalso()
    bloqueo.bloquear("Version")
    llamadas = []

    def trabajo():
        try:
            reintentar(lambda: bloqueo.tocar("Version"))
        finally:
            reintentar(lambda: llamadas.append("COM"))

    with HiloSta(
        registro.init, registro.uninit, habilitar=lambda: None, cancelar=lambda _: None, gracia=0.2
    ) as hilo:
        anterior = hilo.ejecutar(threading.current_thread)
        try:
            with pytest.raises(TiempoAgotado) as info:
                hilo.ejecutar_con_plazo(0.3, trabajo)
            assert info.value.details["cancelacion"] == "abandonada"
            assert info.value.hresult is None
            assert hilo.generacion == 1
            assert hilo.ejecutar(threading.get_ident) != anterior.ident
            assert anterior.is_alive()
            inicio = time.monotonic()
            hilo.cerrar()
            assert time.monotonic() - inicio < 2
            assert anterior.is_alive()
        finally:
            bloqueo.soltar()
            anterior.join(timeout=2)

    assert not llamadas
    assert [n for n, ident in registro.eventos if ident == anterior.ident] == ["init", "uninit"]


def test_latido_continuo_no_vence(sta):
    def trabajo():
        for _ in range(20):
            reintentar(lambda: time.sleep(0.1))
        return "listo"

    assert sta.ejecutar_con_plazo(0.3, trabajo) == "listo"


def test_habilita_una_sola_vez_y_en_sta():
    hilos = []
    with HiloSta(
        lambda: None, lambda: None, habilitar=lambda: hilos.append(threading.get_ident())
    ) as hilo:
        ident = hilo.ejecutar(threading.get_ident)
        assert hilos == []
        for _ in range(2):
            hilo.ejecutar_con_plazo(1, lambda: None)
        assert hilos == [ident]


def test_suspende_el_plazo(sta):
    def trabajo():
        with plazo.suspendido():
            time.sleep(0.5)
        return "listo"

    assert sta.ejecutar_con_plazo(0.3, trabajo) == "listo"


def test_plan_b_abandona_sin_llamar_a_com(monkeypatch):
    monkeypatch.setattr(modulo_sta, "CANCELAR_POR_COM", False)
    bloqueo = BloqueoFalso()
    bloqueo.bloquear("Version")
    prohibidas = []

    with HiloSta(
        lambda: None,
        lambda: None,
        habilitar=lambda: prohibidas.append("habilitar"),
        cancelar=lambda _: prohibidas.append("cancelar"),
    ) as hilo:
        viejo = hilo.ejecutar(threading.current_thread)
        inicio = time.monotonic()
        try:
            with pytest.raises(TiempoAgotado) as info:
                hilo.ejecutar_con_plazo(0.3, bloqueo.tocar, "Version")
            assert time.monotonic() - inicio < 1
            assert info.value.details["cancelacion"] == "abandonada"
            assert prohibidas == []
        finally:
            bloqueo.soltar()
            viejo.join(timeout=2)
