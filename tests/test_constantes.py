import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from se_cli.core import constants
from se_cli.core.errors import ArgumentoInvalido

RUTA = Path(__file__).resolve().parents[1] / "scripts" / "gen_constants.py"
SPEC = importlib.util.spec_from_file_location("gen_constants", RUTA)
gen = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gen  # los dataclasses lo necesitan
SPEC.loader.exec_module(gen)


class InfoTipoFalsa:
    def __init__(self, kind, variables):
        self.kind = kind
        self.variables = variables

    def GetTypeAttr(self):
        return SimpleNamespace(typekind=self.kind, cVars=len(self.variables))

    def GetVarDesc(self, indice):
        return SimpleNamespace(memid=indice, value=self.variables[indice][1])

    def GetNames(self, memid):
        return (self.variables[memid][0],)


class TypelibFalsa:
    """Imita lo mínimo de PyITypeLib; los tipos están desordenados a propósito."""

    def __init__(self):
        self.tipos = [
            ("ZetaConstants", InfoTipoFalsa(0, [("igZ", 9), ("igNeg", -5)])),
            ("UnAlias", InfoTipoFalsa(6, [])),
            ("AlfaConstants", InfoTipoFalsa(0, [("igB", 2), ("igA", 1), ("class", 3)])),
        ]

    def GetLibAttr(self):
        return ("{ABCD}", 0, 3, 1, 4, 8)

    def GetDocumentation(self, indice):
        return ("LibFalsa",) if indice == -1 else (self.tipos[indice][0],)

    def GetTypeInfoCount(self):
        return len(self.tipos)

    def GetTypeInfo(self, indice):
        return self.tipos[indice][1]


@pytest.fixture
def info():
    return gen.leer_typelib("falsa.tlb", cargar=lambda ruta: TypelibFalsa())


def test_leer_typelib_toma_solo_enums(info):
    assert (info.nombre, info.version, info.guid) == ("LibFalsa", "1.4", "{ABCD}")
    assert [(e.nombre, e.miembros) for e in info.enums] == [
        ("ZetaConstants", [("igZ", 9), ("igNeg", -5)]),
        ("AlfaConstants", [("igB", 2), ("igA", 1), ("class", 3)]),
    ]


def test_generar_es_determinista_y_ordenado(info):
    primero = gen.generar(info)
    info.enums.reverse()
    segundo = gen.generar(info)

    assert primero == segundo
    assert primero.index('"AlfaConstants"') < primero.index('"ZetaConstants"')
    assert "LibFalsa 1.4" in primero
    assert "no editar a mano" in primero
    assert '"n_class": 3,' in primero
    assert '"igNeg": -5,' in primero
    assert primero.endswith("\n") and "\r" not in primero


def test_el_modulo_generado_funciona(info):
    modulo = ModuleType("se_cli.core.constantes_falsas")
    exec(compile(gen.generar(info), "<generado>", "exec"), modulo.__dict__)

    assert modulo.nombres_de_enums() == ("AlfaConstants", "ZetaConstants")
    assert modulo.valor("igNeg") == -5
    assert modulo.valor("igB") == 2
    assert modulo.AlfaConstants.igA == 1
    assert modulo.ZetaConstants(9).name == "igZ"


def test_valor_resuelve_nombres_reales():
    assert constants.valor("igProfileClosed") == 1
    assert constants.valor("igFrontView") == 4
    assert constants.DocumentTypeConstants.igPartDocument == 1


def test_valor_falla_claro_con_nombre_inexistente():
    with pytest.raises(ArgumentoInvalido) as info:
        constants.valor("igProfileClosd")

    assert info.value.exit_code == 2
    assert "igProfileClosd" in info.value.mensaje
    assert "igProfileClosed" in info.value.mensaje


def test_enum_inexistente_da_attribute_error():
    with pytest.raises(AttributeError):
        constants.NoExisteConstants  # noqa: B018


def test_main_con_tlb_inexistente(tmp_path, capsys):
    assert gen.main([str(tmp_path / "no.tlb"), "--salida", str(tmp_path / "x.py")]) == 1
    assert "No existe" in capsys.readouterr().err


def test_main_escribe_con_tlb_inyectada(tmp_path, monkeypatch, info):
    tlb = tmp_path / "falsa.tlb"
    tlb.write_bytes(b"")
    monkeypatch.setattr(gen, "leer_typelib", lambda ruta: info)
    salida = tmp_path / "salida.py"

    assert gen.main([str(tlb), "--salida", str(salida)]) == 0
    assert salida.read_text(encoding="utf-8") == gen.generar(info)
