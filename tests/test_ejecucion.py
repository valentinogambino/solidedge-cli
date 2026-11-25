"""Plomería de la CLI: opciones globales y ejecución uniforme, con un comando de prueba."""

import json

import pytest
import typer
from typer.testing import CliRunner

from se_cli import __version__, ejecucion
from se_cli.cli import app as app_real
from se_cli.core.errors import DocNoEncontrado, NoConectado, SeError

runner = CliRunner()


class SesionEspia:
    def __init__(self):
        self.conectada = False
        self.cerrada = False

    def conectar(self, lanzar=False):
        self.conectada = True
        return {}

    def cerrar(self):
        self.cerrada = True


@pytest.fixture
def espia(monkeypatch):
    sesion = SesionEspia()
    monkeypatch.setattr(ejecucion, "crear_sesion", lambda: sesion)
    return sesion


def invocar(comando, *args, funcion=None, modifica=False, plan=None, conectar=True):
    prueba = typer.Typer()

    @prueba.callback()
    def principal(
        ctx: typer.Context,
        json: bool = typer.Option(False, "--json"),
        readonly: bool = typer.Option(False, "--readonly"),
        dry_run: bool = typer.Option(False, "--dry-run"),
    ):
        ctx.obj = ejecucion.Opciones(json=json, readonly=readonly, dry_run=dry_run)

    @prueba.command("x")
    def x(ctx: typer.Context):
        ejecucion.ejecutar(
            ctx,
            funcion or (lambda s: {"hola": "mundo"}),
            modifica=modifica,
            plan=plan,
            conectar=conectar,
        )

    return runner.invoke(prueba, [*args, "x"])


def test_camino_feliz_json(espia):
    r = invocar("x", "--json")
    assert r.exit_code == 0
    assert json.loads(r.stdout) == {"ok": True, "data": {"hola": "mundo"}, "error": None}
    assert espia.conectada and espia.cerrada


def test_sin_conectar_si_se_pide(espia):
    invocar("x", "--json", conectar=False)
    assert not espia.conectada and espia.cerrada


@pytest.mark.parametrize(
    ("error", "codigo", "exit_code"),
    [
        (NoConectado("no hay"), "no_conectado", 3),
        (DocNoEncontrado("falta"), "doc_no_encontrado", 5),
        (ValueError("raro"), "interno", 1),
    ],
)
def test_errores_json_y_exit_code(espia, error, codigo, exit_code):
    def falla(_):
        raise error

    r = invocar("x", "--json", funcion=falla)
    assert r.exit_code == exit_code
    sobre = json.loads(r.stdout)
    assert sobre["ok"] is False and sobre["data"] is None
    assert sobre["error"]["code"] == codigo
    assert espia.cerrada


def test_error_humano_va_a_stderr(espia):
    def falla(_):
        raise NoConectado("No hay una instancia.")

    r = invocar("x", funcion=falla)
    assert r.exit_code == 3
    assert "No hay una instancia." in r.stderr
    assert "No hay una instancia." not in r.stdout


def test_error_previo_a_conectar_cierra_bien(monkeypatch):
    def rota():
        raise SeError("no pudo crear")

    monkeypatch.setattr(ejecucion, "crear_sesion", rota)
    r = invocar("x", "--json")
    assert r.exit_code == 1
    assert json.loads(r.stdout)["error"]["code"] == "interno"


def test_readonly_bloquea_lo_que_modifica(espia):
    r = invocar("x", "--json", "--readonly", modifica=True)
    assert r.exit_code == 6
    assert json.loads(r.stdout)["error"]["code"] == "solo_lectura"
    assert not espia.conectada


def test_readonly_no_bloquea_lectura(espia):
    assert invocar("x", "--json", "--readonly").exit_code == 0


def test_dry_run_informa_sin_conectar(espia):
    r = invocar("x", "--json", "--dry-run", modifica=True, plan=lambda: {"accion": "borrar"})
    assert r.exit_code == 0
    assert json.loads(r.stdout)["data"] == {"dry_run": True, "accion": "borrar"}
    assert not espia.conectada


def test_dry_run_valida_con_plan(espia):
    def plan():
        raise DocNoEncontrado("no existe")

    r = invocar("x", "--json", "--dry-run", modifica=True, plan=plan)
    assert r.exit_code == 5


def test_modo_humano_imprime_tabla(espia):
    r = invocar("x")
    assert r.exit_code == 0
    assert "hola" in r.stdout and "mundo" in r.stdout


def test_version():
    r = runner.invoke(app_real, ["--version"])
    assert r.exit_code == 0 and __version__ in r.stdout


@pytest.mark.parametrize("valor", ["0", "-1", "abc", "nan", "inf", "3601"])
def test_timeout_cli_invalido(cli, valor):
    r, sobre = cli("--timeout", valor, "status")
    assert r.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"


def test_timeout_cli_entorno_y_flag(cli, sesion, monkeypatch):
    monkeypatch.setenv("SE_TIMEOUT", "abc")
    r, sobre = cli("status")
    assert r.exit_code == 2
    assert sobre["error"]["code"] == "argumento_invalido"

    r, _ = cli("--timeout", "4", "status")
    assert r.exit_code == 0
    assert sesion.plazo == 4

    monkeypatch.setenv("SE_TIMEOUT", "3")
    r, _ = cli("status")
    assert r.exit_code == 0
    assert sesion.plazo == 3

    monkeypatch.setenv("SE_TIMEOUT", "")
    r, _ = cli("status")
    assert r.exit_code == 0
    assert sesion.plazo is None


def test_run_ignora_timeout(cli, sesion, tmp_path):
    archivo = tmp_path / "leer.py"
    archivo.write_text("def main(app, args):\n    return app.Version\n", encoding="utf8")
    r, _ = cli("--timeout", "0.001", "run", str(archivo), "--allow-scripts")
    assert r.exit_code == 0
    assert sesion.plazo is None


@pytest.mark.parametrize("abandona", [False, True])
def test_timeout_cli_bloqueado(cli, app_falsa, sta, monkeypatch, abandona):
    from se_cli import ejecucion
    from se_cli.core import sta as modulo_sta

    salidas = []
    monkeypatch.setattr(modulo_sta, "CANCELAR_POR_COM", not abandona)
    monkeypatch.setattr(ejecucion.os, "_exit", salidas.append)
    monkeypatch.setattr(sta, "_cancelar", lambda _: app_falsa.bloqueo.cancelar())
    app_falsa.bloqueo.bloquear("Version")
    try:
        r, sobre = cli("--timeout", "0.3", "status")
        assert r.exit_code == 7
        assert sobre["error"]["code"] == "ocupado"
        assert sobre["error"]["details"]["motivo"] == "timeout"
        assert sobre["error"]["details"]["cancelacion"] == (
            "abandonada" if abandona else "cancelada"
        )
        assert salidas == ([7] if abandona else [])
    finally:
        app_falsa.bloqueo.soltar()
