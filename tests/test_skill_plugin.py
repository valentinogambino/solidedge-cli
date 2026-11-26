"""Valida el plugin de Claude Code (manifiestos y skill) sin Solid Edge, sin red y sin `claude`."""

import json
import re
import shlex
import tomllib
from pathlib import Path

import pytest
import typer.main

from se_cli.cli import app

RAIZ = Path(__file__).resolve().parent.parent
PLUGIN_JSON = RAIZ / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = RAIZ / ".claude-plugin" / "marketplace.json"
CARPETA_SKILL = RAIZ / "skills" / "solidedge-cli"
SKILL_MD = CARPETA_SKILL / "SKILL.md"
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OPCIONES_GLOBALES_CON_VALOR = {"--timeout"}
OPCIONES_GLOBALES = {"--json", "--readonly", "--dry-run", "--version"}


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _frontmatter(texto: str) -> dict[str, str]:
    """Parser mínimo de `clave: valor` (valores de una línea, con o sin comillas simples)."""
    lineas = texto.splitlines()
    assert lineas and lineas[0] == "---", "SKILL.md tiene que empezar con frontmatter ---"
    fin = lineas.index("---", 1)
    campos: dict[str, str] = {}
    for linea in lineas[1:fin]:
        clave, separador, valor = linea.partition(":")
        assert separador, f"línea de frontmatter sin ':': {linea!r}"
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] == "'":
            valor = valor[1:-1].replace("''", "'")
        elif len(valor) >= 2 and valor[0] == valor[-1] == '"':
            valor = valor[1:-1]
        campos[clave.strip()] = valor
    return campos


def test_manifiestos_parsean_y_tienen_los_campos_obligatorios():
    plugin = _json(PLUGIN_JSON)
    marketplace = _json(MARKETPLACE_JSON)
    assert plugin["name"]
    assert plugin["description"]
    assert plugin["author"]["name"]
    assert marketplace["name"]
    assert marketplace["owner"]["name"]
    assert marketplace["plugins"]


def test_version_del_plugin_coincide_con_la_de_pyproject():
    version = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert _json(PLUGIN_JSON)["version"] == version
    assert _json(MARKETPLACE_JSON)["plugins"][0]["version"] == version


def test_nombre_del_plugin_coincide_y_es_kebab_case():
    plugin = _json(PLUGIN_JSON)
    entrada = _json(MARKETPLACE_JSON)["plugins"][0]
    assert plugin["name"] == entrada["name"]
    assert KEBAB.match(plugin["name"])
    assert KEBAB.match(_json(MARKETPLACE_JSON)["name"])


def test_el_plugin_es_el_repo_entero():
    marketplace = _json(MARKETPLACE_JSON)
    assert len(marketplace["plugins"]) == 1
    assert marketplace["plugins"][0]["source"] == "./"


def test_frontmatter_de_la_skill():
    campos = _frontmatter(SKILL_MD.read_text(encoding="utf-8"))
    nombre = campos["name"]
    assert nombre == CARPETA_SKILL.name
    assert len(nombre) <= 64
    assert re.fullmatch(r"[a-z0-9-]+", nombre)
    descripcion = campos["description"]
    assert descripcion.strip()
    assert len(descripcion) <= 1024
    assert "<" not in descripcion and ">" not in descripcion


def test_skill_md_menos_de_500_lineas():
    assert len(SKILL_MD.read_text(encoding="utf-8").splitlines()) < 500


def _archivos_de_la_skill() -> list[Path]:
    return [SKILL_MD, *sorted((CARPETA_SKILL / "reference").glob("*.md"))]


@pytest.mark.parametrize("archivo", _archivos_de_la_skill(), ids=lambda p: p.name)
def test_enlaces_relativos_apuntan_a_archivos_existentes(archivo: Path):
    texto = archivo.read_text(encoding="utf-8")
    texto = re.sub(r"```.*?```", "", texto, flags=re.DOTALL)
    for destino in re.findall(r"\]\(([^)\s]+)\)", texto):
        if re.match(r"^[a-z][a-z0-9+.-]*:", destino) or destino.startswith("#"):
            continue
        ruta = destino.split("#", 1)[0]
        assert (archivo.parent / ruta).exists(), f"{archivo.name}: enlace roto a {destino}"


def _comandos_citados() -> list[tuple[str, tuple[str, ...]]]:
    """Cada `se ...` de los bloques de código: (archivo, palabras candidatas a comando)."""
    citados = []
    for archivo in _archivos_de_la_skill():
        texto = archivo.read_text(encoding="utf-8")
        for bloque in re.findall(r"```[^\n]*\n(.*?)```", texto, flags=re.DOTALL):
            for linea in bloque.splitlines():
                linea = linea.split("#", 1)[0].strip()
                if not re.match(r"^se\s", linea):
                    continue
                try:
                    tokens = shlex.split(linea, posix=False)[1:]
                except ValueError:
                    continue
                palabras = []
                saltar = False
                for token in tokens:
                    if saltar:
                        saltar = False
                    elif token in OPCIONES_GLOBALES_CON_VALOR:
                        saltar = True
                    elif token in OPCIONES_GLOBALES:
                        continue
                    elif re.fullmatch(r"[a-z][a-z-]*", token):
                        palabras.append(token)
                    else:
                        break
                citados.append((archivo.name, tuple(palabras)))
    return citados


def _resuelve(palabras: tuple[str, ...]) -> bool:
    """La primera palabra tiene que ser un comando o grupo de `se`; si es grupo, la segunda un
    subcomando. En un comando simple lo que sigue es un argumento y no se valida."""
    nodo = typer.main.get_command(app)
    for palabra in palabras[:2]:
        comandos = getattr(nodo, "commands", None)
        if comandos is None:
            return True
        if palabra not in comandos:
            return False
        nodo = comandos[palabra]
    return True


def test_hay_comandos_citados_en_la_skill():
    assert len(_comandos_citados()) > 20


@pytest.mark.parametrize(
    ("archivo", "palabras"), sorted(set(_comandos_citados())), ids=lambda v: str(v)
)
def test_los_comandos_citados_existen_en_la_app(archivo: str, palabras: tuple[str, ...]):
    assert palabras, f"{archivo}: `se` sin comando"
    assert _resuelve(palabras), f"{archivo}: `se {' '.join(palabras)}` no existe en la app Typer"
