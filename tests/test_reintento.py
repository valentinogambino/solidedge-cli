import pytest
from com_falso import ComErrorFalso, com_error

from se_cli.core.errors import Ocupado
from se_cli.core.retry import reintentar


class Pruebas:
    """Callable que falla con los errores dados y después devuelve un valor."""

    def __init__(self, *errores, valor="listo"):
        self.errores = list(errores)
        self.valor = valor
        self.llamadas = 0

    def __call__(self):
        self.llamadas += 1
        if self.errores:
            raise self.errores.pop(0)
        return self.valor


@pytest.mark.parametrize("hresult", [0x8001010A, 0x80010001])
def test_exito_tras_rechazos(hresult):
    fn = Pruebas(com_error(hresult), com_error(hresult))
    pausas = []

    assert reintentar(fn, intentos=5, espera=0.25, sleep=pausas.append) == "listo"
    assert fn.llamadas == 3
    assert pausas == [0.25, 0.25]


@pytest.mark.parametrize("hresult", [-2147417846, -2147418111, 0x8001010A, 0x80010001])
def test_hresult_con_y_sin_signo(hresult):
    # ComErrorFalso guarda el HRESULT con signo; el segundo caso lo fuerza sin signo.
    error = ComErrorFalso(0)
    error.hresult = hresult
    fn = Pruebas(error)

    assert reintentar(fn, sleep=lambda _: None) == "listo"
    assert fn.llamadas == 2


def test_agota_y_da_ocupado_exit_7():
    fn = Pruebas(*[com_error(0x8001010A)] * 10)
    pausas = []

    with pytest.raises(Ocupado) as info:
        reintentar(fn, intentos=3, espera=0.1, sleep=pausas.append)

    assert fn.llamadas == 3
    assert len(pausas) == 2
    assert info.value.exit_code == 7
    assert info.value.a_dict()["hresult"] == "0x8001010A"
    assert info.value.__cause__ is not None


def test_no_reintenta_otros_hresult():
    error = com_error(0x80004005)
    fn = Pruebas(error)

    with pytest.raises(ComErrorFalso) as info:
        reintentar(fn, sleep=lambda _: pytest.fail("no debía dormir"))

    assert info.value is error
    assert fn.llamadas == 1


def test_no_reintenta_errores_sin_hresult():
    fn = Pruebas(ValueError("x"))
    with pytest.raises(ValueError):
        reintentar(fn, sleep=lambda _: None)
    assert fn.llamadas == 1


def test_intentos_invalidos():
    with pytest.raises(ValueError):
        reintentar(lambda: 1, intentos=0)


def test_cancelacion_convierte_el_error_y_no_reintenta():
    from se_cli.core import plazo
    from se_cli.core.errors import TiempoAgotado

    estado = plazo.Plazo(0.3)
    llamadas = []

    def intento():
        llamadas.append("COM")
        estado.inicio_cancelacion = estado.latido
        raise com_error(0x8001010A)

    plazo.inicio_tarea(estado)
    try:
        with pytest.raises(TiempoAgotado) as info:
            reintentar(intento, sleep=lambda _: pytest.fail("No debe reintentar."))
        assert isinstance(info.value.__cause__, ComErrorFalso)
        with pytest.raises(TiempoAgotado):
            reintentar(intento)
    finally:
        plazo.fin_tarea()

    assert llamadas == ["COM"]
