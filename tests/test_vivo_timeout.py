"""`--timeout` contra un diálogo modal real de Solid Edge. No corre por defecto.

Las pruebas que abren un diálogo modal visible en Solid Edge durante unos segundos requieren
`SE_LIVE_MODAL=1`, además de la marca `live`.

Cada prueba abre una pieza propia en una carpeta temporal, provoca el diálogo «This file exists»
con `SaveCopyAs` sobre un archivo existente (con `DisplayAlerts = True`) y comprueba que el plazo
corta la espera, que la sesión sigue respondiendo y que el proceso termina con exit 7. El
diálogo se cierra con el botón «No» (sin matar Solid Edge); si no se lo encuentra, el test falla
y pide cerrarlo a mano. Al terminar cierra solo el documento que creó, sin guardar.
"""

import asyncio
import hashlib
import json
import os
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
from se_cli.core import sta as modulo_sta
from se_cli.core.errors import TiempoAgotado
from se_cli.core.session import Sesion
from se_cli.core.sta import HiloSta

PLAZO = 5
LLAMADAS_DE_COSTO = 500

modal = pytest.mark.skipif(
    os.environ.get("SE_LIVE_MODAL") != "1",
    reason=(
        "Abre un diálogo modal en Solid Edge: correr solo con SE_LIVE_MODAL=1 "
        "y avisando antes al usuario."
    ),
)

# Comando de prueba que corre por el mismo `ejecutar` que usa la CLI real y cuelga a propósito.
CODIGO_CLI = """
import sys
import typer
from se_cli.cli import app
from se_cli.core import sta
from se_cli.ejecucion import ejecutar

modo, destino = sys.argv[1], sys.argv[2]
if modo == "abandonada":
    sta.CANCELAR_POR_COM = False


@app.command("colgar")
def colgar(ctx: typer.Context) -> None:
    def correr(sesion):
        sesion.llamar(lambda a: setattr(a, "DisplayAlerts", True))
        return sesion.llamar(
            lambda a: a.ActiveDocument.SaveCopyAs(destino), reintentar_todo=False
        )

    ejecutar(ctx, correr)


sys.argv[1:] = ["--json", "--timeout", "5", "colgar"]
app()
"""

CODIGO_MCP = "from se_cli.mcp_server import main; main()"


def _cli(*args: str):
    resultado = CliRunner().invoke(app, ["--json", *args])
    return resultado, json.loads(resultado.stdout)


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _hwnd_de_solid_edge(sesion: Sesion) -> int:
    return sesion.llamar(lambda app_: app_.hWnd)


def _pid(hwnd: int) -> int:
    return win32process.GetWindowThreadProcessId(hwnd)[1]


def _dialogos_modales(pid: int) -> list[int]:
    encontrados: list[int] = []

    def mirar(hwnd: int, _) -> bool:
        if (
            win32gui.IsWindowVisible(hwnd)
            and win32gui.GetClassName(hwnd) == "#32770"
            and _pid(hwnd) == pid
        ):
            encontrados.append(hwnd)
        return True

    win32gui.EnumWindows(mirar, None)
    return encontrados


def _cerrar_modal(hwnd_principal: int, espera: float = 5.0) -> None:
    """Apretá «No» en el diálogo modal de Solid Edge, sin cerrar el programa."""
    pid = _pid(hwnd_principal)
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


def _cerrar_si_hay(hwnd_principal: int) -> None:
    if _dialogos_modales(_pid(hwnd_principal)):
        _cerrar_modal(hwnd_principal)


@pytest.fixture
def pieza(tmp_path):
    """Una pieza A.par abierta y guardada, y una copia B.par. Cierra todo al terminar."""
    a, b = tmp_path / "A.par", tmp_path / "B.par"
    sesion = Sesion(plazo=60)
    sesion.conectar()
    hwnd = _hwnd_de_solid_edge(sesion)
    previo = sesion.llamar(lambda app_: app_.DisplayAlerts)
    try:
        r, sobre = _cli("docs", "new", "part")
        assert r.exit_code == 0, sobre
        r, sobre = _cli("docs", "save-as", str(a))
        assert r.exit_code == 0, sobre
        shutil.copyfile(a, b)
        yield a, b, hwnd, _hash(b)
    finally:
        try:
            if _dialogos_modales(_pid(hwnd)):
                _cerrar_modal(hwnd)
        finally:
            sesion.llamar(lambda app_: setattr(app_, "DisplayAlerts", previo))
            _, sobre = _cli("docs", "list")
            for doc in reversed(sobre["data"]["documentos"]):
                if doc["nombre"] == "A.par":
                    _cli("docs", "close", doc["nombre"], "--discard")
            sesion.cerrar()


def _abrir_modal(sesion: Sesion, b: Path) -> TiempoAgotado:
    sesion.llamar(lambda app_: setattr(app_, "DisplayAlerts", True))
    inicio = time.perf_counter()
    with pytest.raises(TiempoAgotado) as agotado:
        sesion.llamar(lambda app_: app_.ActiveDocument.SaveCopyAs(str(b)), reintentar_todo=False)
    transcurrido = time.perf_counter() - inicio
    print(
        f"\n  corte en {transcurrido:.2f} s, cancelacion={agotado.value.details['cancelacion']}, "
        f"hresult={agotado.value.hresult and hex(agotado.value.hresult)}"
    )
    assert transcurrido <= 10, transcurrido
    assert agotado.value.details["motivo"] == "timeout"
    return agotado.value


@pytest.mark.live
@modal
def test_h1_h3_cancela_y_la_sesion_sigue(pieza):
    _, b, hwnd, original = pieza
    sesion = Sesion(plazo=PLAZO)
    sesion.conectar()
    try:
        error = _abrir_modal(sesion, b)
        assert error.details["cancelacion"] == "cancelada"
        assert error.hresult in (0x80010002, 0x8001011F)

        inicio = time.perf_counter()
        version = sesion.llamar(lambda app_: app_.Version)
        siguiente = time.perf_counter() - inicio
        hay_modal = bool(_dialogos_modales(_pid(hwnd)))
        print(f"  H3: Version={version!r} en {siguiente:.2f} s, modal abierto: {hay_modal}")
        assert version and siguiente < 2 and hay_modal
    finally:
        _cerrar_si_hay(hwnd)
    assert _hash(b) == original
    assert sesion.llamar(lambda app_: app_.Version)
    sesion.cerrar()


@pytest.mark.live
@modal
def test_plan_b_abandona_y_la_sesion_sigue(pieza, monkeypatch):
    _, b, hwnd, original = pieza
    monkeypatch.setattr(modulo_sta, "CANCELAR_POR_COM", False)
    with HiloSta() as hilo:
        sesion = Sesion(sta=hilo, plazo=PLAZO)
        sesion.conectar()
        try:
            error = _abrir_modal(sesion, b)
            assert error.details["cancelacion"] == "abandonada"
            assert hilo.generacion == 1

            inicio = time.perf_counter()
            version = sesion.llamar(lambda app_: app_.Version)
            siguiente = time.perf_counter() - inicio
            print(f"  plan B: Version={version!r} en {siguiente:.2f} s en el hilo nuevo")
            assert version and siguiente < 5
        finally:
            _cerrar_si_hay(hwnd)
        assert _hash(b) == original
        assert sesion.llamar(lambda app_: app_.Version)
        sesion.cerrar()


@pytest.mark.live
@modal
@pytest.mark.parametrize("modo", ["cancelada", "abandonada"])
def test_h4_la_cli_termina_con_exit_7(pieza, modo):
    _, b, hwnd, original = pieza
    inicio = time.perf_counter()
    proceso = subprocess.Popen(
        [sys.executable, "-c", CODIGO_CLI, modo, str(b)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        salida, errores = proceso.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proceso.kill()
        pytest.fail("H4: el proceso de la CLI quedó colgado más de 30 s.")
    finally:
        # El proceso ya terminó (o se mató): el diálogo sigue en Solid Edge.
        if _dialogos_modales(_pid(hwnd)):
            _cerrar_modal(hwnd)
    transcurrido = time.perf_counter() - inicio
    print(f"\n  H4 ({modo}): exit={proceso.returncode} en {transcurrido:.2f} s; {salida.strip()}")
    assert proceso.returncode == 7, (salida, errores)
    sobre = json.loads(salida)
    assert sobre["error"]["code"] == "ocupado"
    assert sobre["error"]["details"]["motivo"] == "timeout"
    assert sobre["error"]["details"]["cancelacion"] == modo
    assert transcurrido <= 12 + 3, transcurrido  # plazo + gracia + arranque de Python
    assert _hash(b) == original


@pytest.mark.live
@modal
def test_h6_com_invoke_no_abre_el_modal(pieza):
    """`se com invoke` apaga `DisplayAlerts`: el diálogo no aparece y no hay cómo colgarlo."""
    _, b, hwnd, _ = pieza
    ruta = json.dumps(str(b))
    r, sobre = _cli("--timeout", "5", "com", "invoke", "ActiveDocument.SaveCopyAs", ruta)
    print(f"\n  H6: exit={r.exit_code}, modal abierto: {bool(_dialogos_modales(_pid(hwnd)))}")
    assert r.exit_code == 0, sobre
    assert not _dialogos_modales(_pid(hwnd))


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
    print(f"\n  H7: sin={sin * 1000:.1f} ms, con={con * 1000:.1f} ms, cociente={con / sin:.2f}")
    assert con / sin < 3


@pytest.mark.live
@modal
def test_mcp_stdio_ocupado_y_el_servidor_sigue(pieza):
    """Una tool con `timeout` chico devuelve `ocupado` y el `status` siguiente responde."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    a, _, _, _ = pieza
    r, sobre = _cli("docs", "close", "A.par", "--discard")
    assert r.exit_code == 0, sobre

    async def recorrido():
        parametros = StdioServerParameters(command=sys.executable, args=["-c", CODIGO_MCP])
        async with stdio_client(parametros) as (leer, escribir):
            async with ClientSession(leer, escribir) as sesion:
                await sesion.initialize()
                inicio = time.perf_counter()
                lento = await sesion.call_tool("docs_open", {"path": str(a), "timeout": 0.05})
                demora = time.perf_counter() - inicio
                estado = await sesion.call_tool("status", {})
                return lento.structuredContent, demora, estado.structuredContent

    lento, demora, estado = asyncio.run(recorrido())
    print(f"\n  MCP: {lento['error']['code']} en {demora:.2f} s; status: {estado['data']}")
    assert lento["ok"] is False and lento["error"]["code"] == "ocupado"
    assert estado["ok"] is True and estado["data"]["conectado"] is True
    # `docs_open` pudo completarse igual: el fixture cierra A.par si quedó abierto.
