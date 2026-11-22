"""Generá `src/se_cli/core/constants.py` desde `constant.tlb` de Solid Edge.

Leer la typelib con `pythoncom.LoadTypeLib` no necesita Solid Edge abierto ni lo lanza.
La salida es determinista (enums ordenados por nombre, miembros en el orden de la typelib,
sin fechas), así que regenerar con la misma typelib da el mismo archivo.

El módulo generado guarda los datos en un dict y arma cada `IntEnum` recién cuando se lo
pide (`constants.DocumentTypeConstants`), porque crear los 745 enums al importar tarda
más de 0,5 s.

Uso:
    uv run python scripts/gen_constants.py [ruta/constant.tlb] [--salida ruta.py]
"""

from __future__ import annotations

import argparse
import keyword
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TLB_POR_DEFECTO = r"C:\Program Files\Siemens\Solid Edge 2026\Program\constant.tlb"
RAIZ = Path(__file__).resolve().parents[1]
SALIDA_POR_DEFECTO = RAIZ / "src" / "se_cli" / "core" / "constants.py"

TKIND_ENUM = 0
RESERVADOS = frozenset({"name", "value", "mro"})


@dataclass
class Enum:
    nombre: str
    miembros: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class Typelib:
    nombre: str
    version: str
    guid: str
    enums: list[Enum] = field(default_factory=list)


def leer_typelib(ruta: str, cargar: Callable[[str], Any] | None = None) -> Typelib:
    """Leé los enums de una typelib. `cargar` reemplaza a `pythoncom.LoadTypeLib` en tests."""
    if cargar is None:
        import pythoncom

        cargar = pythoncom.LoadTypeLib
    tlb = cargar(ruta)
    guid, _lcid, _sistema, mayor, menor, _flags = tlb.GetLibAttr()
    info = Typelib(
        nombre=tlb.GetDocumentation(-1)[0], version=f"{mayor}.{menor}", guid=str(guid).upper()
    )
    for indice in range(tlb.GetTypeInfoCount()):
        tipo = tlb.GetTypeInfo(indice)
        atributos = tipo.GetTypeAttr()
        if atributos.typekind != TKIND_ENUM:
            continue
        enum = Enum(nombre=tlb.GetDocumentation(indice)[0])
        for j in range(atributos.cVars):
            var = tipo.GetVarDesc(j)
            enum.miembros.append((tipo.GetNames(var.memid)[0], int(var.value)))
        info.enums.append(enum)
    return info


def identificador(nombre: str) -> str:
    """Hacé que `nombre` sea un identificador válido y seguro dentro de un IntEnum."""
    limpio = "".join(c if c.isalnum() or c == "_" else "_" for c in nombre)
    if not limpio or not limpio.isidentifier():
        limpio = f"n_{limpio}"
    if keyword.iskeyword(limpio) or limpio.startswith("_") or limpio in RESERVADOS:
        limpio = f"n_{limpio}"
    return limpio


CABECERA = '''"""Constantes de Solid Edge, generadas desde la typelib {nombre} {version}.

GUID de la typelib: {guid}
Archivo generado por scripts/gen_constants.py, no editar a mano. Para regenerarlo:
    uv run python scripts/gen_constants.py

Uso:
    from se_cli.core.constants import DocumentTypeConstants, valor
    DocumentTypeConstants.igPartDocument
    valor("igProfileClosed")
"""

from enum import IntEnum
from typing import Any

from se_cli.core.errors import ArgumentoInvalido

_DATOS: dict[str, dict[str, int]] = {
'''

PIE = '''}

_INDICE: dict[str, int] = {}


def nombres_de_enums() -> tuple[str, ...]:
    """Nombres de todos los enums, en orden alfabético."""
    return tuple(_DATOS)


def __getattr__(nombre: str) -> Any:
    """Armá el `IntEnum` pedido la primera vez y dejalo cacheado en el módulo."""
    if nombre not in _DATOS:
        raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
    enum = IntEnum(nombre, _DATOS[nombre], module=__name__)
    globals()[nombre] = enum
    return enum


def valor(nombre: str) -> int:
    """Devolvé el valor de una constante por nombre, ej. `valor("igProfileClosed")`.

    Levanta `ArgumentoInvalido` (exit 2) si no existe, con sugerencias parecidas.
    """
    if not _INDICE:
        for miembros in _DATOS.values():
            for miembro, numero in miembros.items():
                _INDICE.setdefault(miembro, numero)
    try:
        return _INDICE[nombre]
    except KeyError:
        from difflib import get_close_matches

        parecidos = get_close_matches(nombre, _INDICE, n=3)
        pista = f" ¿Quisiste decir {', '.join(parecidos)}?" if parecidos else ""
        raise ArgumentoInvalido(f"No existe la constante {nombre!r}.{pista}") from None
'''


def generar(info: Typelib) -> str:
    """Devolvé el código del módulo de constantes, con formato compatible con ruff."""
    cabecera = (
        CABECERA.replace("{nombre}", info.nombre)
        .replace("{version}", info.version)
        .replace("{guid}", info.guid)
    )
    lineas = [cabecera]
    for enum in sorted(info.enums, key=lambda enum: enum.nombre):
        lineas.append(f'    "{identificador(enum.nombre)}": {{\n')
        vistos: set[str] = set()
        for miembro, numero in enum.miembros:
            nombre = identificador(miembro)
            if nombre in vistos:
                continue
            vistos.add(nombre)
            lineas.append(f'        "{nombre}": {numero},\n')
        lineas.append("    },\n")
    return "".join(lineas) + PIE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tlb", nargs="?", default=TLB_POR_DEFECTO, help="Ruta a constant.tlb.")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    args = parser.parse_args(argv)
    if not Path(args.tlb).is_file():
        print(f"No existe la typelib: {args.tlb}", file=sys.stderr)
        return 1
    info = leer_typelib(args.tlb)
    args.salida.write_text(generar(info), encoding="utf-8", newline="\n")
    cantidad = sum(len(enum.miembros) for enum in info.enums)
    print(f"{info.nombre} {info.version}: {len(info.enums)} enums, {cantidad} constantes")
    print(f"Escrito en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
