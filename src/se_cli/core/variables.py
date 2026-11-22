"""Variables y cotas de un documento (`doc.Variables`).

Todo valor numérico vive en SI en la API (los ángulos en radianes); acá se convierte a la
unidad pedida para mostrar y se convierte a SI antes de escribir.

Gotchas de Solid Edge 2026 que respeta este módulo:
- `Variables.Query` necesita el `VarType` explícito (una constante de `seVariableTypeConstants`):
  con 0 devuelve siempre una colección vacía. No hay un "todos", así que se consulta cada tipo y
  se unen los resultados. `NamedBy` va con `seVariableNameByBoth`: con `ByUser` no aparecen las
  cotas.
- Una cota sin nombre de usuario solo se encuentra por `Query`, no por `Item(i)`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from se_cli.core import unidades
from se_cli.core.acceso import items, leer, opcional
from se_cli.core.constants import UnitTypeConstants, VariableNameBy, seVariableTypeConstants
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    NoConectado,
    Ocupado,
    SoloLectura,
    traducir,
)

# Tipos a consultar y cuál de ellos son las cotas (dimensions).
_TIPOS_DE_CONSULTA = (
    seVariableTypeConstants.seVariableType_UserDefined,
    seVariableTypeConstants.seVariableType_Dimension,
    seVariableTypeConstants.seVariableType_Simulation,
    seVariableTypeConstants.seVariableType_Text,
)
_TIPO_COTA = seVariableTypeConstants.seVariableType_Dimension

# `UnitsType` → dimensión de `core/unidades.py` (las demás no se convierten).
_DIMENSION_POR_TIPO: dict[int, str] = {
    int(UnitTypeConstants.igUnitDistance): unidades.LONGITUD,
    int(UnitTypeConstants.igUnitAngle): unidades.ANGULO,
    int(UnitTypeConstants.igUnitMass): unidades.MASA,
}

_PREFIJO = "igUnit"


def _nombre_de_tipo_unidad(codigo: Any) -> str | None:
    """`distance`, `angle`, `mass`, `scalar`... según `UnitTypeConstants` (entero si no hay)."""
    if codigo is None:
        return None
    try:
        nombre = UnitTypeConstants(int(codigo)).name
    except (TypeError, ValueError):
        return str(codigo)
    return nombre.removeprefix(_PREFIJO).lower()


def codigo_de_tipo_unidad(nombre: str) -> int:
    """Código de `UnitTypeConstants` para `--unit-type distance|angle|mass|scalar|...`."""
    clave = nombre.strip().lower()
    for miembro in UnitTypeConstants:
        if miembro.name.removeprefix(_PREFIJO).lower() == clave:
            return int(miembro)
    validos = [m.name.removeprefix(_PREFIJO).lower() for m in UnitTypeConstants]
    raise ArgumentoInvalido(
        f"Tipo de unidad inválido: {nombre!r}. Algunos válidos: distance, angle, mass, scalar, "
        "area, volume, density.",
        details={"validos": validos},
    )


# --- Lectura -------------------------------------------------------------------------------


def _nombre(var: Any, posicion: int = 0) -> str:
    for atributo in ("DisplayName", "Name"):
        texto = opcional(lambda atributo=atributo: getattr(var, atributo))
        if isinstance(texto, str) and texto.strip():
            return texto
    return f"var_{posicion}"


def _formula(var: Any) -> str | None:
    texto = opcional(lambda: var.Formula)
    return texto if isinstance(texto, str) and texto.strip() else None


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _describir(var: Any, es_cota: bool, elegidas: dict[str, str], posicion: int = 0) -> dict:
    """Datos planos de una variable; lo que la API no entrega queda en `None`."""
    valor_si = opcional(lambda: var.Value)
    codigo = opcional(lambda: var.UnitsType)
    dimension = _DIMENSION_POR_TIPO.get(codigo) if isinstance(codigo, int) else None
    valor, unidad = valor_si, None
    if _es_numero(valor_si):
        valor_si = float(valor_si)
        valor, unidad = unidades.convertir(valor_si, dimension, elegidas)
    solo_lectura = opcional(lambda: var.IsReadOnly)
    return {
        "nombre": _nombre(var, posicion),
        "valor_si": valor_si,
        "valor": valor,
        "unidad": unidad,
        "formula": _formula(var),
        "tipo_unidad": _nombre_de_tipo_unidad(codigo),
        "es_cota": es_cota,
        "solo_lectura": None if solo_lectura is None else bool(solo_lectura),
    }


def _consultar(variables: Any, patron: str) -> list[tuple[Any, bool]]:
    """`[(variable, es_cota)]` de todos los tipos, sin repetir nombres (ver gotchas arriba)."""
    encontradas: list[tuple[Any, bool]] = []
    vistos: set[str] = set()
    errores: list[BaseException] = []
    for tipo in _TIPOS_DE_CONSULTA:
        try:
            coleccion = leer(
                lambda tipo=tipo: variables.Query(
                    patron, int(VariableNameBy.seVariableNameByBoth), int(tipo), True
                )
            )
        except (Ocupado, NoConectado):
            raise
        except Exception as error:  # noqa: BLE001 - un tipo puede fallar y los demás no
            errores.append(error)
            continue
        if coleccion is None:
            continue
        for var in items(coleccion):
            clave = _nombre(var, len(encontradas) + 1).casefold()
            if clave in vistos:
                continue
            vistos.add(clave)
            encontradas.append((var, tipo == _TIPO_COTA))
    if len(errores) == len(_TIPOS_DE_CONSULTA):
        raise traducir(errores[0])
    return encontradas


def _buscar(doc: Any, nombre: str) -> tuple[Any, bool]:
    """Variable por nombre exacto (sin distinguir mayúsculas), o `DocNoEncontrado` (exit 5)."""
    variables = leer(lambda: doc.Variables)
    buscado = nombre.strip().casefold()
    for var, es_cota in _consultar(variables, nombre.strip()):
        if _nombre(var).casefold() == buscado:
            return var, es_cota
    raise DocNoEncontrado(
        f"No existe la variable {nombre!r} en el documento.", details={"nombre": nombre}
    )


def _existe(doc: Any, nombre: str) -> bool:
    try:
        _buscar(doc, nombre)
    except DocNoEncontrado:
        return False
    return True


def listar(doc: Any, filtro: str | None = None, elegidas: dict[str, str] | None = None) -> dict:
    """Variables y cotas que coinciden con `filtro` (comodines `*` y `?`; por defecto todas)."""
    variables = leer(lambda: doc.Variables)
    patron = filtro.strip() if filtro and filtro.strip() else "*"
    lista = [
        _describir(var, es_cota, elegidas or {}, i)
        for i, (var, es_cota) in enumerate(_consultar(variables, patron), start=1)
    ]
    return {"cantidad": len(lista), "variables": lista}


def obtener(doc: Any, nombre: str, elegidas: dict[str, str] | None = None) -> dict:
    """Una variable por nombre; inexistente da exit 5."""
    var, es_cota = _buscar(doc, nombre)
    return _describir(var, es_cota, elegidas or {})


# --- Escritura -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Orden:
    """Qué escribir en `vars set`: un valor ya en SI o una fórmula."""

    cantidad: unidades.Cantidad | None
    formula: str | None


def preparar_set(valor: str | None, formula: str | None) -> Orden:
    """Validá los argumentos de `vars set` sin tocar COM (exit 2 si algo no cierra)."""
    if (valor is None) == (formula is None):
        raise ArgumentoInvalido("Indicá un valor o una fórmula con --formula, no ambos ni ninguno.")
    if formula is not None:
        if not formula.strip():
            raise ArgumentoInvalido("La fórmula está vacía.")
        return Orden(None, formula.strip())
    return Orden(unidades.parsear_valor(valor or ""), None)


def parsear_nueva(
    nombre: str, valor: str, tipo_unidad: str | None
) -> tuple[unidades.Cantidad, int | None]:
    """Validá `vars add` sin COM: `(cantidad, codigo_de_UnitsType | None)`.

    Sin `--unit-type` el tipo se deduce de la unidad del valor (`120mm` → distance).
    """
    if not nombre.strip():
        raise ArgumentoInvalido("El nombre de la variable está vacío.")
    cantidad = unidades.parsear_valor(valor)
    deducido = None
    if cantidad.dimension is not None:
        deducido = {
            unidades.LONGITUD: UnitTypeConstants.igUnitDistance,
            unidades.ANGULO: UnitTypeConstants.igUnitAngle,
            unidades.MASA: UnitTypeConstants.igUnitMass,
        }[cantidad.dimension]
    if tipo_unidad is None:
        return cantidad, None if deducido is None else int(deducido)
    codigo = codigo_de_tipo_unidad(tipo_unidad)
    if deducido is not None and codigo != int(deducido):
        raise ArgumentoInvalido(
            f"El valor {valor!r} es de {cantidad.dimension} y --unit-type es {tipo_unidad!r}."
        )
    return cantidad, codigo


def _exigir_dimension(var: Any, cantidad: unidades.Cantidad, nombre: str) -> None:
    """Un valor con unidad solo entra en una variable de esa misma dimensión."""
    if cantidad.dimension is None:
        return
    codigo = opcional(lambda: var.UnitsType)
    dimension = _DIMENSION_POR_TIPO.get(codigo) if isinstance(codigo, int) else None
    if dimension != cantidad.dimension:
        raise ArgumentoInvalido(
            f"{nombre} es de tipo {_nombre_de_tipo_unidad(codigo) or 'desconocido'}: no "
            f"admite un valor en {cantidad.unidad} ({cantidad.dimension}).",
            details={"nombre": nombre},
        )


def _escribir_valor(var: Any, valor_si: float) -> None:
    """Única función que asigna `Variable.Value` (en SI). Ajustar acá si se prueba en vivo."""
    leer(lambda: setattr(var, "Value", valor_si))


def _escribir_formula(var: Any, formula: str) -> None:
    """Única función que asigna `Variable.Formula`."""
    leer(lambda: setattr(var, "Formula", formula))


def modificar(
    doc: Any,
    nombre: str,
    orden: Orden,
    *,
    force: bool = False,
    elegidas: dict[str, str] | None = None,
) -> dict:
    """Cambiá una variable. Devuelve `{nombre, antes, despues}`.

    Una variable de solo lectura, o gobernada por una fórmula cuando se quiere poner un valor,
    se rechaza (exit 6) salvo `force`, y con `force` la API tiene la última palabra.
    """
    var, es_cota = _buscar(doc, nombre)
    elegidas = elegidas or {}
    antes = _describir(var, es_cota, elegidas)
    real = antes["nombre"]
    if antes["solo_lectura"] and not force:
        raise SoloLectura(
            f"{real} es de solo lectura. Usá --force para intentarlo igual.",
            details={"nombre": real},
        )
    if orden.formula is None and antes["formula"] and not force:
        raise SoloLectura(
            f"{real} está gobernada por la fórmula {antes['formula']!r}. Usá --formula para "
            "cambiarla o --force para pisarla con un valor.",
            details={"nombre": real, "formula": antes["formula"]},
        )
    if orden.cantidad is not None:
        _exigir_dimension(var, orden.cantidad, real)
        _escribir_valor(var, orden.cantidad.valor_si)
    else:
        _escribir_formula(var, orden.formula or "")
    despues = _describir(var, es_cota, elegidas)
    return {"nombre": real, "antes": _resumen(antes), "despues": _resumen(despues)}


def _resumen(datos: dict) -> dict:
    return {clave: datos[clave] for clave in ("valor_si", "valor", "unidad", "formula")}


def agregar(
    doc: Any,
    nombre: str,
    cantidad: unidades.Cantidad,
    codigo_unidad: int | None,
    elegidas: dict[str, str] | None = None,
) -> dict:
    """Creá una variable de usuario; si ya existe da exit 6 y no toca nada."""
    nombre = nombre.strip()
    if _existe(doc, nombre):
        raise SoloLectura(
            f"Ya existe la variable {nombre!r}: usá `se vars set`.", details={"nombre": nombre}
        )
    variables = leer(lambda: doc.Variables)
    var = _crear(variables, nombre, codigo_unidad)
    _escribir_valor(var, cantidad.valor_si)
    return _describir(var, False, elegidas or {})


def _crear(variables: Any, nombre: str, codigo_unidad: int | None) -> Any:
    """Única función que llama a `Variables.Add(nombre, formula[, UnitsType])`.

    Se crea con la fórmula `"0"` y el valor real se asigna después en SI, porque un número
    pelado en una fórmula se interpreta en las unidades del documento y no en metros.
    """
    crear: Callable[[], Any]
    if codigo_unidad is None:
        crear = lambda: variables.Add(nombre, "0")  # noqa: E731
    else:
        crear = lambda: variables.Add(nombre, "0", codigo_unidad)  # noqa: E731
    return leer(crear)


__all__ = [
    "Orden",
    "agregar",
    "codigo_de_tipo_unidad",
    "listar",
    "modificar",
    "obtener",
    "parsear_nueva",
    "preparar_set",
]
