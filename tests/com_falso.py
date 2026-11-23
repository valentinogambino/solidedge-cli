"""COM falso para tests: imita lo mínimo de `Application` sin Solid Edge ni pywin32."""

from __future__ import annotations

import fnmatch
import math
import os
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
        "View.SaveAsImage",
        "SaveAsFlatDXFEx",
        "ModelLinks.Add",
        "SheetSetup.SheetSizeOption=",
        "DrawingViews.AddPartView",
        "DrawingViews.AddSheetMetalView",
        "DrawingViews.AddAssemblyView",
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
        "PhysicalProperties.Update",
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
        # Último cálculo de la sesión (9 valores) o None si nunca se calculó, y la geometría
        # que da el cálculo de una pieza. Un ensamble tiene `PhysicalProperties`.
        self.fisicas_calculadas: tuple | None = None
        self.fisicas_pendientes: tuple | None = None
        self.densidad_calculada = 0.0
        self.fisicas = FISICAS_POR_DEFECTO
        if tipo == 3:
            self.PhysicalProperties = FisicasDeEnsambleFalsas(self)
        # Exportación (F4): "escribir" deja un archivo con contenido, "nada" no escribe y
        # "vacio" lo deja en 0 bytes.
        self.modo_exportacion = "escribir"
        self.Windows = ColeccionFalsa(
            [VentanaDeHojaFalsa(self) if tipo == 2 else VentanaFalsa(self)]
        )
        if tipo == 4:
            con_chapa(self)
        if tipo == 2:
            self.ModelLinks = EnlacesFalsos(self)
            self.ActiveSheet = HojaFalsa(self)
            self.Sections = SeccionesFalsas()
            self.Sheets = ColeccionFalsa([self.ActiveSheet])

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
        self._consolidar_fisicas()

    def SaveAs(self, ruta: str) -> None:
        self.registro.append(("SaveAs", self.Name, ruta))
        self._tocar("SaveAs")
        with open(ruta, "wb") as archivo:
            archivo.write(b"falso")
        self.FullName = ruta
        self.Name = ruta.replace("\\", "/").rsplit("/", 1)[-1]
        self._sucio = False
        self._consolidar_fisicas()

    def _consolidar_fisicas(self) -> None:
        """Un cálculo con densidad recién se puede leer (`GetPhysicalProperties`) tras guardar."""
        if self.fisicas_pendientes is not None:
            self.fisicas_calculadas = self.fisicas_pendientes
            self.fisicas_pendientes = None

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


# Tamaños (ancho, alto) en metros de `PaperSizeConstants` ISO apaisados.
PAPEL_ISO_APAISADO = {
    27: (0.210, 0.148),
    29: (0.297, 0.210),
    31: (0.420, 0.297),
    33: (0.594, 0.420),
    35: (0.841, 0.594),
    37: (1.189, 0.841),
}


class EnlaceFalso:
    def __init__(self, ruta: str) -> None:
        self.ruta = ruta


class EnlacesFalsos:
    """`Draft.ModelLinks`."""

    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.enlaces: list[EnlaceFalso] = []

    def Add(self, ruta: str) -> EnlaceFalso:
        self.doc.registro.append(("ModelLinks.Add", ruta))
        self.doc._tocar("ModelLinks.Add")
        enlace = EnlaceFalso(ruta)
        self.enlaces.append(enlace)
        return enlace

    @property
    def Count(self) -> int:
        return len(self.enlaces)


class ConfiguracionDeHojaFalsa:
    """`Sheet.SheetSetup`: arranca en A4 apaisada y `SheetSizeOption` cambia las medidas."""

    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.SheetWidth, self.SheetHeight = 0.297, 0.210
        self._opcion = 29

    @property
    def SheetSizeOption(self) -> int:
        return self._opcion

    @SheetSizeOption.setter
    def SheetSizeOption(self, valor: int) -> None:
        self.doc.registro.append(("SheetSetup.SheetSizeOption=", valor))
        self.doc._tocar("SheetSizeOption")
        self._opcion = valor
        self.SheetWidth, self.SheetHeight = PAPEL_ISO_APAISADO[valor]


class VistasDeDibujoFalsas(_ConFallos):
    """`Sheet.DrawingViews`: registra orientación, escala y posición de cada vista."""

    def __init__(self, doc: DocumentoFalso) -> None:
        super().__init__()
        self.doc = doc
        self.vistas: list[tuple] = []

    def _agregar(self, metodo: str, enlace, orientacion, escala, x, y, tipo) -> None:
        llamada = (f"DrawingViews.{metodo}", enlace.ruta, orientacion, escala, x, y, tipo)
        self.doc.registro.append(llamada)
        self._tocar(metodo)
        self.vistas.append(llamada[1:])

    def AddPartView(self, enlace, orientacion, escala, x, y, tipo=0) -> None:
        self._agregar("AddPartView", enlace, orientacion, escala, x, y, tipo)

    def AddSheetMetalView(self, enlace, orientacion, escala, x, y, tipo=0) -> None:
        self._agregar("AddSheetMetalView", enlace, orientacion, escala, x, y, tipo)

    def AddAssemblyView(self, enlace, orientacion, escala, x, y, tipo=0) -> None:
        self._agregar("AddAssemblyView", enlace, orientacion, escala, x, y, tipo)

    @property
    def Count(self) -> int:
        return len(self.vistas)


class HojaDeFondoFalsa:
    def __init__(self, nombre: str) -> None:
        self.Name = nombre


class SeccionDeFondosFalsa:
    """`Sections.BackgroundSection`: la plantilla ISO trae fondos de A4 a A1."""

    def __init__(self) -> None:
        self.Sheets = ColeccionFalsa([HojaDeFondoFalsa(f"A{n}-Sheet") for n in (4, 3, 2, 1)])


class SeccionesFalsas:
    def __init__(self) -> None:
        self.BackgroundSection = SeccionDeFondosFalsa()


class HojaFalsa:
    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.SheetSetup = ConfiguracionDeHojaFalsa(doc)
        self.DrawingViews = VistasDeDibujoFalsas(doc)
        self._fondo = HojaDeFondoFalsa("A2-Sheet")

    @property
    def Background(self) -> HojaDeFondoFalsa:
        return self._fondo

    @Background.setter
    def Background(self, hoja: HojaDeFondoFalsa) -> None:
        self.doc.registro.append(("Sheet.Background=", hoja.Name))
        self._fondo = hoja


class VistaFalsa:
    """`Window.View`: solo la captura de imagen."""

    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc

    def Fit(self) -> None:
        self.doc.registro.append(("View.Fit", self.doc.Name))

    def SaveAsImage(self, ruta: str, ancho: int, alto: int) -> None:
        self.doc.registro.append(("View.SaveAsImage", self.doc.Name, ruta, ancho, alto))
        self.doc._tocar("SaveAsImage")
        if self.doc.modo_exportacion == "escribir":
            with open(ruta, "wb") as archivo:
                archivo.write(b"imagen")
        elif self.doc.modo_exportacion == "vacio":
            open(ruta, "wb").close()


class VentanaDeHojaFalsa(VistaFalsa):
    """`SheetWindow` de un Draft: no tiene `View`; `Fit` y `SaveAsImage` son de la ventana."""

    def __init__(self, doc: DocumentoFalso) -> None:
        super().__init__(doc)


class VentanaFalsa:
    def __init__(self, doc: DocumentoFalso) -> None:
        self.View = VistaFalsa(doc)


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
    doc.fisicas_pendientes = (volumen, area, volumen * kwargs["Density"], *resto)
    doc.densidad_calculada = kwargs["Density"]
    return (*doc.fisicas_pendientes, 0.99, 0)


def leer_fisicas(objeto: Any, **kwargs: Any) -> tuple:
    """Imita `Model.GetPhysicalProperties`: 13 valores con el estado primero.

    Sin cálculo previo devuelve estado 2, ceros y `None` en los arreglos (verificado en vivo).
    """
    doc = getattr(objeto, "doc", objeto)
    doc.registro.append(("Model.GetPhysicalProperties", kwargs))
    if set(kwargs) != _BUFFERS_FISICOS:
        raise com_error(0x8002000F, "Parameter not optional")
    if doc.fisicas_calculadas is None:
        return (2, 0.0, 0.0, 0.0, 0.0, 0.0, None, None, None, None, None, None, 0.0)
    volumen, area, masa, *resto = doc.fisicas_calculadas
    return (1, doc.densidad_calculada, 0.99, volumen, area, masa, *resto, 0.99)


class FisicasDeEnsambleFalsas:
    """`PhysicalProperties` de un ensamble: `Update()` y `GetAssemblyPhysicalProperties()`.

    Devuelve (masa, volumen, área, cdm, cdv, momentos, eje1, eje2, eje3, principales, radios,
    enfermo, estado); el área de un ensamble viene en -1 (verificado en vivo).
    """

    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.IsUpToDate = False
        self.actualizaciones = 0

    def Update(self) -> None:
        self.doc.registro.append(("PhysicalProperties.Update", self.doc.Name))
        self.IsUpToDate = True
        self.actualizaciones += 1

    def GetAssemblyPhysicalProperties(self, **kwargs: Any) -> tuple:
        self.doc.registro.append(("PhysicalProperties.GetAssemblyPhysicalProperties", kwargs))
        if not self.IsUpToDate:
            return (
                0.0,
                0.0,
                0.0,
                (0.0,) * 3,
                (0.0,) * 3,
                (0.0,) * 6,
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
                (0.0,) * 3,
                (0.0,) * 3,
                False,
                False,
            )
        volumen, _area, masa, cdg, cdv, momentos, principales, ejes, radios = self.doc.fisicas
        return (
            masa,
            volumen,
            -1.0,
            cdg,
            cdv,
            momentos,
            ejes[0:3],
            ejes[3:6],
            ejes[6:9],
            principales,
            radios,
            False,
            True,
        )


class ModelosDeChapaFalsos(ColeccionFalsa):
    """`Models` de una chapa: suma `SaveAsFlatDXFEx` (desarrollo a DXF)."""

    def __init__(self, doc: DocumentoFalso) -> None:
        super().__init__([])
        self.doc = doc

    def SaveAsFlatDXFEx(self, ruta, cara, arista, vertice, usar_desarrollo) -> None:
        self.doc.registro.append(
            ("SaveAsFlatDXFEx", self.doc.Name, ruta, cara, arista, vertice, usar_desarrollo)
        )
        self.doc._tocar("SaveAsFlatDXFEx")
        if self.doc.modo_exportacion == "escribir":
            with open(ruta, "wb") as archivo:
                archivo.write(b"dxf-plano")
        elif self.doc.modo_exportacion == "vacio":
            open(ruta, "wb").close()


def con_chapa(doc: DocumentoFalso, con_desarrollo: bool = True) -> None:
    """Dejale a una chapa su `Models` con `SaveAsFlatDXFEx` y, o no, un flat pattern."""
    doc.Models = ModelosDeChapaFalsos(doc)
    doc.FlatPatternModels = ColeccionFalsa([object()] if con_desarrollo else [])


class CuerpoFalso:
    """`Model.Body`: `GetRange` devuelve `(minimo, maximo)` o falla si no hay caja."""

    def __init__(self, caja=None) -> None:
        self.caja = caja

    def GetRange(self, minimo, maximo):
        if self.caja is None:
            raise com_error(0x80004005, "Error no especificado")
        return self.caja


class ModeloFalso:
    """`Model` de una pieza: colección de features y cálculo de propiedades físicas."""

    def __init__(self, doc: DocumentoFalso, features: list | None = None, caja=None) -> None:
        self.doc = doc
        self.Features = ColeccionFalsa(features)
        self.Body = CuerpoFalso(caja)

    def ComputePhysicalPropertiesWithSpecifiedDensity(self, **kwargs: Any) -> tuple:
        return calcular_fisicas(self, **kwargs)

    def GetPhysicalProperties(self, **kwargs: Any) -> tuple:
        return leer_fisicas(self, **kwargs)


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
        caja=None,
    ) -> None:
        self.caja = caja
        self.Name = nombre
        self.OccurrenceFileName = archivo
        self.Visible = visible
        self.Subassembly = bool(hijos)
        self.SubOccurrences = ColeccionFalsa(hijos)


TIPO_POR_EXTENSION = {"par": 1, "dft": 2, "asm": 3, "psm": 4}
TIPO_POR_PROGID = {
    "SolidEdge.PartDocument": 1,
    "SolidEdge.DraftDocument": 2,
    "SolidEdge.AssemblyDocument": 3,
    "SolidEdge.SheetMetalDocument": 4,
}


def _caja_de_ocurrencia(self, minimo, maximo):
    if self.caja is None:
        raise com_error(0x80004005, "Error no especificado")
    return self.caja


OcurrenciaFalsa.GetRangeBox = _caja_de_ocurrencia


class DocumentosFalsos(_ConFallos):
    def __init__(
        self, documentos: list[DocumentoFalso] | None = None, registro: list | None = None
    ) -> None:
        super().__init__()
        self.registro = registro if registro is not None else []
        self._documentos = list(documentos or [])
        # Configuración por nombre de archivo para los documentos que abre `Open`:
        # {"error": excepción}, {"modo_exportacion": "nada" | "vacio"} o {"caja": (min, max)}.
        self.al_abrir: dict[str, dict[str, Any]] = {}
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
        tipo = TIPO_POR_PROGID.get(prog_id)
        if tipo is None:
            tipo = TIPO_POR_EXTENSION.get(prog_id.rsplit(".", 1)[-1].lower(), 1)
        return self._agregar(DocumentoFalso(f"Document{len(self._documentos) + 1}", tipo=tipo))

    def Open(self, ruta: str) -> DocumentoFalso:
        # El Open real no tiene flag de solo lectura (verificado en vivo, SE 226.00.01.04):
        # el documento queda en solo lectura solo si el archivo tiene el atributo de Windows.
        self.registro.append(("Documents.Open", ruta))
        self._tocar("Open")
        nombre = ruta.replace("\\", "/").rsplit("/", 1)[-1]
        config = self.al_abrir.get(nombre, {})
        if "error" in config:
            raise config["error"]
        extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        doc = DocumentoFalso(
            nombre,
            ruta=ruta,
            tipo=TIPO_POR_EXTENSION.get(extension, 1),
            solo_lectura=os.path.exists(ruta) and not os.access(ruta, os.W_OK),
        )
        doc.modo_exportacion = config.get("modo_exportacion", "escribir")
        if "desarrollo" in config:
            con_chapa(doc, config["desarrollo"])
        if "caja" in config:
            doc.Models = ColeccionFalsa([ModeloFalso(doc, caja=config["caja"])])
        return self._agregar(doc)


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


# --- Modelado (F5): perfiles, extrusión, revolución y cortes ----------------------------------

ESCRITURAS = ESCRITURAS | {
    "ProfileSets.Add",
    "Profiles.Add",
    "Lines2d.AddBy2Points",
    "Circles2d.AddByCenterRadius",
    "Profile.End",
    "Profile.ToggleConstruction",
    "Profile.SetAxisOfRevolution",
    "Models.AddFiniteExtrudedProtrusion",
    "Models.AddFiniteRevolvedProtrusion",
    "ExtrudedProtrusions.AddFiniteMulti",
    "ExtrudedCutouts.AddFiniteMulti",
    "ExtrudedCutouts.AddThroughAllMulti",
    "RevolvedProtrusions.AddFiniteMulti",
    "Feature.Delete",
}

LADO_IZQUIERDO = 1  # igLeft: un corte hacia atras desde un plano de la base no toca material
LADO_SIMETRICO = 3  # igSymmetric: el corte pasante simetrico no corta nada (verificado en vivo)


class LineaFalsa:
    def __init__(self, puntos: tuple) -> None:
        self.puntos = puntos
        self.construccion = False


class LineasFalsas:
    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.lineas: list[LineaFalsa] = []

    def AddBy2Points(self, x1, y1, x2, y2):
        self.doc.registro.append(("Lines2d.AddBy2Points", x1, y1, x2, y2))
        self.doc._tocar("AddBy2Points")
        linea = LineaFalsa((x1, y1, x2, y2))
        self.lineas.append(linea)
        return linea

    @property
    def Count(self) -> int:
        return len(self.lineas)


class CirculosFalsos:
    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.circulos: list[tuple] = []

    def AddByCenterRadius(self, x, y, r):
        self.doc.registro.append(("Circles2d.AddByCenterRadius", x, y, r))
        self.doc._tocar("AddByCenterRadius")
        self.circulos.append((x, y, r))
        return object()

    @property
    def Count(self) -> int:
        return len(self.circulos)


class EjeDeRefFalso:
    def __init__(self, linea: LineaFalsa) -> None:
        _x1, y1, _x2, y2 = linea.puntos
        self.eje = "x" if y1 == y2 else "y"


class PerfilFalso:
    """`Profile`: acumula lineas y circulos; `End` devuelve -103 con lineas y 0 con un circulo."""

    def __init__(self, doc: DocumentoFalso, plano: Any) -> None:
        self.doc = doc
        self.plano = plano
        self.Lines2d = LineasFalsas(doc)
        self.Circles2d = CirculosFalsos(doc)
        self.Name = "Profile_1"

    def End(self, bandera: int) -> int:
        self.doc.registro.append(("Profile.End", bandera))
        self.doc._tocar("End")
        if self.doc.codigo_end is not None:
            return self.doc.codigo_end
        return -103 if self.Lines2d.Count else 0

    def ToggleConstruction(self, linea: LineaFalsa) -> None:
        self.doc.registro.append(("Profile.ToggleConstruction",))
        linea.construccion = not linea.construccion

    def SetAxisOfRevolution(self, linea: LineaFalsa) -> EjeDeRefFalso:
        self.doc.registro.append(("Profile.SetAxisOfRevolution",))
        return EjeDeRefFalso(linea)

    def caja(self) -> tuple[float, float, float, float]:
        puntos = [ln.puntos for ln in self.Lines2d.lineas if not ln.construccion]
        xs = [v for p in puntos for v in (p[0], p[2])]
        ys = [v for p in puntos for v in (p[1], p[3])]
        return min(xs), min(ys), max(xs), max(ys)

    def area(self) -> float:
        if self.Circles2d.circulos:
            return sum(math.pi * r * r for _, _, r in self.Circles2d.circulos)
        x0, y0, x1, y1 = self.caja()
        return (x1 - x0) * (y1 - y0)

    def volumen_revolucion(self, eje: str, angulo: float) -> float:
        """Teorema de Pappus con el centroide del rectangulo."""
        x0, y0, x1, y1 = self.caja()
        distancia = (x0 + x1) / 2 if eje == "y" else (y0 + y1) / 2
        return self.area() * distancia * angulo


class PerfilesFalsos:
    def __init__(self, conjunto: ConjuntoDePerfilesFalso) -> None:
        self.conjunto = conjunto

    @property
    def Count(self) -> int:
        return len(self.conjunto.perfiles)

    def Item(self, indice: int) -> PerfilFalso:
        return self.conjunto.perfiles[indice - 1]

    def Add(self, plano: Any) -> PerfilFalso:
        self.conjunto.doc.registro.append(("Profiles.Add", getattr(plano, "Name", None)))
        perfil = PerfilFalso(self.conjunto.doc, plano)
        self.conjunto.perfiles.append(perfil)
        return perfil


class ConjuntoDePerfilesFalso:
    def __init__(self, doc: DocumentoFalso, numero: int) -> None:
        self.doc = doc
        self.Name = f"ProfileSet_{numero}"
        self.perfiles: list[PerfilFalso] = []
        self.Profiles = PerfilesFalsos(self)


class ConjuntosDePerfilesFalsos(ColeccionFalsa):
    def __init__(self, doc: DocumentoFalso) -> None:
        super().__init__([])
        self.doc = doc

    def Add(self) -> ConjuntoDePerfilesFalso:
        self.doc.registro.append(("ProfileSets.Add",))
        self.doc._tocar("ProfileSets.Add")
        conjunto = ConjuntoDePerfilesFalso(self.doc, len(self.elementos) + 1)
        self.elementos.append(conjunto)
        return conjunto


class OperacionFalsa:
    def __init__(self, nombre: str, delta: float, coleccion: OperacionesFalsas) -> None:
        self.Name = nombre
        self.delta = delta
        self.coleccion = coleccion

    def Delete(self) -> None:
        self.coleccion.doc.registro.append(("Feature.Delete", self.Name))
        self.coleccion.elementos.remove(self)


class OperacionesFalsas(ColeccionFalsa):
    """`ExtrudedProtrusions`, `ExtrudedCutouts` o `RevolvedProtrusions` de un modelo."""

    def __init__(self, doc: DocumentoFalso, prefijo: str, signo: int, modelo: ModeloParteFalso):
        super().__init__([])
        self.doc, self.prefijo, self.signo, self.modelo = doc, prefijo, signo, modelo
        self.contador = 0

    def agregar(self, delta: float) -> OperacionFalsa:
        self.contador += 1
        operacion = OperacionFalsa(f"{self.prefijo}_{self.contador}", self.signo * delta, self)
        self.elementos.append(operacion)
        return operacion

    def _anotar(self, que: str, *datos: Any) -> None:
        self.doc.registro.append((que, *datos))
        self.doc._tocar(que)

    def AddFiniteMulti(self, cantidad, perfiles, *resto):
        perfil = perfiles[0]
        if self.prefijo == "ExtrudedProtrusion":
            lado, distancia = resto
            self._anotar("ExtrudedProtrusions.AddFiniteMulti", cantidad, lado, distancia)
            return self.agregar(perfil.area() * distancia)
        if self.prefijo == "ExtrudedCutout":
            lado, distancia = resto
            self._anotar("ExtrudedCutouts.AddFiniteMulti", cantidad, lado, distancia)
            efecto = 0.0 if lado == self.doc.lado_sin_efecto else perfil.area() * distancia
            return self.agregar(efecto)
        eje, lado, angulo = resto
        self._anotar("RevolvedProtrusions.AddFiniteMulti", cantidad, eje.eje, lado, angulo)
        return self.agregar(perfil.volumen_revolucion(eje.eje, angulo))

    def AddThroughAllMulti(self, cantidad, perfiles, lado):
        self._anotar("ExtrudedCutouts.AddThroughAllMulti", cantidad, lado)
        sin_efecto = lado in (self.doc.lado_sin_efecto, LADO_SIMETRICO)
        return self.agregar(0.0 if sin_efecto else perfiles[0].area() * self.modelo.espesor)


class CuerpoDeParteFalso:
    def __init__(self, modelo: ModeloParteFalso) -> None:
        self.modelo = modelo

    @property
    def Volume(self) -> float:
        return self.modelo.volumen()


class ModeloParteFalso:
    def __init__(self, doc: DocumentoFalso) -> None:
        self.doc = doc
        self.espesor = 0.0
        self.ExtrudedProtrusions = OperacionesFalsas(doc, "ExtrudedProtrusion", 1, self)
        self.ExtrudedCutouts = OperacionesFalsas(doc, "ExtrudedCutout", -1, self)
        self.RevolvedProtrusions = OperacionesFalsas(doc, "RevolvedProtrusion", 1, self)
        self.Body = CuerpoDeParteFalso(self)

    def volumen(self) -> float:
        colecciones = (self.ExtrudedProtrusions, self.ExtrudedCutouts, self.RevolvedProtrusions)
        return sum(op.delta for col in colecciones for op in col.elementos)


class ModelosDeParteFalsos(ColeccionFalsa):
    """`Models` de una pieza ordenada: la primera operacion crea el modelo."""

    def __init__(self, doc: DocumentoFalso) -> None:
        super().__init__([])
        self.doc = doc

    def AddFiniteExtrudedProtrusion(self, cantidad, perfiles, lado, distancia):
        self.doc.registro.append(("Models.AddFiniteExtrudedProtrusion", cantidad, lado, distancia))
        self.doc._tocar("AddFiniteExtrudedProtrusion")
        modelo = ModeloParteFalso(self.doc)
        modelo.espesor = distancia
        modelo.ExtrudedProtrusions.agregar(perfiles[0].area() * distancia)
        self.elementos.append(modelo)
        return modelo

    def AddFiniteRevolvedProtrusion(self, cantidad, perfiles, eje, lado, angulo):
        self.doc.registro.append(
            ("Models.AddFiniteRevolvedProtrusion", cantidad, eje.eje, lado, angulo)
        )
        self.doc._tocar("AddFiniteRevolvedProtrusion")
        modelo = ModeloParteFalso(self.doc)
        modelo.RevolvedProtrusions.agregar(perfiles[0].volumen_revolucion(eje.eje, angulo))
        self.elementos.append(modelo)
        return modelo


def con_modelado(doc: DocumentoFalso, *, modo: int | None = 2) -> DocumentoFalso:
    """Dejale a una pieza o chapa planos, perfiles y `Models` capaces de modelar.

    Imita lo verificado en vivo: 3 planos, `Profile.End` devuelve -103 con lineas, y un corte
    hacia `igLeft` desde el plano no quita material (el corte pasante simetrico tampoco).
    """
    doc.RefPlanes = ColeccionFalsa([PlanoRefFalso(f"RefPlane_{n}") for n in (1, 2, 3)])
    doc.ProfileSets = ConjuntosDePerfilesFalsos(doc)
    doc.Models = ModelosDeParteFalsos(doc)
    doc.codigo_end = None
    doc.lado_sin_efecto = LADO_IZQUIERDO
    if modo is not None:
        doc.ModelingMode = modo
    return doc
