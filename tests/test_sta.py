import threading

import pytest

from se_cli.core.errors import SeError
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
    hilo = HiloSta(registro.init, registro.uninit)
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
