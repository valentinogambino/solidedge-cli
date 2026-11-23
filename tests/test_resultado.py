import json
from datetime import UTC, date, datetime
from enum import IntEnum
from pathlib import Path

from se_cli.core.errors import ErrorCom, NoConectado
from se_cli.core.result import a_json, a_serializable, fallo, ok


def test_forma_exacta_de_ok():
    assert ok({"version": "226"}) == {"ok": True, "data": {"version": "226"}, "error": None}
    assert ok() == {"ok": True, "data": None, "error": None}


def test_forma_exacta_de_fallo():
    sin_extras = fallo(NoConectado("No hay Solid Edge."))
    assert sin_extras == {
        "ok": False,
        "data": None,
        "error": {"code": "no_conectado", "message": "No hay Solid Edge."},
    }
    con_extras = fallo(ErrorCom("Falló", hresult=-2147417846, details={"fuente": "SE"}))
    assert con_extras["error"] == {
        "code": "com_error",
        "message": "Falló",
        "hresult": "0x8001010A",
        "details": {"fuente": "SE"},
    }


class Color(IntEnum):
    ROJO = 3


class ObjetoCom:
    def __repr__(self):
        return "<COMObject " + "x" * 200 + ">"


def test_serializa_tipos_raros():
    datos = {
        "fecha": datetime(2026, 11, 22, 10, 30, tzinfo=UTC),
        "dia": date(2026, 11, 22),
        "tupla": (1, (2, 3)),
        "enum": Color.ROJO,
        "ruta": Path("a") / "b",
        "nan": float("nan"),
        "conjunto": {2, 1},
        "com": ObjetoCom(),
        3: "clave numérica",
    }
    plano = a_serializable(datos)

    assert plano["fecha"] == "2026-11-22T10:30:00+00:00"
    assert plano["dia"] == "2026-11-22"
    assert plano["tupla"] == [1, [2, 3]]
    assert plano["enum"] == 3
    assert plano["ruta"] == str(Path("a") / "b")
    assert plano["nan"] is None
    assert plano["conjunto"] == [1, 2]
    assert plano["com"].startswith("<COMObject ") and len(plano["com"]) == 80
    assert plano["com"].endswith("...")
    assert plano["3"] == "clave numérica"


def test_a_json_no_escapa_no_ascii_y_es_json_valido():
    texto = a_json(ok({"nombre": "Ménsula ñ", "dim": (1.5, 2)}))
    assert "Ménsula ñ" in texto
    assert json.loads(texto)["data"]["dim"] == [1.5, 2]


def test_fecha_com_se_informa_sin_zona_horaria():
    class datetime_com(datetime):  # imita pywintypes.datetime
        pass

    datetime_com.__module__ = "pywintypes"
    fecha = datetime_com(2026, 11, 23, 1, 25, 55, tzinfo=UTC)

    assert a_serializable(fecha) == "2026-11-23T01:25:55"
