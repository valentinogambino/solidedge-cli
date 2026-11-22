"""`se mass` sobre el COM falso."""

import pytest
from com_falso import ColeccionFalsa, ModeloFalso

CLAVES = {
    "masa",
    "volumen",
    "area",
    "densidad",
    "centro_de_masa",
    "centro_de_volumen",
    "momentos_de_inercia",
    "momentos_principales",
    "ejes_principales",
    "radios_de_giro",
    "actualizado",
    "unidades",
}

# (volumen, área, masa, cdg, cdv, momentos globales, principales, ejes, radios)
GUARDADAS = (
    0.002,
    0.1,
    5.4,
    (0.1, 0.2, 0.3),
    (0.11, 0.21, 0.31),
    (1.0, 2.0, 3.0, 0.1, 0.2, 0.3),
    (1.5, 2.5, 3.5),
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    (0.01, 0.02, 0.03),
)


def _pieza(app, tipo=1, nombre="Pieza.par"):
    doc = app.agregar_documento(nombre, ruta=f"C:\\p\\{nombre}", tipo=tipo)
    doc.Models = ColeccionFalsa([ModeloFalso(doc)])
    return doc


@pytest.fixture
def pieza(app_falsa):
    doc = _pieza(app_falsa)
    doc.fisicas_de_usuario = GUARDADAS
    return doc


def test_sin_densidad_lee_lo_guardado_y_no_escribe(cli, app_falsa, pieza):
    r, sobre = cli("mass")

    assert r.exit_code == 0
    assert app_falsa.escrituras == []
    data = sobre["data"]
    assert set(data) == CLAVES
    assert data["masa"] == 5.4 and data["volumen"] == 0.002 and data["area"] == 0.1
    assert data["densidad"] == pytest.approx(2700.0)
    assert data["centro_de_masa"] == [0.1, 0.2, 0.3]
    assert data["centro_de_volumen"] == [0.11, 0.21, 0.31]
    assert data["momentos_de_inercia"] == {
        "Ixx": 1.0,
        "Iyy": 2.0,
        "Izz": 3.0,
        "Ixy": 0.1,
        "Ixz": 0.2,
        "Iyz": 0.3,
    }
    assert data["momentos_principales"] == [1.5, 2.5, 3.5]
    assert data["ejes_principales"][:3] == [1.0, 0.0, 0.0]
    assert data["radios_de_giro"] == [0.01, 0.02, 0.03]
    assert data["actualizado"] is False
    assert data["unidades"]["masa"] == "kg" and data["unidades"]["longitud"] == "m"


def test_sin_densidad_ni_propiedades_guardadas_da_exit_2(cli, app_falsa):
    _pieza(app_falsa)
    r, sobre = cli("mass")
    assert r.exit_code == 2 and "--density" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_con_density_llama_con_kwargs_y_buffers(cli, app_falsa, pieza):
    r, sobre = cli("mass", "--density", "2700")

    assert r.exit_code == 0
    (llamada,) = app_falsa.escrituras
    nombre, kwargs = llamada
    assert nombre == "ComputePhysicalPropertiesWithSpecifiedDensity"
    assert set(kwargs) == {
        "Density",
        "Accuracy",
        "CenterOfGravity",
        "CenterOfVolume",
        "GlobalMomentsOfInteria",  # el typo "Interia" es de Siemens
        "PrincipalMomentsOfInteria",
        "PrincipalAxes",
        "RadiiOfGyration",
    }
    assert kwargs["Density"] == 2700.0
    assert len(kwargs["GlobalMomentsOfInteria"]) == 6 and len(kwargs["PrincipalAxes"]) == 9
    data = sobre["data"]
    assert data["masa"] == pytest.approx(0.001 * 2700.0)
    assert data["densidad"] == 2700.0
    assert data["actualizado"] is True
    assert app_falsa.historial_alertas == [False, True]


def test_units_convierte_todo(cli, app_falsa, pieza):
    r, sobre = cli("mass", "--units", "mm,g")

    data = sobre["data"]
    assert r.exit_code == 0
    assert data["masa"] == pytest.approx(5400.0)
    assert data["volumen"] == pytest.approx(0.002 / 1e-9)
    assert data["area"] == pytest.approx(0.1 / 1e-6)
    assert data["centro_de_masa"] == [
        pytest.approx(100.0),
        pytest.approx(200.0),
        pytest.approx(300.0),
    ]
    assert data["densidad"] == pytest.approx(2700.0 * 1e-9 / 1e-3)
    assert data["momentos_de_inercia"]["Ixx"] == pytest.approx(1.0 / (1e-3 * 1e-6))
    assert data["ejes_principales"][0] == 1.0
    assert data["unidades"] == {
        "masa": "g",
        "longitud": "mm",
        "volumen": "mm^3",
        "area": "mm^2",
        "densidad": "g/mm^3",
        "inercia": "g*mm^2",
    }


def test_units_invalida_da_exit_2(cli, pieza):
    r, _ = cli("mass", "--units", "furlong")
    assert r.exit_code == 2


def test_chapa_y_ensamble_son_soportados(cli, app_falsa):
    chapa = _pieza(app_falsa, tipo=4, nombre="Chapa.psm")
    chapa.fisicas_de_usuario = GUARDADAS
    asm = app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3)
    asm.fisicas_de_usuario = GUARDADAS

    assert cli("mass", "--doc", "Chapa.psm")[0].exit_code == 0
    r, sobre = cli("mass", "--density", "1000", "--doc", "Conj.asm")
    assert r.exit_code == 0 and sobre["data"]["masa"] == pytest.approx(1.0)


@pytest.mark.parametrize("tipo", [2, 6, 8])
def test_tipo_no_soportado_da_exit_2(cli, app_falsa, tipo):
    app_falsa.agregar_documento("Otro", ruta="C:\\p\\Otro", tipo=tipo)
    r, sobre = cli("mass", "--density", "1000")
    assert r.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"
    assert "no se puede usar" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


@pytest.mark.parametrize("valor", ["0", "-5", "nan"])
def test_densidad_invalida_da_exit_2_sin_conectar(cli_sin_instancia, valor):
    r, _ = cli_sin_instancia("mass", f"--density={valor}")
    assert r.exit_code == 2
    assert cli_sin_instancia.proveedor.llamadas == 0


def test_readonly_bloquea_solo_el_recalculo(cli, app_falsa, pieza):
    r, sobre = cli("--readonly", "mass", "--density", "2700")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert app_falsa.escrituras == []

    assert cli("--readonly", "mass")[0].exit_code == 0


def test_dry_run_con_density_no_toca_com(cli, app_falsa, pieza):
    r, sobre = cli("--dry-run", "mass", "--density", "2700")
    assert r.exit_code == 0
    assert sobre["data"] == {"dry_run": True, "accion": "mass", "densidad": 2700.0}
    assert app_falsa.registro == []


def test_dry_run_sin_density_igual_lee(cli, app_falsa, pieza):
    r, sobre = cli("--dry-run", "mass")
    assert r.exit_code == 0 and set(sobre["data"]) == CLAVES


def test_doc_inexistente_da_exit_5(cli, pieza):
    r, sobre = cli("mass", "--doc", "NoExiste.par")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"


def test_sin_instancia_da_exit_3(cli_sin_instancia):
    r, sobre = cli_sin_instancia("mass")
    assert r.exit_code == 3 and sobre["ok"] is False


def test_modo_humano(cli, pieza):
    r, _ = cli("mass", como_json=False)
    assert r.exit_code == 0 and "masa" in r.stdout


def test_tupla_incompleta_da_error_com(cli, app_falsa, pieza):
    pieza.fisicas_de_usuario = (1.0, 2.0)
    r, sobre = cli("mass")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
