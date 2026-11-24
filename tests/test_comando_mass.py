"""`se mass` sobre el COM falso."""

import pytest
from com_falso import ColeccionFalsa, ModeloFalso, OcurrenciaFalsa

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
    doc.fisicas_calculadas = GUARDADAS
    doc.densidad_calculada = 2700.0
    return doc


def test_sin_densidad_lee_lo_guardado_y_no_escribe(cli, app_falsa, pieza):
    r, sobre = cli("mass")

    assert r.exit_code == 0
    assert app_falsa.escrituras == []
    data = sobre["data"]
    assert set(data) == CLAVES
    assert data["masa"] == 5.4 and data["volumen"] == 0.002 and data["area"] == 0.1
    assert data["densidad"] == 2700.0
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


def test_sin_densidad_lee_con_get_physical_properties_y_no_con_las_de_usuario(
    cli, app_falsa, pieza
):
    cli("mass")

    nombres = [llamada[0] for llamada in app_falsa.registro]
    assert "Model.GetPhysicalProperties" in nombres
    assert "GetUserPhysicalProperties" not in nombres


def test_sin_densidad_ni_calculo_previo_da_exit_2(cli, app_falsa):
    _pieza(app_falsa)
    r, sobre = cli("mass")
    assert r.exit_code == 2 and "--density" in sobre["error"]["message"]
    assert app_falsa.escrituras == []


def test_el_calculo_con_density_se_puede_leer_recien_despues_de_guardar(cli, app_falsa):
    _pieza(app_falsa)

    assert cli("mass", "--density", "2700")[0].exit_code == 0
    assert cli("mass")[0].exit_code == 2  # verificado en vivo: Status 2 hasta guardar
    assert cli("docs", "save")[0].exit_code == 0
    r, sobre = cli("mass")

    assert r.exit_code == 0
    assert sobre["data"]["densidad"] == 2700.0 and sobre["data"]["actualizado"] is False


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


def test_chapa_es_soportada(cli, app_falsa):
    chapa = _pieza(app_falsa, tipo=4, nombre="Chapa.psm")
    chapa.fisicas_calculadas = GUARDADAS
    chapa.densidad_calculada = 2700.0

    r, sobre = cli("mass", "--doc", "Chapa.psm")

    assert r.exit_code == 0 and sobre["data"]["masa"] == 5.4


def test_ensamble_actualiza_y_no_informa_area(cli, app_falsa):
    asm = app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3)

    r, sobre = cli("mass", "--doc", "Conj.asm")

    data = sobre["data"]
    assert r.exit_code == 0
    assert data["area"] is None and data["actualizado"] is True
    assert data["masa"] == pytest.approx(7.85)  # FISICAS_POR_DEFECTO
    assert len(data["ejes_principales"]) == 9
    assert asm.PhysicalProperties.actualizaciones == 1

    r, sobre = cli("mass", "--doc", "Conj.asm")
    assert sobre["data"]["actualizado"] is False
    assert asm.PhysicalProperties.actualizaciones == 1


def test_ensamble_con_density_no_esta_soportado(cli, app_falsa):
    app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3)

    r, sobre = cli("mass", "--density", "1000", "--doc", "Conj.asm")

    assert r.exit_code == 6 and sobre["error"]["code"] == "no_soportado"
    assert app_falsa.escrituras == []


class _PiezaConMaterial:
    def __init__(self, material: str) -> None:
        self.material = material


def _con_piezas(asm, *piezas):
    """Ocurrencias `(archivo, material)`; un material None deja la pieza sin abrir."""
    ocurrencias = []
    for n, (archivo, material) in enumerate(piezas, 1):
        ocurrencia = OcurrenciaFalsa(f"{archivo}:{n}", f"C:\\p\\{archivo}")
        if material is not None:
            ocurrencia.OccurrenceDocument = _PiezaConMaterial(material)
        ocurrencias.append(ocurrencia)
    asm.Occurrences = ColeccionFalsa(ocurrencias)


def test_ensamble_lista_las_piezas_sin_material_y_no_cambia_la_masa(cli, app_falsa):
    asm = app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3)
    _con_piezas(
        asm,
        ("A.par", "Acero"),
        ("B.par", ""),
        ("B.par", ""),
        ("C.par", "Aluminio"),
        ("D.par", None),
    )

    r, sobre = cli("mass", "--doc", "Conj.asm")

    data = sobre["data"]
    assert r.exit_code == 0
    assert data["masa"] == pytest.approx(7.85)
    assert data["piezas_sin_material"] == [{"archivo": "C:\\p\\B.par", "cantidad": 2}]
    assert "1 pieza(s)" in data["advertencia"]


def test_ensamble_con_todas_las_piezas_con_material_no_advierte(cli, app_falsa):
    asm = app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3)
    _con_piezas(asm, ("A.par", "Acero"))

    r, sobre = cli("mass", "--doc", "Conj.asm")

    assert r.exit_code == 0
    assert sobre["data"]["piezas_sin_material"] == []
    assert "advertencia" not in sobre["data"]


def test_ensamble_baja_a_los_subensambles(cli, app_falsa):
    asm = app_falsa.agregar_documento("Conj.asm", ruta="C:\\p\\Conj.asm", tipo=3)
    hoja = OcurrenciaFalsa("P:1", "C:\\p\\P.par")
    hoja.OccurrenceDocument = _PiezaConMaterial("")
    asm.Occurrences = ColeccionFalsa([OcurrenciaFalsa("S:1", "C:\\p\\S.asm", hijos=[hoja])])

    r, sobre = cli("mass", "--doc", "Conj.asm")

    assert r.exit_code == 0
    assert sobre["data"]["piezas_sin_material"] == [{"archivo": "C:\\p\\P.par", "cantidad": 1}]


def test_pieza_no_suma_claves_de_material(cli, app_falsa, pieza):
    r, sobre = cli("mass")

    assert r.exit_code == 0
    assert "piezas_sin_material" not in sobre["data"]


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


def test_tupla_incompleta_da_error_com(cli, app_falsa, pieza, monkeypatch):
    monkeypatch.setattr(ModeloFalso, "GetPhysicalProperties", lambda self, **kwargs: (1.0, 2.0))
    r, sobre = cli("mass")
    assert r.exit_code == 4 and sobre["error"]["code"] == "com_error"
