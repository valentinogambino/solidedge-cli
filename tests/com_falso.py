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


class DocumentoFalso(_ConFallos):
    def __init__(self, nombre: str = "Part1.par") -> None:
        super().__init__()
        self.Name = nombre
        self.FullName = nombre
        self.cerrado = False

    def Close(self, guardar: bool = False) -> None:
        self._tocar("Close")
        self.cerrado = True

    def Activate(self) -> None:
        self._tocar("Activate")


class DocumentosFalsos(_ConFallos):
    def __init__(self, documentos: list[DocumentoFalso] | None = None) -> None:
        super().__init__()
        self._documentos = list(documentos or [])
        self.activo: DocumentoFalso | None = self._documentos[-1] if self._documentos else None

    @property
    def Count(self) -> int:
        self._tocar("Count")
        return len(self._documentos)

    def Item(self, indice: int) -> DocumentoFalso:
        self._tocar("Item")
        return self._documentos[indice - 1]

    def Add(self, prog_id: str) -> DocumentoFalso:
        self._tocar("Add")
        documento = DocumentoFalso(f"{prog_id}{len(self._documentos) + 1}")
        self._documentos.append(documento)
        self.activo = documento
        return documento


class AplicacionFalsa(_ConFallos):
    """`Application` falsa. Los atributos con fallos programables son propiedades."""

    def __init__(self, version: str = "226.00.00.00", documentos=None) -> None:
        super().__init__()
        self._version = version
        self._alertas = True
        self._documentos = DocumentosFalsos(documentos)
        self.historial_alertas: list[bool] = []

    @property
    def Version(self) -> str:
        self._tocar("Version")
        return self._version

    @property
    def Name(self) -> str:
        self._tocar("Name")
        return "Solid Edge"

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
    def ActiveDocument(self) -> DocumentoFalso | None:
        self._tocar("ActiveDocument")
        return self._documentos.activo


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
