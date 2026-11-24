"""Relaciones 3D de un ensamble: `asm relate mate|align|axial` y `asm relations list|delete`.

Verificado en vivo contra Solid Edge 2026 CE (226.00.01.04, 2026-11-23) con cajas de 50x30x20 mm y
cilindros de 20 mm de diámetro:

- Una relación se arma con `Relations3d.AddPlanar(ref1, ref2, normalsAligned, punto1, punto2)` o
  `AddAxial(ref1, ref2, normalsAligned)`. Las referencias salen de
  `AssemblyDocument.CreateReference(ocurrencia, cara)`, con la cara tomada de
  `OccurrenceDocument.Models.Item(1).Body.Faces(igQueryAll)` (el mismo orden que `edges list`).
- `AddPlanar` exige los dos puntos (sin ellos: "Invalid number of parameters"). Funcionan
  `Face.Geometry.GetRootPoint([0, 0, 0])` o el origen: no hace falta que caigan dentro de la cara.
- `normalsAligned=True` en `AddPlanar` es **mate** (caras enfrentadas, normales opuestas, las caras
  quedan en contacto) y `False` es **align** (caras coplanares con la misma normal). Al leer la
  relación, `NormalsAligned` devuelve lo contrario de lo que se pasó (mate lee False, align True).
- `AddAxial` deja coaxiales los dos cilindros con `True` o `False` (en ejes paralelos da lo mismo);
  se usa `True`.
- `PlanarRelation3d.Offset` se escribe después de crearla y mueve la ocurrencia suelta. Con `mate`,
  un offset positivo separa las caras; con `align`, +5 mm deja la cara a +5 mm de la otra.
- Con las dos ocurrencias fijas Solid Edge NO rechaza la relación: la crea con `Status` solved pero
  `DetailedStatus` igPlanarRelation `BetweenFixed` (4) y sin mover nada. Se detecta y se borra.
- Tipos: ground 1959028688, axial 1472929712, planar -2058948880. `Occurrence1`/`Occurrence2` solo
  existen en planar y axial; la ground trae `Occurrence`.
"""

from __future__ import annotations

from typing import Any

from se_cli.core import ensamble, unidades
from se_cli.core.acceso import exigir_tipo, items, leer, opcional
from se_cli.core.errors import (
    ArgumentoInvalido,
    DocNoEncontrado,
    ErrorCom,
    NoConectado,
    Ocupado,
)
from se_cli.core.modelado import parsear_longitud
from se_cli.core.redondeos import _TIPO_DE_CARA, _caras_del, _cuerpo

TIPOS = ("mate", "align", "axial")

_TIPO_GROUND = 1959028688  # igGroundRelation3d
_TIPO_AXIAL = 1472929712  # igAxialRelation3d
_TIPO_PLANAR = -2058948880  # igPlanarRelation3d

_RESUELTA = 1  # igRelation3dDetailedStatusSolved
_ENTRE_FIJAS = 4  # igRelation3dDetailedStatusBetweenFixed
_ESTADOS = {
    0: "desconocido",
    1: "resuelta",
    2: "suprimida",
    3: "entre_miembros_de_un_set",
    4: "entre_fijas",
    5: "insatisfecha",
    6: "geometria_faltante",
}

_TOLERANCIA = 1e-9


# --- Validación local (sin COM) ---------------------------------------------------------------


def parsear_cara(texto: str, opcion: str) -> tuple[str, int]:
    """`<occ>:<cara>` -> (selector de ocurrencia, índice de cara 1-based).

    Se corta en el último `:` porque los nombres de ocurrencia lo traen (`caja.par:1:3`).
    """
    ocurrencia, separador, cara = texto.rpartition(":")
    cara = cara.strip()
    if not separador or not ocurrencia.strip() or not cara.isdigit() or int(cara) < 1:
        raise ArgumentoInvalido(
            f"{opcion} tiene que ser <occ>:<cara> (ej. 1:3 o caja.par:2:5; cara desde 1, "
            f"como `se edges list`): {texto!r}."
        )
    return ocurrencia.strip(), int(cara)


def planificar_relate(tipo: str, a: str, b: str, offset: str | None) -> dict[str, Any]:
    clave = tipo.strip().lower()
    if clave not in TIPOS:
        raise ArgumentoInvalido(f"Tipo de relación inválido: {tipo!r}. Usá {', '.join(TIPOS)}.")
    if offset is not None and clave == "axial":
        raise ArgumentoInvalido("--offset solo vale para mate y align, no para axial.")
    ocurrencia_a, cara_a = parsear_cara(a, "--a")
    ocurrencia_b, cara_b = parsear_cara(b, "--b")
    return {
        "accion": "asm.relate",
        "tipo": clave,
        "a": {"ocurrencia": ocurrencia_a, "cara": cara_a},
        "b": {"ocurrencia": ocurrencia_b, "cara": cara_b},
        "offset_si": None
        if offset is None
        else parsear_longitud(offset, "--offset", positiva=False),
    }


def _indice_de_relacion(texto: str) -> int:
    clave = texto.strip()
    if not clave.isdigit() or int(clave) < 1:
        raise ArgumentoInvalido(
            f"El índice de la relación tiene que ser un entero desde 1 "
            f"(el `indice` de `asm relations list`): {texto!r}."
        )
    return int(clave)


def planificar_delete(indice: str) -> dict[str, Any]:
    return {"accion": "asm.relations.delete", "indice": _indice_de_relacion(indice)}


# --- Caras y referencias ----------------------------------------------------------------------


def _cara(doc: Any, selector: str, numero: int, tipo: str) -> tuple[int, Any, Any, dict[str, Any]]:
    """`(indice de la ocurrencia, ocurrencia, cara, info)` con la cara del cuerpo de su pieza."""
    indice, ocurrencia = ensamble._buscar(doc, selector)
    pieza = leer(lambda: ocurrencia.OccurrenceDocument)
    _, cuerpo = _cuerpo(pieza, "asm relate")
    caras = _caras_del(cuerpo)
    if numero > len(caras):
        raise DocNoEncontrado(
            f"No existe la cara {numero} de la ocurrencia {selector!r}: su cuerpo tiene "
            f"{len(caras)} (los índices son los de `se edges list` con esa pieza abierta).",
            details={"ocurrencia": indice, "cara": numero, "cantidad_caras": len(caras)},
        )
    cara = caras[numero - 1]
    codigo = opcional(lambda: int(cara.Geometry.Type))
    forma = _TIPO_DE_CARA.get(codigo, "otra") if codigo is not None else "otra"
    esperado = "cilindro" if tipo == "axial" else "plano"
    if forma not in (esperado, "otra"):
        raise ArgumentoInvalido(
            f"La cara {numero} de la ocurrencia {selector!r} es de tipo {forma}: "
            f"`{tipo}` necesita una cara de tipo {esperado}.",
            details={"ocurrencia": indice, "cara": numero, "tipo_de_cara": forma},
        )
    return indice, ocurrencia, cara, {"ocurrencia": indice, "cara": numero, "tipo_de_cara": forma}


def _punto_de_la_cara(cara: Any) -> tuple[float, float, float]:
    """Punto de apoyo del plano de la cara (`GetRootPoint`), en coordenadas de la pieza."""

    def raiz() -> tuple[float, float, float]:
        x, y, z = cara.Geometry.GetRootPoint([0.0, 0.0, 0.0])[:3]
        return float(x), float(y), float(z)

    return opcional(raiz) or (0.0, 0.0, 0.0)


# --- Lectura de las relaciones ----------------------------------------------------------------


def _ocurrencias_de(doc: Any, relacion: Any) -> list[dict[str, Any]]:
    """Ocurrencias que toca la relación, con su índice en `doc.Occurrences` si se encuentra."""
    nombres = []
    unica = opcional(lambda: relacion.Occurrence.Name)
    if unica is not None:
        nombres.append(str(unica))
    else:
        for atributo in ("Occurrence1", "Occurrence2"):
            nombre = opcional(lambda a=atributo: getattr(relacion, a).Name)
            if nombre is not None:
                nombres.append(str(nombre))
    todas = [str(opcional(lambda o=o: o.Name) or "") for o in items(leer(lambda: doc.Occurrences))]
    return [{"indice": todas.index(n) + 1 if n in todas else None, "nombre": n} for n in nombres]


def _tipo_legible(relacion: Any) -> tuple[str, int | None]:
    codigo = opcional(lambda: int(relacion.Type))
    if codigo == _TIPO_GROUND:
        return "ground", codigo
    if codigo == _TIPO_AXIAL:
        return "axial", codigo
    if codigo == _TIPO_PLANAR:
        # `NormalsAligned` se lee al revés de lo que se pasa a AddPlanar: False es mate.
        alineadas = opcional(lambda: bool(relacion.NormalsAligned))
        if alineadas is None:
            return "planar", codigo
        return ("align" if alineadas else "mate"), codigo
    return "otro", codigo


def describir_relacion(
    doc: Any, indice: int, relacion: Any, elegidas: dict[str, str] | None = None
) -> dict[str, Any]:
    """`{indice, tipo, tipo_codigo, ocurrencias, offset, estado}` de una relación."""
    largo = (elegidas or {}).get(unidades.LONGITUD, unidades.UNIDAD_SI[unidades.LONGITUD])
    tipo, codigo = _tipo_legible(relacion)
    offset = None
    if tipo in ("mate", "align", "planar"):
        crudo = opcional(lambda: float(relacion.Offset))
        offset = None if crudo is None else round(unidades.de_si(crudo, largo), 12) + 0.0
    detalle = opcional(lambda: int(relacion.DetailedStatus))
    return {
        "indice": indice,
        "tipo": tipo,
        "tipo_codigo": codigo,
        "ocurrencias": _ocurrencias_de(doc, relacion),
        "offset": offset,
        "estado": None if detalle is None else _ESTADOS.get(detalle, f"otro({detalle})"),
        "unidades": {"longitud": largo},
    }


def listar(doc: Any, elegidas: dict[str, str] | None = None) -> dict[str, Any]:
    """Relaciones 3D del ensamble (`asm relations list`), índice 1-based por orden de lectura."""
    exigir_tipo(doc, ("assembly",), "asm relations list")
    lista = [
        describir_relacion(doc, i, r, elegidas)
        for i, r in enumerate(items(leer(lambda: doc.Relations3d)), start=1)
    ]
    largo = (elegidas or {}).get(unidades.LONGITUD, unidades.UNIDAD_SI[unidades.LONGITUD])
    return {"cantidad": len(lista), "relaciones": lista, "unidades": {"longitud": largo}}


def _posicion_en(doc: Any, relacion: Any) -> int | None:
    """Posición 1-based de `relacion` en `Relations3d`; None si no se encuentra."""
    for i, candidata in enumerate(items(leer(lambda: doc.Relations3d)), start=1):
        if candidata == relacion:
            return i
    return None


def _borrar_sin_fallar(relacion: Any) -> None:
    try:
        leer(lambda: relacion.Delete())
    except (Ocupado, NoConectado):
        raise
    except Exception:  # noqa: BLE001 - es limpieza: el error original es el que importa
        pass


# --- Comandos ---------------------------------------------------------------------------------


def relacionar(
    doc: Any,
    tipo: str,
    a: str,
    b: str,
    offset: str | None,
    elegidas: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Creá una relación `mate`, `align` o `axial` entre una cara de cada ocurrencia.

    Si Solid Edge la deja sin resolver (p. ej. las dos ocurrencias fijas) se borra y es exit 4.
    """
    exigir_tipo(doc, ("assembly",), "asm relate")
    plan = planificar_relate(tipo, a, b, offset)
    tipo = plan["tipo"]
    sel_a, cara_a = plan["a"]["ocurrencia"], plan["a"]["cara"]
    sel_b, cara_b = plan["b"]["ocurrencia"], plan["b"]["cara"]
    ia, occ_a, cara_obj_a, info_a = _cara(doc, sel_a, cara_a, tipo)
    ib, occ_b, cara_obj_b, info_b = _cara(doc, sel_b, cara_b, tipo)
    if ia == ib:
        raise ArgumentoInvalido("--a y --b tienen que ser de ocurrencias distintas.")

    relaciones = leer(lambda: doc.Relations3d)
    antes = int(leer(lambda: relaciones.Count))
    nombre_a = str(opcional(lambda: occ_a.Name) or "")
    nombre_b = str(opcional(lambda: occ_b.Name) or "")
    fijas = [
        bool(ensamble._relaciones_fijas(doc, nombre_a)),
        bool(ensamble._relaciones_fijas(doc, nombre_b)),
    ]
    pista = (
        " Las dos ocurrencias están fijas: soltá una con `se asm ground <occ> --release`."
        if all(fijas)
        else ""
    )

    try:
        ref_a = leer(lambda: doc.CreateReference(occ_a, cara_obj_a))
        ref_b = leer(lambda: doc.CreateReference(occ_b, cara_obj_b))
        if tipo == "axial":
            relacion = leer(lambda: relaciones.AddAxial(ref_a, ref_b, True))
        else:
            punto_a, punto_b = _punto_de_la_cara(cara_obj_a), _punto_de_la_cara(cara_obj_b)
            relacion = leer(
                lambda: relaciones.AddPlanar(ref_a, ref_b, tipo == "mate", punto_a, punto_b)
            )
    except (Ocupado, NoConectado, ArgumentoInvalido, DocNoEncontrado):
        raise
    except Exception as error:  # noqa: BLE001
        raise ErrorCom(
            f"Solid Edge rechazó la relación {tipo}: {error}.{pista}",
            details={"a": info_a, "b": info_b},
        ) from error

    despues = int(leer(lambda: relaciones.Count))
    if despues != antes + 1:
        raise ErrorCom(
            f"Solid Edge no creó la relación {tipo}.{pista}",
            details={"antes": antes, "despues": despues, "a": info_a, "b": info_b},
        )

    if plan["offset_si"] is not None:
        valor = plan["offset_si"]
        try:
            leer(lambda: setattr(relacion, "Offset", valor))
        except (Ocupado, NoConectado):
            raise
        except Exception as error:  # noqa: BLE001
            _borrar_sin_fallar(relacion)
            raise ErrorCom(
                f"Solid Edge no aceptó el offset de {valor} m: {error}.{pista}",
                details={"offset_si": valor, "relacion_borrada": True},
            ) from error

    detalle = opcional(lambda: int(relacion.DetailedStatus))
    estado = opcional(lambda: int(relacion.Status))
    offset_leido = opcional(lambda: float(relacion.Offset)) if tipo != "axial" else None
    desviado = (
        plan["offset_si"] is not None
        and offset_leido is not None
        and abs(offset_leido - plan["offset_si"]) > _TOLERANCIA
    )
    if detalle != _RESUELTA or estado == 0 or desviado:
        _borrar_sin_fallar(relacion)
        motivo = _ESTADOS.get(detalle, "sin resolver") if detalle is not None else "sin resolver"
        extra = pista if detalle == _ENTRE_FIJAS else ""
        raise ErrorCom(
            f"La relación {tipo} quedó {motivo} y se borró.{extra}",
            details={
                "estado": motivo,
                "relacion_borrada": True,
                "a": info_a,
                "b": info_b,
            },
        )

    largo = (elegidas or {}).get(unidades.LONGITUD, unidades.UNIDAD_SI[unidades.LONGITUD])
    posicion = _posicion_en(doc, relacion) or despues
    return {
        "indice": posicion,
        "tipo": tipo,
        "a": info_a,
        "b": info_b,
        "offset": None if offset_leido is None else _convertido(offset_leido, largo),
        "estado": _ESTADOS.get(detalle, "resuelta"),
        "ocurrencias": [
            ensamble.describir(doc, ia, occ_a, elegidas),
            ensamble.describir(doc, ib, occ_b, elegidas),
        ],
        "unidades": {"longitud": largo},
    }


def _convertido(valor_si: float, unidad: str) -> float:
    return round(unidades.de_si(valor_si, unidad), 12) + 0.0


def borrar(doc: Any, selector: str) -> dict[str, Any]:
    """Borrá la relación `selector` (índice de `asm relations list`); inexistente es exit 5."""
    exigir_tipo(doc, ("assembly",), "asm relations delete")
    indice = _indice_de_relacion(selector)
    relaciones = leer(lambda: doc.Relations3d)
    antes = int(leer(lambda: relaciones.Count))
    if indice > antes:
        raise DocNoEncontrado(
            f"No existe la relación {indice}: el ensamble tiene {antes} "
            "(corré `se asm relations list`).",
            details={"indice": indice, "cantidad": antes},
        )
    relacion = leer(lambda: relaciones.Item(indice))
    descripcion = describir_relacion(doc, indice, relacion)
    leer(lambda: relacion.Delete())
    despues = int(leer(lambda: relaciones.Count))
    if despues != antes - 1:
        raise ErrorCom(
            f"Solid Edge no borró la relación {indice}.",
            details={"antes": antes, "despues": despues},
        )
    return {
        "indice": indice,
        "tipo": descripcion["tipo"],
        "ocurrencias": descripcion["ocurrencias"],
        "removed": True,
        "restantes": despues,
    }


__all__ = [
    "TIPOS",
    "borrar",
    "describir_relacion",
    "listar",
    "parsear_cara",
    "planificar_delete",
    "planificar_relate",
    "relacionar",
]
