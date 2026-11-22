from importlib.metadata import version

from typer.testing import CliRunner

from se_cli import __version__
from se_cli.cli import app


def test_version():
    resultado = CliRunner().invoke(app, ["--version"])

    assert resultado.exit_code == 0
    assert resultado.stdout.strip() == __version__ == version("solidedge-cli")
