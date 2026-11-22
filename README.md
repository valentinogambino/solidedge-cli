# solidedge-cli

`se` es una CLI para manejar Solid Edge 2026 Community Edition por COM desde la terminal.

Necesitás Windows, Solid Edge 2026 y uv. Para correr la receta de tests, instalá también just.

```powershell
uv sync
uv run se --help
just test
```

Para verificar F0, abrí Solid Edge y corré `uv run python scripts/smoke.py`.
Los archivos de la prueba quedan en `out/smoke/`.

## Opciones globales

Van antes del comando: `se --json docs list`.

| opción | efecto |
|---|---|
| `--json` | Salida `{ok, data, error}` en una línea por stdout, sin colores. Sin `--json` sale una tabla y los errores van a stderr. |
| `--readonly` | Bloquea todo comando que modifica (`open`, `new`, `save`, `save-as`, `close`, `quit`, `connect --launch`): exit 6, `solo_lectura`, sin tocar Solid Edge. |
| `--dry-run` | Los comandos que modifican informan qué harían (`"dry_run": true`) sin llamar a COM de escritura. Los argumentos se validan igual. |
| `--version` | Versión de `se`. |

Cada invocación es un proceso nuevo: se engancha a la instancia abierta y la suelta al terminar.
Solo `se connect --launch` arranca Solid Edge.

## Sesión

```powershell
se --json connect
# {"ok": true, "data": {"version": "226.00.00.00", "nombre": "Solid Edge", "lanzada": false}, "error": null}
```
Sin instancia abierta sale con exit 3. `se connect --launch` la lanza (modifica: lo bloquea `--readonly`).

```powershell
se --json status
# {"ok": true, "data": {"conectado": true, "version": "226.00.00.00", "nombre": "Solid Edge", "visible": true, "documentos": 2, "activo": "Pieza.par"}, "error": null}
```
Sin instancia **no** es error: sale exit 0 con `"conectado": false`, para sondear desde un agente.

```powershell
se --json quit --yes
# {"ok": true, "data": {"cerrada": true, "descartados": []}, "error": null}
```
Exige `--yes` (exit 2 sin él). Con documentos con cambios sin guardar se niega (exit 6) salvo `--discard`.

## Documentos

Un `<doc>` es un índice (1-based, como `docs list`), un nombre exacto (sin distinguir
mayúsculas) o una ruta completa; ambiguo o inexistente da exit 5. Sin `<doc>` se usa el activo.
Guardar y cerrar corren con `DisplayAlerts` apagado (se restaura siempre) para que no salgan
diálogos modales.

```powershell
se --json docs list
# {"ok": true, "data": {"cantidad": 1, "documentos": [{"indice": 1, "nombre": "Pieza.par", "ruta": "C:\\p\\Pieza.par", "tipo": "part", "modificado": false, "activo": true, "solo_lectura": false}]}, "error": null}
```
`tipo`: `part`, `assembly`, `draft`, `sheetmetal`, `weldment` o `desconocido` (más los tipos
de sync y visores con su nombre de constante). `ruta` es `null` si el documento nunca se guardó.

```powershell
se --json docs active
# {"ok": true, "data": {"indice": 1, "nombre": "Pieza.par", "ruta": "C:\\p\\Pieza.par", "tipo": "part", "modificado": false, "activo": true, "solo_lectura": false}, "error": null}
```
Sin documento activo: exit 5.

```powershell
se --json docs open C:\p\Pieza.par [--read-only-doc]
# {"ok": true, "data": {"indice": 1, "nombre": "Pieza.par", ..., "ya_abierto": false}, "error": null}
```
Ruta inexistente: exit 5. Si ya estaba abierto lo activa y devuelve `"ya_abierto": true`.

```powershell
se --json docs new part [--template C:\p\base.par]
# {"ok": true, "data": {"indice": 2, "nombre": "Document2", "ruta": null, "tipo": "part", ...}, "error": null}
```
Tipos: `part`, `assembly`, `draft`, `sheetmetal`, `weldment`. Tipo inválido: exit 2. `weldment`
exige `--template`.

```powershell
se --json docs save [<doc>]
# {"ok": true, "data": {..., "modificado": false, "guardado": true}, "error": null}
```
Un documento que nunca se guardó da exit 2 y pide `save-as`.

```powershell
se --json docs save-as C:\p\Copia.par [<doc>] [--overwrite]
# {"ok": true, "data": {..., "guardado": true, "destino": "C:\\p\\Copia.par", "existe": true}, "error": null}
```
Si el destino existe y no se pasó `--overwrite`: exit 6 (Solid Edge abriría un diálogo que
`DisplayAlerts` no suprime). Con `--overwrite` el archivo anterior se aparta y se restaura si el
guardado falla.

```powershell
se --json docs close [<doc>] [--save | --discard]
# {"ok": true, "data": {"cerrado": true, "documento": "Pieza.par", "guardado": false, "descartado": false}, "error": null}
se --json docs close --all --yes [--save | --discard]
# {"ok": true, "data": {"cerrados": ["B.par", "A.par"], "cantidad": 2}, "error": null}
```
Con cambios sin guardar y sin `--save` ni `--discard` se niega (exit 6) y no cierra nada. `--all`
exige `--yes`; si algún documento tiene cambios y no hay flag, no cierra ninguno.

## Datos del modelo

Todos aceptan `--doc <selector>` (el mismo que `se docs`: índice, nombre o ruta; por defecto el
activo; inexistente da exit 5). Los valores numéricos viven en SI (metros, radianes, kilogramos);
`--units` los muestra en otra unidad y los valores que se escriben admiten unidad.

### Unidades

Un valor sin unidad es SI. El separador decimal es el punto: `1,5mm` da exit 2. Un valor
negativo va después de `--` (`se vars set Largo -- -5mm`). `--units` acepta una lista separada
por comas con a lo sumo una unidad por dimensión (`--units mm,deg,g`).

| dimensión | unidades | factor a SI |
|---|---|---|
| longitud | `m`, `mm`, `cm`, `in`, `ft` | 1, 0.001, 0.01, 0.0254 (exacto), 0.3048 |
| ángulo | `rad`, `deg` | 1, pi/180 |
| masa | `kg`, `g`, `lb` | 1, 0.001, 0.45359237 |

### Variables y cotas

```powershell
se --json vars list [--filter "Largo*"] [--units mm]
# {"ok": true, "data": {"cantidad": 1, "variables": [{"nombre": "Largo", "valor_si": 0.1, "valor": 100.0, "unidad": "mm", "formula": null, "tipo_unidad": "distance", "es_cota": false, "solo_lectura": false}]}, "error": null}
```
`--filter` usa comodines `*` y `?`. Incluye las cotas (`es_cota: true`). Un campo que la API no
entrega queda en `null`.

```powershell
se --json vars get Largo [--units mm]
# {"ok": true, "data": {"nombre": "Largo", "valor_si": 0.1, "valor": 0.1, "unidad": "m", "formula": null, "tipo_unidad": "distance", "es_cota": false, "solo_lectura": false}, "error": null}
```
Inexistente: exit 5.

```powershell
se --json vars set Largo 120mm
# {"ok": true, "data": {"nombre": "Largo", "antes": {"valor_si": 0.1, "valor": 0.1, "unidad": "m", "formula": null}, "despues": {"valor_si": 0.12, "valor": 0.12, "unidad": "m", "formula": null}}, "error": null}
se --json vars set Largo --formula "Ancho*2"
```
El valor se convierte a SI antes de escribir; una unidad de otra dimensión (`45deg` en una
distancia) da exit 2. Una variable de solo lectura, o gobernada por una fórmula cuando se pone un
valor, da exit 6 salvo `--force` (la API decide si lo acepta).

```powershell
se --json vars add Alto 80mm [--unit-type distance]
# {"ok": true, "data": {"nombre": "Alto", "valor_si": 0.08, "valor": 0.08, "unidad": "m", "formula": null, "tipo_unidad": "distance", "es_cota": false, "solo_lectura": false}, "error": null}
```
`--unit-type`: `distance`, `angle`, `mass`, `scalar`, `area`, `volume`, `density`... (nombres de
`UnitTypeConstants`); por defecto se deduce de la unidad del valor. Si ya existe: exit 6.

### Propiedades de archivo

```powershell
se --json props get [<nombre>] [--set Custom]
# {"ok": true, "data": {"cantidad": 2, "propiedades": [{"conjunto": "SummaryInformation", "nombre": "Title", "valor": "Soporte"}, {"conjunto": "Custom", "nombre": "Proveedor", "valor": "ACME"}]}, "error": null}
se --json props get Title
# {"ok": true, "data": {"conjunto": "SummaryInformation", "nombre": "Title", "valor": "Soporte"}, "error": null}
```
Una propiedad inexistente da exit 5; si está en varios conjuntos pide `--set` (exit 2).

```powershell
se --json props set Lote L-7 [--set Custom] [--save]
# {"ok": true, "data": {"conjunto": "Custom", "nombre": "Lote", "antes": null, "despues": "L-7", "creada": true, "guardado": false}, "error": null}
```
En `Custom` crea la propiedad si no existe; en los demás conjuntos una propiedad inexistente da
exit 5. No guarda el documento (`guardado: false`) salvo `--save`.

### Propiedades físicas

```powershell
se --json mass [--density 7850] [--units mm,g]
# {"ok": true, "data": {"masa": 5.4, "volumen": 0.002, "area": 0.1, "densidad": 2700.0, "centro_de_masa": [0.1, 0.2, 0.3], "centro_de_volumen": [0.11, 0.21, 0.31], "momentos_de_inercia": {"Ixx": 1.0, "Iyy": 2.0, "Izz": 3.0, "Ixy": 0.1, "Ixz": 0.2, "Iyz": 0.3}, "momentos_principales": [1.5, 2.5, 3.5], "ejes_principales": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0], "radios_de_giro": [0.01, 0.02, 0.03], "actualizado": false, "unidades": {"masa": "kg", "longitud": "m", "volumen": "m^3", "area": "m^2", "densidad": "kg/m^3", "inercia": "kg*m^2"}}, "error": null}
```
Sin `--density` lee las propiedades físicas ya guardadas en el modelo (solo lectura,
`actualizado: false`); si no hay, exit 2 y pide `--density`. Con `--density` (kg/m3) recalcula,
lo que modifica el estado del documento: lo bloquea `--readonly` y `--dry-run` solo informa.
Solo pieza, chapa y ensamble; otro tipo de documento da exit 2.

### Ensambles y operaciones

```powershell
se --json asm tree [--depth 10]
# {"ok": true, "data": {"documento": "Conj.asm", "profundidad": 10, "arbol": [{"nombre": "Sub.asm:1", "archivo": "C:\p\Sub.asm", "cantidad": 2, "visible": true, "ensamble": true, "hijos": [{"nombre": "tornillo.par:1", "archivo": "C:\p\tornillo.par", "cantidad": 3, "visible": true, "ensamble": false, "hijos": []}]}]}, "error": null}
se --json asm tree --flat
# {"ok": true, "data": {"documento": "Conj.asm", "cantidad": 2, "materiales": [{"archivo": "C:\p\Sub.asm", "cantidad": 2, "ensamble": true}, {"archivo": "C:\p\tornillo.par", "cantidad": 6, "ensamble": false}]}, "error": null}
```
Las ocurrencias hermanas del mismo archivo se agrupan en `cantidad`. `--depth` es la cantidad de
niveles a expandir (1 = solo el primer nivel; lo que queda sin expandir lleva `truncado: true`);
un ciclo se corta con `ciclo: true`. `--flat` multiplica las cantidades a través de los
subensambles. En modo humano el árbol sale con `rich.tree`. Solo ensambles: otro tipo da exit 2.
`Occurrence` no tiene miembro de supresión, así que el nodo no informa `suprimido`.

```powershell
se --json features list
# {"ok": true, "data": {"cantidad": 2, "operaciones": [{"indice": 1, "nombre": "ExtrudedProtrusion_1", "tipo": "ExtrudedProtrusion", "suprimida": false, "estado": "ok"}, {"indice": 2, "nombre": "ExtrudedCutout_1", "tipo": "ExtrudedCutout", "suprimida": true, "estado": "suppressed"}]}, "error": null}
```
`indice` es 1-based. `tipo` sale de `FeatureTypeConstants` (el entero si no tiene nombre). Solo
pieza y chapa: otro tipo da exit 2.

## Exportar y Draft

Los tres comandos escriben archivos (`export` además abre y cierra documentos en un lote), así que
cuentan como que modifican: `--readonly` los bloquea (exit 6) y `--dry-run` informa qué harían
sin tocar Solid Edge ni el disco. Corren con `DisplayAlerts` apagado (se restaura siempre).

**Estado de la validación:** todo F4 se probó contra un COM falso. Las llamadas a Solid Edge
(`SaveCopyAs` por extensión, `View.SaveAsImage`, `ModelLinks.Add`, `DrawingViews.Add*View`,
`SaveAsFlatDXFEx`, tamaños de hoja) todavía **no se validaron en vivo**; cada una está aislada en
una función pequeña de `src/se_cli/core/` para corregirla fácil.

**Marca de agua:** en Community Edition el PDF y el DXF pueden salir con marca de agua. Todavía no
se verificó, así que esos resultados traen `"marca_de_agua": "sin verificar"` y una `nota`.

### Formatos y tipos de documento

| `--format` | alias | extensión de salida | documentos que admite |
|---|---|---|---|
| `step` | `stp` | `.stp` (también acepta `.step` en `--out`) | `part`, `sheetmetal`, `assembly` |
| `stl` | | `.stl` | `part`, `sheetmetal`, `assembly` |
| `x_t` | `parasolid` | `.x_t` | `part`, `sheetmetal`, `assembly` |
| `igs` | `iges` | `.igs` (también `.iges`) | `part`, `sheetmetal`, `assembly` |
| `pdf` | | `.pdf` | `draft` |
| `dxf` | | `.dxf` | `draft` |
| `png` | | `.png` | `part`, `sheetmetal`, `assembly`, `draft` (la vista de la ventana, 1920x1080) |

Los documentos síncronos (`syncpart`, ...) se tratan como su versión ordenada. Un formato que no
encaja con el tipo del documento da exit 2 antes de escribir nada. Todo sale por `SaveCopyAs`
(salvo `png`, que usa `View.SaveAsImage`): no reapunta el documento vivo a la copia.

### `se export`

```powershell
se --json export --format step                       # documento activo, junto al documento
se --json export --format pdf --doc Plano.dft --out C:\salida\plano.pdf --overwrite
# {"ok": true, "data": {"entrada": "C:\\p\\Pieza.par", "documento": "Pieza.par", "tipo": "part", "formato": "step", "salida": "C:\\p\\Pieza.stp", "ok": true, "bytes": 8152, "duracion_s": 0.41}, "error": null}
```
Sin entradas exporta el documento activo (o `--doc`). Tiene que estar guardado o, si no, exige
`--out` con ruta de archivo. `--out` puede ser un archivo (sin extensión se le pone la del formato;
con la de otro formato da exit 2) o una carpeta existente. Si la salida ya existe y no hay
`--overwrite`: exit 6 (Solid Edge abriría un diálogo modal que `DisplayAlerts` no suprime); con
`--overwrite` el archivo anterior se aparta y se restaura si la exportación falla. Después de
exportar se verifica que el archivo exista y pese más de 0 bytes; si no, exit 4.

```powershell
se --json export .\*.par --format step --out C:\salida   # lote: Python expande el glob
se --json export .\piezas --format stl --recursive
# {"ok": true, "data": {"formato": "step", "salida": "C:\\salida", "resultados": [{"entrada": "C:\\p\\A.par", "salida": "C:\\salida\\A.stp", "ok": true, "bytes": 8152, "duracion_s": 1.2}, {"entrada": "C:\\p\\B.par", "salida": "C:\\salida\\B.stp", "ok": true, "bytes": 9120, "duracion_s": 0.9}], "resumen": {"total": 2, "ok": 2, "fallidos": 0}}, "error": null}
```
Con entradas (archivos, carpetas o globs; en Windows el shell no expande `*`, lo hace `se`) exporta
un lote. Una carpeta toma los archivos `.par`, `.psm`, `.asm` y `.dft` compatibles con el formato
(`--recursive` baja por las subcarpetas y habilita `**` en los globs). Un archivo explícito que no
es compatible da exit 2, uno inexistente o un glob sin coincidencias exit 5. `--out` tiene que ser
una carpeta (se crea). Dos entradas que darían la misma salida son exit 2.

Por archivo: si ya está abierto se usa esa instancia y **no se cierra**; si no, se abre, se
exporta y se cierra sin guardar (`Close(False)`). Al terminar queda activo el documento que lo
estaba antes. Una salida que ya existe sin `--overwrite` deja a ese archivo en `ok: false` (código
`solo_lectura`) sin cortar el lote.

Si algún archivo falla el lote termina con **exit 1** y `ok: false`, y los resultados parciales
van en `error.details` (mismas claves `resultados` y `resumen`):

```powershell
# {"ok": false, "data": null, "error": {"code": "lote_con_fallos", "message": "Fallaron 1 de 2 exportaciones. B.par: Ya existe C:\\salida\\B.stp. Usá --overwrite para reemplazarlo.", "details": {"formato": "step", "salida": "C:\\salida", "resultados": [{"entrada": "C:\\p\\A.par", "salida": "C:\\salida\\A.stp", "ok": true, "bytes": 8152, "duracion_s": 1.2}, {"entrada": "C:\\p\\B.par", "salida": "C:\\salida\\B.stp", "ok": false, "error": {"code": "solo_lectura", "message": "Ya existe C:\\salida\\B.stp. Usá --overwrite para reemplazarlo.", "details": {"ruta": "C:\\salida\\B.stp"}}, "duracion_s": 0.0}], "resumen": {"total": 2, "ok": 1, "fallidos": 1}}}}
```

Con `--dry-run` lista entradas y salidas:

```powershell
se --json --dry-run export .\*.par --format step
# {"ok": true, "data": {"dry_run": true, "accion": "export", "formato": "step", "entradas": [{"entrada": "C:\\p\\A.par", "salida": "C:\\p\\A.stp"}], "overwrite": false}, "error": null}
```

### `se draft from-part`

```powershell
se --json draft from-part C:\p\Pieza.par --views front,top,right,iso --scale auto --sheet A3 --pdf
# {"ok": true, "data": {"draft": "C:\\p\\Pieza.dft", "modelo": "C:\\p\\Pieza.par", "hoja": {"nombre": "A3", "ancho": 0.42, "alto": 0.297, "origen": "solicitada"}, "escala": "1:2", "vistas": [{"nombre": "front", "orientacion": "igFrontView", "x": 0.1125, "y": 0.10425}, {"nombre": "top", "orientacion": "igTopView", "x": 0.1125, "y": 0.22275}, {"nombre": "right", "orientacion": "igRightView", "x": 0.3075, "y": 0.10425}, {"nombre": "iso", "orientacion": "igTopFrontRightView", "x": 0.3075, "y": 0.22275}], "abierto": false, "escala_auto": true, "pdf": "C:\\p\\Pieza.pdf", "pdf_bytes": 20480, "marca_de_agua": "sin verificar", "nota": "En Community Edition la salida puede llevar marca de agua; todavía no se validó en vivo."}, "error": null}
```
Crea un Draft nuevo (con `--template` si se pasa), enlaza el modelo (`.par`, `.psm` o `.asm`; si
no existe, exit 5), coloca las vistas, lo guarda en `--out` (por defecto junto al modelo, con
extensión `.dft`) y lo cierra. `--keep-open` lo deja abierto y activo; `--pdf` exporta además
`<nombre>.pdf` junto al `.dft`. No pisa un `.dft` ni un PDF existentes sin `--overwrite` (exit 6).
Nunca cierra ni modifica el modelo fuente: solo se abre (y se cierra sin guardar) si hace falta
medirlo para `--scale auto` y no estaba abierto.

- `--views`: `front`, `top`, `right`, `left`, `bottom`, `back` e `iso` (alias `isometric`),
  hasta 6; por defecto `front,top,right,iso`. Un nombre inválido da exit 2.
- `--scale`: `1:2`, `2:1`, `0.5` o `auto` (por defecto). Con `auto` se elige la escala normalizada
  más grande entre 5:1, 2:1, 1:1, 1:2, 1:5, 1:10, 1:20, 1:50 y 1:100 con la que entran todas las
  vistas en su celda, usando la caja del modelo (`Body.GetRange`, o `GetRangeBox` por ocurrencia
  en un ensamble). Si la API no la da, usa 1:1 y devuelve `"escala_auto": false`.
- `--sheet`: `A5` a `A0` apaisadas. Sin esto se usa la hoja de la plantilla (o A3 si no se puede leer).
- Las vistas se reparten en una grilla de celdas sin superposición: la frontal abajo a la
  izquierda, la superior encima, la derecha al lado y la isométrica en la esquina libre. Se deja un
  margen de 15 mm y 30 mm abajo para el cuadro de rotulación.

### `se sheetmetal flat-dxf`

```powershell
se --json sheetmetal flat-dxf C:\p\Chapa.psm --out C:\salida\chapa.dxf
# {"ok": true, "data": {"entrada": "C:\\p\\Chapa.psm", "documento": "Chapa.psm", "tipo": "sheetmetal", "formato": "dxf", "salida": "C:\\salida\\chapa.dxf", "ok": true, "bytes": 4096, "duracion_s": 0.7, "marca_de_agua": "sin verificar", "nota": "En Community Edition la salida puede llevar marca de agua; todavía no se validó en vivo."}, "error": null}
```
Exporta el desarrollo (flat pattern) de una chapa. Toma un archivo `.psm` (si no está abierto se
abre y se cierra sin guardar), `--doc <selector>` o el documento activo. Un documento que no es
chapa da exit 2. Usa el desarrollo que la chapa **ya tiene** (`Models.SaveAsFlatDXFEx` con
`UseFlatPatternModel=True`, sin elegir cara, arista ni vértice); si no tiene, sale con exit 5 y
explica que hay que crearlo en Solid Edge: generarlo exige elegir geometría. Misma regla de
`--overwrite` y de verificación de tamaño que `export`.

### Supuestos de la API para validar en vivo

| qué | llamada usada |
|---|---|
| STEP, STL, Parasolid, IGES, PDF, DXF | `doc.SaveCopyAs(ruta)`, el formato sale de la extensión; sin opciones de STEP/STL |
| PNG | `doc.Windows.Item(1).View.SaveAsImage(ruta, 1920, 1080)` con el documento activado |
| Draft nuevo | `Documents.Add("SolidEdge.DraftDocument")` o la plantilla |
| Hoja | `ActiveSheet.SheetSetup.SheetSizeOption = PaperSizeConstants.igIso<A>Wide`; medidas leídas de `SheetWidth`/`SheetHeight` |
| Enlace y vistas | `ModelLinks.Add(ruta)`; `ActiveSheet.DrawingViews.AddPartView`, `AddSheetMetalView` o `AddAssemblyView` con `(enlace, orientación, escala, x, y, 0)`; la `x, y` es el centro de la vista |
| Caja del modelo | `Models.Item(1).Body.GetRange([0]*3, [0]*3)` (lee los puntos del retorno); ensamble: `Occurrence.GetRangeBox` |
| Desarrollo | `FlatPatternModels.Count`; `Models.SaveAsFlatDXFEx(ruta, None, None, None, True)` |

## Códigos de salida

Son estables entre versiones; los fija un test (`tests/test_errores.py`).

| exit | significado | `error.code` |
|---|---|---|
| 0 | ok | |
| 1 | error interno o no clasificado; o un lote (`export`) con algún archivo fallido | `interno`, `lote_con_fallos` |
| 2 | uso o argumento inválido (coincide con Typer) | `argumento_invalido` |
| 3 | Solid Edge no disponible o no conectado | `no_conectado` |
| 4 | error COM | `com_error` |
| 5 | recurso no encontrado (documento, variable...) | `doc_no_encontrado` |
| 6 | operación bloqueada (`--readonly`, `se run` sin flag) o no soportada | `solo_lectura`, `no_soportado` |
| 7 | Solid Edge ocupado tras agotar los reintentos | `ocupado` |

## Forma de `--json`

Todo comando con `--json` imprime un único objeto `{ok, data, error}`.

```json
{"ok": true, "data": {"version": "226.00.00.00"}, "error": null}
```

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "no_conectado",
    "message": "No hay una instancia de Solid Edge abierta.",
    "hresult": "0x800401E3",
    "details": {}
  }
}
```

`error.hresult` (hex sin signo) y `error.details` solo aparecen cuando hay algo para informar.
El JSON sale en UTF-8 sin escapar acentos; las fechas van en ISO 8601 y los objetos COM
no se serializan (solo datos planos).

## Pruebas

`uv run pytest` usa un COM falso y no necesita Solid Edge. Las pruebas con la marca `live`
necesitan Solid Edge abierto y no corren por defecto: `uv run pytest -m live`.
`src/se_cli/core/constants.py` se regenera con `uv run python scripts/gen_constants.py`.
