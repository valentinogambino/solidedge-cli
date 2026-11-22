"""COM falso para tests: imita lo mínimo de `Application` sin Solid Edge ni pywin32."""

from __future__ import annotations

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
    {"Documents.Add", "Documents.Open", "Save", "SaveAs", "Close", "Quit", "Dirty=", "Activate"}
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
