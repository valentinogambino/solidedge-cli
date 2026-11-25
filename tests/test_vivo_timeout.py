"""`--timeout` contra un diálogo modal real de Solid Edge. No corre por defecto.

Abre una pieza propia en una carpeta temporal, provoca el diálogo «This file exists» con
`SaveCopyAs` sobre un archivo existente y comprueba que el plazo corta la espera, que la
sesión sigue respondiendo con el modal abierto y que el proceso de la CLI termina con exit 7.
El diálogo se cierra con el botón «No» (sin matar Solid Edge); si no se lo encuentra, el test
falla y pide cerrarlo a mano. Al terminar cierra solo el documento que creó, sin guardar.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import win32con
import win32gui
import win32process
from typer.testing import CliRunner

from se_cli.cli import app
from se_cli.core.errors import TiempoAgotado
from se_cli.core.session import Sesion
from se_cli.core.sta import HiloSta

PLAZO = 5
LLAMADAS_DE_COSTO = 500


def _cli(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _hwnd_de_solid_edge(sesion: Sesion) -> int:
    return sesion.llamar(lambda app_: app_.hWnd)


def _dialogos_modales(pid: int) -> list[int]:
    encontrados: list[int] = []

    def mirar(hwnd: int, _) -> bool:
        if (
            win32gui.IsWindowVisible(hwnd)
            and win32gui.GetClassName(hwnd) == "#32770"
            and win32process.GetWindowThreadProcessId(hwnd)[1] == pid
        ):
            encontrados.append(hwnd)
        return True

    win32gui.EnumWindows(mirar, None)
    return encontrados


def _cerrar_modal(hwnd_principal: int, espera: float = 5.0) -> None:
    """Apretá «No» en el diálogo modal de Solid Edge, sin cerrar el programa."""
    pid = win32process.GetWindowThreadProcessId(hwnd_principal)[1]
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        for dialogo in _dialogos_modales(pid):
            botones: list[int] = []

            def mirar(hijo: int, _, acumulado=botones) -> bool:
                texto = win32gui.GetWindowText(hijo).replace("&", "").strip().lower()
                if win32gui.GetClassName(hijo) == "Button" and texto in {"no", "cancel"}:
                    acumulado.append(hijo)
                return True

            win32gui.EnumChildWindows(dialogo, mirar, None)
            if botones:
                win32gui.SendMessage(botones[0], win32con.BM_CLICK, 0, 0)
                time.sleep(0.5)
                return
        time.sleep(0.2)
    pytest.fail(
        "No se encontró el botón «No» del diálogo modal: cerralo a mano en Solid Edge "
        "(el diálogo «This file exists» sigue abierto)."
    )


def _hay_modal(sesion: Sesion) -> bool:
    pid = win32process.GetWindowThreadProcessId(_hwnd_de_solid_edge(sesion))[1]
    return bool(_dialogos_modales(pid))


@pytest.mark.live
def test_timeout_con_dialogo_modal(tmp_path):
    a, b = tmp_path / "A.par", tmp_path / "B.par"
    sesion = Sesion(plazo=PLAZO)
    previo: bool | None = None
    hwnd = None
    try:
        r, sobre = _cli("docs", "new", "part")
        assert r.exit_code == 0, sobre
        r, sobre = _cli("docs", "save-as", str(a))
        assert r.exit_code == 0, sobre
        shutil.copyfile(a, b)
        original = _hash(b)

        sesion.conectar()
        hwnd = _hwnd_de_solid_edge(sesion)
        previo = sesion.llamar(lambda app_: app_.DisplayAlerts)
        sesion.llamar(lambda app_: setattr(app_, "DisplayAlerts", True))

        # H1: el plazo corta la llamada que quedó esperando el diálogo.
        inicio = time.perf_counter()
        with pytest.raises(TiempoAgotado) as agotado:
            sesion.llamar(
                lambda app_: app_.ActiveDocument.SaveCopyAs(str(b)), reintentar_todo=False
            )
        transcurrido = time.perf_counter() - inicio
        detalles = agotado.value.details
        print(
            f"\nH1: {transcurrido:.2f} s, cancelacion={detalles['cancelacion']}, "
            f"hresult={agotado.value.hresult}"
        )
        assert transcurrido <= 10, transcurrido
        assert detalles["motivo"] == "timeout"

        # H3: con el modal abierto, la llamada siguiente de la misma sesión responde.
        inicio = time.perf_counter()
        version = sesion.llamar(lambda app_: app_.Version)
        siguiente = time.perf_counter() - inicio
        print(
            f"H3: app.Version={version!r} en {siguiente:.2f} s con el modal abierto "
            f"(hay modal: {_hay_modal(sesion)})"
        )
        assert version
        assert siguiente < 2, siguiente

        _cerrar_modal(hwnd)
        assert _hash(b) == original
        assert sesion.llamar(lambda app_: app_.Version)

        # H4/H6: el proceso de la CLI termina con exit 7 y no queda colgado.
        codigo = "from se_cli.cli import app; app()"
        inicio = time.perf_counter()
        proceso = subprocess.Popen(
            [
                sys.executable,
                "-c",
                codigo,
                "--json",
                "--timeout",
                str(PLAZO),
                "com",
                "invoke",
                "ActiveDocument.SaveCopyAs",
                json.dumps(str(b)),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            salida, errores = proceso.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proceso.kill()
            _cerrar_modal(hwnd)
            pytest.fail("H4: el proceso de la CLI quedó colgado más de 30 s.")
        transcurrido = time.perf_counter() - inicio
        print(f"H4/H6: exit={proceso.returncode} en {transcurrido:.2f} s; stdout={salida.strip()}")
        modal_abierto = _hay_modal(sesion)
        if modal_abierto:
            _cerrar_modal(hwnd)
        if proceso.returncode == 0 and not modal_abierto:
            pytest.skip(
                "H6: `com invoke` apaga DisplayAlerts y el diálogo no aparece; "
                "no hay forma de colgar la CLI con este comando."
            )
        assert proceso.returncode == 7, (salida, errores)
        assert transcurrido <= 12 + 3, transcurrido  # arranque de Python incluido
        sobre = json.loads(salida)
        assert sobre["error"]["code"] == "ocupado"
        assert sobre["error"]["details"]["motivo"] == "timeout"
        assert _hash(b) == original
        assert sesion.llamar(lambda app_: app_.Version)
    finally:
        if previo is not None:
            try:
                sesion.llamar(lambda app_: setattr(app_, "DisplayAlerts", previo))
            except Exception:  # noqa: BLE001 - el diálogo puede seguir abierto
                pass
        if hwnd is not None:
            pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            if _dialogos_modales(pid):
                _cerrar_modal(hwnd)
        _, sobre = _cli("docs", "list")
        for doc in reversed(sobre["data"]["documentos"]):
            if doc["nombre"] == "A.par":
                _cli("docs", "close", doc["nombre"], "--discard")
        sesion.cerrar()


@pytest.mark.live
def test_costo_de_habilitar_la_cancelacion():
    def medir(plazo):
        with HiloSta() as hilo:
            sesion = Sesion(sta=hilo, plazo=plazo)
            sesion.conectar()

            def bucle(app_):
                inicio = time.perf_counter()
                for _ in range(LLAMADAS_DE_COSTO):
                    _ = app_.Version
                return time.perf_counter() - inicio

            sesion.llamar(bucle)  # calentamiento
            return min(sesion.llamar(bucle) for _ in range(3))

    sin = medir(None)
    con = medir(60)
    print(f"\nH7: sin={sin * 1000:.1f} ms, con={con * 1000:.1f} ms, cociente={con / sin:.2f}")
    assert con / sin < 3
