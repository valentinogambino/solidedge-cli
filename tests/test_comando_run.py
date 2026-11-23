"""`se run` sobre el COM falso."""

import pytest

SCRIPT_OK = """
def main(app, args):
    return {"version": app.Version, "documentos": app.Documents.Count, "args": args}
"""

MARCA = "tocado"


@pytest.fixture
def script(tmp_path):
    ruta = tmp_path / "leer.py"
    ruta.write_text(SCRIPT_OK, encoding="utf-8")
    return ruta


def test_sin_allow_scripts_siempre_da_exit_6_sin_leer_el_archivo(cli, app_falsa, tmp_path):
    efecto = tmp_path / "efecto.txt"
    ruta = tmp_path / "malo.py"
    ruta.write_text(f"open({str(efecto)!r}, 'w').write('x')\ndef main(a, b): pass\n")

    r, sobre = cli("run", str(ruta))

    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"
    assert "--allow-scripts" in sobre["error"]["message"]
    assert not efecto.exists() and app_falsa.registro == []


def test_sin_allow_scripts_falla_aunque_el_archivo_no_exista_o_haya_dry_run(cli, tmp_path):
    r, _ = cli("run", str(tmp_path / "nada.py"))
    assert r.exit_code == 6
    r, _ = cli.con("--dry-run", "run", str(tmp_path / "nada.py"))
    assert r.exit_code == 6


def test_con_allow_scripts_corre_main_y_devuelve_el_resultado(cli, app_falsa, script):
    app_falsa.agregar_documento("A.par")

    r, sobre = cli("run", str(script), "--allow-scripts", "--", "uno", "dos")

    assert r.exit_code == 0, r.output
    assert sobre["data"] == {
        "script": str(script),
        "resultado": {"version": "226.00.00.00", "documentos": 1, "args": ["uno", "dos"]},
    }


def test_main_corre_dentro_del_hilo_sta(cli, sta, tmp_path):
    ruta = tmp_path / "hilo.py"
    ruta.write_text("import threading\ndef main(app, args):\n    return threading.get_ident()\n")
    r, sobre = cli("run", str(ruta), "--allow-scripts")
    assert r.exit_code == 0 and sobre["data"]["resultado"] == sta.ident


def test_resultado_con_objetos_no_planos_se_resume(cli, tmp_path):
    ruta = tmp_path / "obj.py"
    ruta.write_text("def main(app, args):\n    return {'doc': app, 'tupla': (1, 2)}\n")
    r, sobre = cli("run", str(ruta), "--allow-scripts")
    assert r.exit_code == 0
    assert isinstance(sobre["data"]["resultado"]["doc"], str)
    assert sobre["data"]["resultado"]["tupla"] == [1, 2]


def test_archivo_inexistente_da_exit_5(cli, tmp_path):
    r, sobre = cli("run", str(tmp_path / "nada.py"), "--allow-scripts")
    assert r.exit_code == 5 and sobre["error"]["code"] == "doc_no_encontrado"


def test_script_sin_main_da_exit_2(cli, tmp_path):
    ruta = tmp_path / "sinmain.py"
    ruta.write_text("x = 1\n")
    r, sobre = cli("run", str(ruta), "--allow-scripts")
    assert r.exit_code == 2 and "main" in sobre["error"]["message"]


def test_excepcion_del_script_da_exit_1_con_traceback(cli, tmp_path):
    ruta = tmp_path / "falla.py"
    ruta.write_text("def main(app, args):\n    return 1 / 0\n")
    r, sobre = cli("run", str(ruta), "--allow-scripts")
    assert r.exit_code == 1 and sobre["error"]["code"] == "interno"
    assert "ZeroDivisionError" in sobre["error"]["message"]
    assert "ZeroDivisionError" in sobre["error"]["details"]["traceback"]
    assert "falla.py" in sobre["error"]["details"]["traceback"]


def test_error_de_sintaxis_del_script_da_exit_1(cli, tmp_path):
    ruta = tmp_path / "roto.py"
    ruta.write_text("def main(:\n")
    r, sobre = cli("run", str(ruta), "--allow-scripts")
    assert r.exit_code == 1 and "SyntaxError" in sobre["error"]["details"]["traceback"]


def test_readonly_y_dry_run(cli, app_falsa, script):
    r, sobre = cli.con("--readonly", "run", str(script), "--allow-scripts")
    assert r.exit_code == 6 and sobre["error"]["code"] == "solo_lectura"

    r, sobre = cli.con("--dry-run", "run", str(script), "--allow-scripts", "--", "x")
    assert r.exit_code == 0
    assert sobre["data"] == {"dry_run": True, "accion": "run", "script": str(script), "args": ["x"]}
    assert app_falsa.registro == []


def test_sin_instancia_da_exit_3(cli_sin_instancia, script):
    r, sobre = cli_sin_instancia("run", str(script), "--allow-scripts")
    assert r.exit_code == 3 and sobre["error"]["code"] == "no_conectado"
