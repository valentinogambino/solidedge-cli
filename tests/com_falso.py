"""COM falso para tests: imita lo mínimo de `Application` sin Solid Edge ni pywin32."""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from typing import Any


class ComErrorFalso(Exception):
    """Imita `pywintypes.com_error`: `hresult` con signo, `strerror` y `excepinfo`."""

    def __init__(
        self,
        hresult: int,
        strerror: str = "",
        excepinfo: tuple | None = None,
        argerror: int | None = None,
    ) -> None:
        # pywin32 entrega el HRESULT como int con signo.
        self.hresult = hresult - 0x100000000 if hresult >= 0x80000000 else hresult
        self.strerror = strerror
        self.excepinfo = excepinfo
        self.argerror = argerror
        super().__init__(self.hresult, strerror, excepinfo, argerror)


def com_error(hresult: int, strerror: str = "Error", descripcion: str | None = None):
    """Armá un `ComErrorFalso`, con `excepinfo` si hay descripción."""
    excepinfo = (0, "SolidEdge", descripcion, None, 0, hresult) if descripcion else None
    return ComErrorFalso(hresult, strerror, excepinfo)


class _ConFallos:
    """Mixin: `fallar(nombre, *errores)` hace que los próximos accesos a `nombre` levanten."""

    def __init__(self) -> None:
        self._fallos: dict[str, list[BaseException]] = defaultdict(list)
        self.accesos: dict[str, int] = defaultdict(int)

    def fallar(self, nombre: str, *errores: BaseException) -> None:
        self._fallos[nombre].extend(errores)

    def _tocar(self, nombre: str) -> None:
        self.accesos[nombre] += 1
        if self._fallos[nombre]:
            raise self._fallos[nombre].pop(0)


# Llamadas COM que cambian el estado de Solid Edge o de un documento.
ESCRITURAS = frozenset(
    {
        "Documents.Add",
        "Documents.Open",
        "Save",
        "SaveAs",
        "SaveCopyAs",
        "Close",
        "Quit",
        "Dirty=",
        "Activate",
        "Variables.Add",
        "Variable.Value=",
        "Variable.Formula=",
        "Properties.Add",
        "Property.Value=",
        "ComputePhysicalPropertiesWithSpecifiedDensity",
    }
)


class DocumentoFalso(_ConFallos):
    """Documento falso. `registro` es la lista compartida donde se anota cada llamada."""

    def __init__(
        self,
        nombre: str = "Part1.par",
        *,
        ruta: str | None = None,
        tipo: int = 1,
        sucio: bool = False,
        solo_lectura: bool = False,
        registro: list | None = None,
    ) -> None:
        super().__init__()
        self.Name = nombre
        # Un documento nunca guardado tiene un FullName sin carpeta.
        self.FullName = ruta or nombre
        self.Type = tipo
        self._sucio = sucio
        self.ReadOnly = solo_lectura
        self.cerrado = False
        self.registro = registro if registro is not None else []
        self.coleccion: DocumentosFalsos | None = None
        # Datos del modelo (F3); cada test arma los que necesita.
        self.Variables = VariablesFalsas(self)
        self.Properties = ColeccionFalsa([])
        self.Occurrences = ColeccionFalsa([])
        self.Models = ColeccionFalsa([])
        self.DesignEdgebarFeatures = ColeccionFalsa([])
        self.fisicas_de_usuario: tuple | None = None
        self.fisicas = FISICAS_POR_DEFECTO
        # Exportación (F4): "escribir" deja un archivo con contenido, "nada" no escribe y
        # "vacio" lo deja en 0 bytes.
        self.modo_exportacion = "escribir"

    def GetUserPhysicalProperties(self) -> tuple:
        """Sin propiedades guardadas la llamada real falla (E_FAIL)."""
        self.registro.append(("GetUserPhysicalProperties", self.Name))
        if self.fisicas_de_usuario is None:
            raise com_error(0x80004005, "Error no especificado")
        return self.fisicas_de_usuario

    def ComputePhysicalPropertiesWithSpecifiedDensity(self, **kwargs: Any) -> tuple:
        """Cálculo de un ensamble: igual que el de un `Model`."""
        return calcular_fisicas(self, **kwargs)

    @property
    def Dirty(self) -> bool:
        self._tocar("Dirty")
        return self._sucio

    @Dirty.setter
    def Dirty(self, valor: bool) -> None:
        self.registro.append(("Dirty=", self.Name, valor))
        self._tocar("Dirty_set")
        self._sucio = valor

    def Save(self) -> None:
        self.registro.append(("Save", self.Name))
        self._tocar("Save")
        self._sucio = False

    def SaveAs(self, ruta: str) -> None:
        self.registro.append(("SaveAs", self.Name, ruta))
        self._tocar("SaveAs")
        with open(ruta, "wb") as archivo:
            archivo.write(b"falso")
        self.FullName = ruta
        self.Name = ruta.replace("\\", "/").rsplit("/", 1)[-1]
        self._sucio = False

    def SaveCopyAs(self, ruta: str) -> None:
        """Exporta por extensión sin reapuntar el documento (como la API real)."""
        self.registro.append(("SaveCopyAs", self.Name, ruta))
        self._tocar("SaveCopyAs")
        if self.modo_exportacion == "escribir":
            with open(ruta, "wb") as archivo:
                archivo.write(b"exportado")
        elif self.modo_exportacion == "vacio":
            open(ruta, "wb").close()

    def Close(self, guardar: bool = False) -> None:
        self.registro.append(("Close", self.Name, guardar))
        self._tocar("Close")
        self.cerrado = True
        if self.coleccion is not None:
            self.coleccion.quitar(self)

    def Activate(self) -> None:
        self.registro.append(("Activate", self.Name))
        self._tocar("Activate")
        if self.coleccion is not None:
            self.coleccion.activo = self


class ColeccionFalsa:
    """Colección COM genérica: `Count`, `Item(i)` (1-based) y `Item(nombre)`."""

    def __init__(self, elementos: list | None = None) -> None:
        self.elementos = list(elementos or [])

    @property
    def Count(self) -> int:
        return len(self.elementos)

    def Item(self, clave: int | str) -> Any:
        if isinstance(clave, str):
            for elemento in self.elementos:
                if getattr(elemento, "Name", None) == clave:
                    return elemento
            raise com_error(0x80020009, "Excepción", f"No existe {clave}")
        return self.elementos[clave - 1]


class VariableFalsa:
    """Variable o cota. `tipo` es el `seVariableTypeConstants` en el que `Query` la encuentra."""

    def __init__(
        self,
        nombre: str,
        valor: Any = 0.0,
        *,
        formula: str = "",
        unidad: int | None = 58,
        tipo: int = 1560616706,
        solo_lectura: bool = False,
    ) -> None:
        self.DisplayName = nombre
        self.Name = nombre
        self._valor = valor
        self._formula = formula
        self.UnitsType = unidad
        self.tipo = tipo
        self.IsReadOnly = solo_lectura
        self.doc: DocumentoFalso | None = None

    def _anotar(self, que: str, valor: Any) -> None:
        if self.doc is not None:
            self.doc.registro.append((que, self.DisplayName, valor))

    @property
    def Value(self) -> Any:
        return self._valor

    @Value.setter
    def Value(self, valor: Any) -> None:
        self._anotar("Variable.Value=", valor)
        self._valor = valor
        self._formula = ""

    @property
    def Formula(self) -> str:
        return self._formula

    @Formula.setter
    def Formula(self, formula: str) -> None:
        self._anotar("Variable.Formula=", formula)
        self._formula = formula


class VariablesFalsas:
    """`doc.Variables`. `Query` exige `VarType` y `NamedBy` válidos, como Solid Edge 2026."""

    TIPOS = frozenset({1661573600, 1560616706, 215773802, -170730141})

    def __init__(self, doc: DocumentoFalso, variables: list[VariableFalsa] | None = None) -> None:
        self.doc = doc
        self.variables: list[VariableFalsa] = []
        for variable in variables or []:
            self.agregar(variable)

    def agregar(self, variable: VariableFalsa) -> VariableFalsa:
        variable.doc = self.doc
        self.variables.append(variable)
        return variable

    @property
    def Count(self) -> int:
        return len(self.variables)

    def Item(self, clave: int | str) -> VariableFalsa:
        if isinstance(clave, str):
            for variable in self.variables:
                if variable.DisplayName == clave:
                    return variable
            raise com_error(0x80020009, "Excepción", f"No existe {clave}")
        return self.variables[clave - 1]

    def Query(self, patron: str, nombrado_por: int, tipo: int, ignorar_mayusculas: bool):
        self.doc.registro.append(("Variables.Query", patron, nombrado_por, tipo))
        if tipo not in self.TIPOS or nombrado_por != 2:
            return ColeccionFalsa([])  # con otro VarType o NamedBy Solid Edge devuelve vacío
        hallados = [
            v
            for v in self.variables
            if v.tipo == tipo and fnmatch.fnmatch(v.DisplayName.casefold(), patron.casefold())
        ]
        return ColeccionFalsa(hallados)

    def Add(self, nombre: str, formula: str, tipo_unidad: int | None = None) -> VariableFalsa:
        self.doc.registro.append(("Variables.Add", nombre, formula, tipo_unidad))
        return self.agregar(VariableFalsa(nombre, 0.0, unidad=tipo_unidad if tipo_unidad else 58))


class PropiedadFalsa:
    def __init__(self, nombre: str, valor: Any, conjunto: ConjuntoPropiedadesFalso) -> None:
        self.Name = nombre
        self._valor = valor
        self.conjunto = conjunto

    @property
    def Value(self) -> Any:
        return self._valor

    @Value.setter
    def Value(self, valor: Any) -> None:
        self.conjunto.doc.registro.append(("Property.Value=", self.Name, valor))
        self._valor = valor


class ConjuntoPropiedadesFalso(ColeccionFalsa):
    """Un conjunto de propiedades (`SummaryInformation`, `Custom`, ...)."""

    def __init__(self, doc: DocumentoFalso, nombre: str, valores: dict[str, Any]) -> None:
        super().__init__([])
        self.doc = doc
        self.Name = nombre
        for clave, valor in valores.items():
            self.elementos.append(PropiedadFalsa(clave, valor, self))

    def Add(self, nombre: str, valor: Any) -> PropiedadFalsa:
        self.doc.registro.append(("Properties.Add", self.Name, nombre, valor))
        propiedad = PropiedadFalsa(nombre, valor, self)
        self.elementos.append(propiedad)
        return propiedad


def con_propiedades(doc: DocumentoFalso, conjuntos: dict[str, dict[str, Any]]) -> None:
    """Dejale al documento esos conjuntos de propiedades."""
    doc.Properties = ColeccionFalsa(
        [ConjuntoPropiedadesFalso(doc, nombre, valores) for nombre, valores in conjuntos.items()]
    )


# (volumen, área, masa, cdg, cdv, momentos globales, principales, ejes, radios)
FISICAS_POR_DEFECTO = (
    0.001,
    0.06,
    7.85,
    (0.01, 0.02, 0.03),
    (0.011, 0.021, 0.031),
    (1.0, 2.0, 3.0, 0.1, 0.2, 0.3),
    (1.0, 2.0, 3.0),
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
    (0.1, 0.2, 0.3),
)

_BUFFERS_FISICOS = {
    "Density",
    "Accuracy",
    "CenterOfGravity",
    "CenterOfVolume",
    "GlobalMomentsOfInteria",
    "PrincipalMomentsOfInteria",
    "PrincipalAxes",
    "RadiiOfGyration",
}


def calcular_fisicas(objeto: Any, **kwargs: Any) -> tuple:
    """Imita `ComputePhysicalPropertiesWithSpecifiedDensity`: solo kwargs, buffers `[in,out]`.

    Sin los seis buffers falla como la API real ("Parameter not optional"). Devuelve la tupla
    de 11 valores del late binding, con la masa escalada por la densidad pedida.
    """
    doc = getattr(objeto, "doc", objeto)
    doc.registro.append(("ComputePhysicalPropertiesWithSpecifiedDensity", kwargs))
    if set(kwargs) != _BUFFERS_FISICOS:
        raise com_error(0x8002000F, "Parameter not optional")
    volumen, area, _masa, *resto = doc.fisicas
    return (volumen, area, volumen * kwargs["Density"], *resto, 0.99, 0)


class ModeloFalso:
    """`Model` de una pieza: colección de features y cálculo de propiedades físicas."""

    def __init__(self, doc: DocumentoFalso, features: list | None = None) -> None:
        self.doc = doc
        self.Features = ColeccionFalsa(features)

    def ComputePhysicalPropertiesWithSpecifiedDensity(self, **kwargs: Any) -> tuple:
        return calcular_fisicas(self, **kwargs)


class FeatureFalsa:
    def __init__(
        self,
        nombre: str,
        tipo: int = 462094706,
        *,
        suprimida: bool = False,
        estado: int = 1216476310,
    ) -> None:
        self.Name = nombre
        self.Type = tipo
        self.Suppress = suprimida
        self.Status = estado


class PlanoRefFalso:
    """Plano de referencia del Pathfinder: tiene `Name` y `Type` pero no `Suppress`."""

    def __init__(self, nombre: str) -> None:
        self.Name = nombre
        self.Type = 0


class OcurrenciaFalsa:
    """`Occurrence` de un ensamble; si tiene hijos es un subensamble."""

    def __init__(
        self,
        nombre: str,
        archivo: str,
        *,
        visible: bool = True,
        hijos: list[OcurrenciaFalsa] | None = None,
    ) -> None:
        self.Name = nombre
        self.OccurrenceFileName = archivo
        self.Visible = visible
        self.Subassembly = bool(hijos)
        self.SubOccurrences = ColeccionFalsa(hijos)


class DocumentosFalsos(_ConFallos):
    def __init__(
        self, documentos: list[DocumentoFalso] | None = None, registro: list | None = None
    ) -> None:
        super().__init__()
        self.registro = registro if registro is not None else []
        self._documentos = list(documentos or [])
        for documento in self._documentos:
            documento.registro = self.registro
            documento.coleccion = self
        self.activo: DocumentoFalso | None = self._documentos[-1] if self._documentos else None

    def quitar(self, documento: DocumentoFalso) -> None:
        self._documentos.remove(documento)
        if self.activo is documento:
            self.activo = self._documentos[-1] if self._documentos else None

    def _agregar(self, documento: DocumentoFalso) -> DocumentoFalso:
        documento.registro = self.registro
        documento.coleccion = self
        self._documentos.append(documento)
        self.activo = documento
        return documento

    @property
    def Count(self) -> int:
        self._tocar("Count")
        return len(self._documentos)

    def Item(self, indice: int) -> DocumentoFalso:
        self._tocar("Item")
        return self._documentos[indice - 1]

    def Add(self, prog_id: str) -> DocumentoFalso:
        self.registro.append(("Documents.Add", prog_id))
        self._tocar("Add")
        return self._agregar(DocumentoFalso(f"Document{len(self._documentos) + 1}"))

    def Open(self, ruta: str, flags: int | None = None) -> DocumentoFalso:
        self.registro.append(("Documents.Open", ruta, flags))
        self._tocar("Open")
        nombre = ruta.replace("\\", "/").rsplit("/", 1)[-1]
        return self._agregar(DocumentoFalso(nombre, ruta=ruta, solo_lectura=flags == 1))


class AplicacionFalsa(_ConFallos):
    """`Application` falsa. Los atributos con fallos programables son propiedades.

    `registro` anota las llamadas en orden; `escrituras` filtra las que cambian estado.
    """

    def __init__(self, version: str = "226.00.00.00", documentos=None) -> None:
        super().__init__()
        self._version = version
        self._alertas = True
        self.registro: list[tuple] = []
        self._documentos = DocumentosFalsos(documentos, self.registro)
        self.historial_alertas: list[bool] = []
        self.visible = True
        self.salio = False

    def agregar_documento(self, nombre: str = "Part1.par", **opciones: Any) -> DocumentoFalso:
        """Sumá un documento abierto (queda activo) sin anotarlo como escritura."""
        return self._documentos._agregar(DocumentoFalso(nombre, **opciones))

    @property
    def escrituras(self) -> list[tuple]:
        return [llamada for llamada in self.registro if llamada[0] in ESCRITURAS]

    @property
    def Version(self) -> str:
        self._tocar("Version")
        return self._version

    @property
    def Name(self) -> str:
        self._tocar("Name")
        return "Solid Edge"

    @property
    def Visible(self) -> bool:
        self._tocar("Visible")
        return self.visible

    @property
    def DisplayAlerts(self) -> bool:
        self._tocar("DisplayAlerts")
        return self._alertas

    @DisplayAlerts.setter
    def DisplayAlerts(self, valor: bool) -> None:
        self._tocar("DisplayAlerts_set")
        self._alertas = valor
        self.historial_alertas.append(valor)

    @property
    def Documents(self) -> DocumentosFalsos:
        self._tocar("Documents")
        return self._documentos

    @property
    def ActiveDocument(self) -> DocumentoFalso:
        self._tocar("ActiveDocument")
        if self._documentos.activo is None:
            raise com_error(0x80020009, "Excepción", "No hay documento activo")
        return self._documentos.activo

    def Quit(self) -> None:
        self.registro.append(("Quit",))
        self._tocar("Quit")
        self.salio = True


class FabricaApp:
    """Proveedor de app inyectable: cada llamada cuenta y devuelve la siguiente app.

    `apps` es la lista de apps a entregar (la última se repite). Un elemento que sea una
    excepción se levanta en lugar de devolverse. Sin `apps`, levanta `MK_E_UNAVAILABLE`.
    """

    def __init__(self, *apps: Any) -> None:
        self.apps = list(apps)
        self.llamadas = 0

    def __call__(self) -> Any:
        self.llamadas += 1
        if not self.apps:
            raise com_error(0x800401E3, "Operation unavailable")
        elemento = self.apps[min(self.llamadas, len(self.apps)) - 1]
        if isinstance(elemento, BaseException):
            raise elemento
        return elemento
