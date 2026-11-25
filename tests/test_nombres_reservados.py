import ntpath
import os

import pytest

from se_cli.core import documentos

RESERVADOS = [
    "CON",
    "con",
    "PRN",
    "AUX",
    "NUL",
    "nul",
    "CONIN$",
    "CONOUT$",
    "COM1",
    "com9",
    "LPT1",
    "lpt9",
    "COM¹",
    "LPT²",
    "COM³",
    "NUL.txt",
    "con .par",
    "COM1.asm",
    "aux.tar.gz",
]
NO_RESERVADOS = ["CONSOLA.par", "nulo", "COM10", "LPT0", "COM0", "pieza.con", "", "a.nul", "COM"]


@pytest.mark.parametrize("nombre", RESERVADOS)
def test_lista_propia_detecta_reservados(nombre):
    assert documentos._reservado_por_lista(nombre)


@pytest.mark.parametrize("nombre", NO_RESERVADOS)
def test_lista_propia_no_marca_nombres_comunes(nombre):
    assert not documentos._reservado_por_lista(nombre)


def test_usa_os_path_isreserved_si_existe(monkeypatch):
    llamadas = []

    def falso(nombre):
        llamadas.append(nombre)
        return nombre == "marcado"

    monkeypatch.setattr(os.path, "isreserved", falso, raising=False)
    assert documentos.es_nombre_reservado("marcado")
    assert not documentos.es_nombre_reservado("CON")  # manda lo que diga isreserved
    assert llamadas == ["marcado", "CON"]


def test_sin_os_path_isreserved_cae_a_la_lista(monkeypatch):
    monkeypatch.delattr(os.path, "isreserved", raising=False)
    monkeypatch.delattr(ntpath, "isreserved", raising=False)
    assert documentos.es_nombre_reservado("NUL.txt")
    assert not documentos.es_nombre_reservado("nulo")


@pytest.mark.parametrize("destino", ["NUL.txt", "dir/con .par", "COM1.asm"])
def test_validar_nombres_rechaza_reservados(destino):
    with pytest.raises(documentos.ArgumentoInvalido):
        documentos.validar_nombres_windows(destino)
