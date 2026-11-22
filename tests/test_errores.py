import pytest
from com_falso import ComErrorFalso, com_error

from se_cli.core import errors
from se_cli.core.errors import (
    CODIGOS_DE_SALIDA,
    ErrorCom,
    NoConectado,
    Ocupado,
    SeError,
    formatear_hresult,
    traducir,
    traducir_com_error,
)


def test_tabla_de_exit_codes_estable():
    assert CODIGOS_DE_SALIDA == {
        "interno": 1,
        "lote_con_fallos": 1,
        "argumento_invalido": 2,
        "no_conectado": 3,
        "com_error": 4,
        "doc_no_encontrado": 5,
        "solo_lectura": 6,
        "no_soportado": 6,
        "ocupado": 7,
    }
    assert [int(s) for s in errors.Salida] == [0, 1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize(
    ("clase", "codigo", "salida"),
    [
        (SeError, "interno", 1),
        (errors.ErrorLote, "lote_con_fallos", 1),
        (errors.ArgumentoInvalido, "argumento_invalido", 2),
        (NoConectado, "no_conectado", 3),
        (ErrorCom, "com_error", 4),
        (errors.DocNoEncontrado, "doc_no_encontrado", 5),
        (errors.SoloLectura, "solo_lectura", 6),
        (errors.NoSoportado, "no_soportado", 6),
        (Ocupado, "ocupado", 7),
    ],
)
def test_cada_clase_tiene_su_codigo_y_exit_code(clase, codigo, salida):
    error = clase("x")
    assert (error.codigo, error.exit_code) == (codigo, salida)


def test_hresult_hex_sin_signo():
    assert formatear_hresult(-2147417846) == "0x8001010A"
    assert formatear_hresult(0x8001010A) == "0x8001010A"
    assert formatear_hresult(5) == "0x00000005"


def test_traducir_com_error_conserva_hresult_y_excepinfo():
    error = traducir_com_error(com_error(0x80020009, "Exception occurred.", "Plano inválido"))

    assert isinstance(error, ErrorCom)
    assert error.exit_code == 4
    assert error.mensaje == "Plano inválido"
    assert error.a_dict() == {
        "code": "com_error",
        "message": "Plano inválido",
        "hresult": "0x80020009",
        "details": {
            "excepinfo": "Plano inválido",
            "fuente": "SolidEdge",
            "strerror": "Exception occurred.",
        },
    }


def test_traducir_com_error_sin_excepinfo_usa_strerror():
    error = traducir_com_error(ComErrorFalso(0x80004005, "Error no especificado"))
    assert error.mensaje == "Error no especificado"
    assert error.a_dict()["hresult"] == "0x80004005"


@pytest.mark.parametrize(
    ("hresult", "clase", "exit_code"),
    [
        (0x80010001, Ocupado, 7),
        (0x8001010A, Ocupado, 7),
        (0x800706BA, NoConectado, 3),
        (0x80010108, NoConectado, 3),
        (0x80004005, ErrorCom, 4),
    ],
)
def test_traducir_clasifica_por_hresult(hresult, clase, exit_code):
    error = traducir_com_error(com_error(hresult))
    assert isinstance(error, clase)
    assert error.exit_code == exit_code


def test_traducir_deja_pasar_se_error_y_clasifica_el_resto():
    original = NoConectado("nada")
    assert traducir(original) is original
    assert traducir(com_error(0x80004005)).codigo == "com_error"
    interno = traducir(ValueError("roto"))
    assert (interno.codigo, interno.exit_code) == ("interno", 1)
    assert "ValueError" in interno.mensaje
