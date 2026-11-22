"""Probá COM contra una instancia abierta de Solid Edge.

Esta prueba previa al núcleo es la única excepción al acceso COM por se_cli/core.
"""

import argparse
import json
import re
import time
import zlib
from datetime import datetime
from pathlib import Path

PROGID = "SolidEdge.Application"
MK_E_UNAVAILABLE = 0x800401E3
RPC_E_CALL_REJECTED = 0x80010001
RPC_E_SERVERCALL_RETRYLATER = 0x8001010A

PLANO_BASE = 1  # Primer plano de referencia de la plantilla Part (índice COM).
PERFIL_CERRADO = 1  # igProfileClosed, ProfileValidationType.
LADO_POSITIVO = 2  # igRight, FeaturePropertyConstants.
VISTA_FRONTAL = 4  # igFrontView, ViewOrientationConstants.
OPCIONES_VISTA = 0  # Sin opciones adicionales para AddPartView.
LADO_CUBO = 0.05  # Metros.

CADENAS_MARCA = ("Community", "Academic", "Student", "Not for commercial", "Siemens")
CONFIRMAR_PDF = "Confirmá el resultado abriendo el PDF."


def reintentar(fn, intentos=10, espera=0.5):
    """Reintentá una llamada individual si Solid Edge está ocupado."""
    from pywintypes import com_error

    if intentos < 1:
        raise ValueError("Tiene que haber al menos un intento.")
    for intento in range(intentos):
        try:
            return fn()
        except com_error as error:
            hresult = error.hresult & 0xFFFFFFFF
            if (
                hresult not in (RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER)
                or intento == intentos - 1
            ):
                raise
            time.sleep(espera)


def detectar_marca_de_agua(pdf):
    """Buscá indicios en bytes de PDF y streams FlateDecode simples."""
    fragmentos = [pdf]
    lectura_parcial = not (pdf.startswith(b"%PDF-") and b"%%EOF" in pdf)
    streams = re.finditer(rb"\bstream\r?\n(.*?)\r?\nendstream\b", pdf, re.DOTALL)
    cantidad = 0
    for stream in streams:
        cantidad += 1
        # Buscá el diccionario del objeto que precede al stream.
        inicio_objeto = pdf.rfind(b" obj", 0, stream.start())
        cabecera = pdf[inicio_objeto + 4 : stream.start()] if inicio_objeto >= 0 else b""
        if not re.search(rb"/Filter\b", cabecera):
            continue
        if not re.search(rb"/Filter\s*(?:/FlateDecode\b|\[\s*/FlateDecode\s*\])", cabecera):
            lectura_parcial = True
            continue
        try:
            fragmentos.append(zlib.decompress(stream[1]))
        except zlib.error:
            lectura_parcial = True
    if cantidad != len(re.findall(rb"\bstream\r?\n", pdf)) or re.search(rb"/Encrypt\b", pdf):
        lectura_parcial = True

    halladas = [
        cadena
        for cadena in CADENAS_MARCA
        if any(
            cadena.lower().encode(codificacion) in fragmento.lower()
            for fragmento in fragmentos
            for codificacion in ("ascii", "utf-16-be", "utf-16-le")
        )
    ]
    estado = "detectada" if halladas else "indeterminada" if lectura_parcial else "no detectada"
    return {"estado": estado, "cadenas": halladas, "mensaje": CONFIRMAR_PDF}


def reservar_salida():
    raiz = Path(__file__).resolve().parents[1] / "out" / "smoke"
    try:
        raiz.mkdir(parents=True)
    except FileExistsError:
        if not raiz.is_dir():
            raise
    else:
        return raiz

    segundo = int(time.time())
    while True:
        carpeta = raiz / datetime.fromtimestamp(segundo).strftime("%Y%m%d-%H%M%S")
        try:
            carpeta.mkdir()
        except FileExistsError:
            segundo += 1
        else:
            return carpeta


def registrar_paso(pasos, nombre, accion, *, requiere=True):
    inicio = time.perf_counter()
    paso = {"nombre": nombre, "ok": False}
    valor = None
    try:
        if not requiere:
            raise RuntimeError("Omitido porque falló un paso previo.")
        valor = accion()
    except Exception as error:
        paso["error"] = str(error)
    else:
        paso["ok"] = True
    paso["duracion_s"] = round(time.perf_counter() - inicio, 4)
    pasos.append(paso)
    return valor


def crear_cubo(part):
    plano = reintentar(lambda: part.RefPlanes.Item(PLANO_BASE))
    conjunto = reintentar(lambda: part.ProfileSets.Add())
    perfil = reintentar(lambda: conjunto.Profiles.Add(plano))
    lineas = reintentar(lambda: perfil.Lines2d)
    vertices = [(0.0, 0.0), (LADO_CUBO, 0.0), (LADO_CUBO, LADO_CUBO), (0.0, LADO_CUBO)]
    for origen, destino in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        reintentar(lambda origen=origen, destino=destino: lineas.AddBy2Points(*origen, *destino))
    estado = reintentar(lambda: perfil.End(PERFIL_CERRADO))
    if estado != 0:
        raise RuntimeError(f"Profile.End devolvió {estado} al validar el rectángulo.")
    modelos = reintentar(lambda: part.Models)
    reintentar(lambda: modelos.AddFiniteExtrudedProtrusion(1, (perfil,), LADO_POSITIVO, LADO_CUBO))


def crear_vista(draft, ruta_part):
    enlace = reintentar(lambda: draft.ModelLinks.Add(str(ruta_part)))
    vistas = reintentar(lambda: draft.ActiveSheet.DrawingViews)
    reintentar(lambda: vistas.AddPartView(enlace, VISTA_FRONTAL, 1.0, 0.10, 0.10, OPCIONES_VISTA))


def guardar(archivos, ruta, metodo, rutas_previas):
    if ruta.exists() or ruta in rutas_previas:
        raise FileExistsError(f"La ruta de salida ya está en uso: {ruta}")
    reintentar(lambda: metodo(str(ruta)))
    if not ruta.is_file() or ruta.stat().st_size == 0:
        raise RuntimeError(f"Solid Edge no escribió un archivo con contenido en {ruta}.")
    archivos[ruta.suffix[1:]] = str(ruta)
    return ruta


def probar_sesion(app, salida, data, dejar_abiertos):
    import pythoncom

    pasos, archivos = data["pasos"], data["archivos"]
    documentos = reintentar(lambda: app.Documents)
    cantidad = reintentar(lambda: documentos.Count)
    previos = [
        reintentar(lambda indice=indice: documentos.Item(indice))
        for indice in range(1, cantidad + 1)
    ]
    identidades = [
        reintentar(lambda doc=doc: doc._oleobj_.QueryInterface(pythoncom.IID_IUnknown))
        for doc in previos
    ]
    nombres = []
    for doc in previos:
        nombre = reintentar(lambda doc=doc: doc.FullName or doc.Name)
        nombres.append(nombre)
    rutas_previas = {Path(nombre).resolve() for nombre in nombres if Path(nombre).is_absolute()}
    data["documentos_previos"] = nombres
    activo = (
        registrar_paso(
            pasos,
            "Identificar documento activo",
            lambda: reintentar(lambda: app.ActiveDocument),
        )
        if cantidad
        else None
    )

    def leer_aplicacion():
        data["version"] = str(reintentar(lambda: app.Version))
        data["aplicacion"] = str(reintentar(lambda: app.Name))
        data["cantidad_documentos_previos"] = cantidad

    def nuevo_documento(tipo):
        doc = reintentar(lambda: documentos.Add(f"SolidEdge.{tipo}Document"))
        identidad = reintentar(lambda: doc._oleobj_.QueryInterface(pythoncom.IID_IUnknown))
        if identidad in identidades:
            raise RuntimeError(f"Documents.Add devolvió un {tipo} que ya estaba abierto.")
        creados.append((tipo, doc))
        return doc

    registrar_paso(pasos, "Leer aplicación", leer_aplicacion)
    alertas_previas = reintentar(lambda: app.DisplayAlerts)
    creados = []
    try:
        reintentar(lambda: setattr(app, "DisplayAlerts", False))
        part = registrar_paso(pasos, "Crear Part", lambda: nuevo_documento("Part"))
        registrar_paso(
            pasos, "Extruir cubo de 50 mm", lambda: crear_cubo(part), requiere=part is not None
        )
        cubo_creado = pasos[-1]["ok"]
        ruta_part = registrar_paso(
            pasos,
            "Guardar Part",
            lambda: guardar(
                archivos, salida / "cubo.par", lambda ruta: part.SaveAs(ruta), rutas_previas
            ),
            requiere=cubo_creado,
        )
        registrar_paso(
            pasos,
            "Exportar STEP",
            lambda: guardar(
                archivos, salida / "cubo.stp", lambda ruta: part.SaveCopyAs(ruta), rutas_previas
            ),
            requiere=cubo_creado,
        )
        draft = registrar_paso(pasos, "Crear Draft", lambda: nuevo_documento("Draft"))
        registrar_paso(
            pasos,
            "Enlazar Part y crear vista",
            lambda: crear_vista(draft, ruta_part),
            requiere=draft is not None and ruta_part is not None,
        )
        vista_creada = pasos[-1]["ok"]
        registrar_paso(
            pasos,
            "Guardar Draft",
            lambda: guardar(
                archivos, salida / "cubo.dft", lambda ruta: draft.SaveAs(ruta), rutas_previas
            ),
            requiere=vista_creada,
        )
        ruta_pdf = registrar_paso(
            pasos,
            "Exportar PDF",
            lambda: guardar(
                archivos, salida / "cubo.pdf", lambda ruta: draft.SaveCopyAs(ruta), rutas_previas
            ),
            requiere=vista_creada,
        )
        marca = registrar_paso(
            pasos,
            "Inspeccionar marca de agua",
            lambda: detectar_marca_de_agua(ruta_pdf.read_bytes()),
            requiere=ruta_pdf is not None,
        )
        if marca is not None:
            data["marca_de_agua"] = marca
    finally:
        try:
            if not dejar_abiertos:
                for tipo, doc in reversed(creados):
                    registrar_paso(
                        pasos,
                        f"Cerrar {tipo}",
                        lambda doc=doc: reintentar(lambda: doc.Close(False)),
                    )
            if activo is not None:
                registrar_paso(
                    pasos,
                    "Reactivar documento previo",
                    lambda: reintentar(lambda: activo.Activate()),
                )
        finally:
            registrar_paso(
                pasos,
                "Restaurar DisplayAlerts",
                lambda: reintentar(lambda: setattr(app, "DisplayAlerts", alertas_previas)),
            )


def ejecutar_com(salida, data, dejar_abiertos):
    import pythoncom
    import win32com.client
    from pywintypes import com_error
    from win32com.client import dynamic

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = None
    try:
        try:
            activa = reintentar(lambda: win32com.client.GetActiveObject(PROGID))
        except com_error as error:
            if error.hresult & 0xFFFFFFFF == MK_E_UNAVAILABLE:
                return 2, "No hay una instancia de Solid Edge abierta disponible por COM."
            raise

        # Pasá el IDispatch de la instancia existente al wrapper dinámico.
        app = dynamic.Dispatch(activa._oleobj_)
        del activa
        probar_sesion(app, salida, data, dejar_abiertos)
        return 0, None
    finally:
        del app
        pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dejar-abiertos", action="store_true", help="Dejá abiertos el Part y el Draft."
    )
    parser.add_argument("--json", action="store_true", help="Imprimí el resultado en JSON.")
    args = parser.parse_args()
    data = {
        "version": None,
        "pasos": [],
        "archivos": {},
        "marca_de_agua": {"estado": "indeterminada", "cadenas": [], "mensaje": CONFIRMAR_PDF},
    }

    salida = None
    try:
        salida = reservar_salida()
        codigo, error = ejecutar_com(salida, data, args.dejar_abiertos)
    except Exception as exc:
        codigo, error = 1, str(exc)
    if codigo == 0 and any(not paso["ok"] for paso in data["pasos"]):
        codigo, error = 1, "Falló al menos un paso del smoke."

    resultado = {"ok": codigo == 0, "data": data, "error": error}
    if salida is not None:
        try:
            (salida / "resultado.json").write_text(
                json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            codigo = 1
            resultado["ok"] = False
            detalle = f"No se pudo escribir resultado.json ({exc})."
            resultado["error"] = f"{error} {detalle}" if error else detalle
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        print("Smoke de Solid Edge" + (f" {data['version']}" if data["version"] else ""))
        for paso in data["pasos"]:
            estado = "ok" if paso["ok"] else "error"
            detalle = f" · {paso['error']}" if "error" in paso else ""
            print(f"  {estado} · {paso['nombre']} ({paso['duracion_s']:.4f} s){detalle}")
        marca = data["marca_de_agua"]
        cadenas = ", ".join(marca["cadenas"]) or "ninguna"
        print(f"Marca de agua {marca['estado']} · cadenas halladas: {cadenas}. {marca['mensaje']}")
        if salida is not None:
            print(f"Salida en {salida}")
        if resultado["error"]:
            print(resultado["error"])
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
