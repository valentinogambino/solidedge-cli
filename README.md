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
