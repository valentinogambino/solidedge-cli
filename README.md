# solidedge-cli

`se` es una CLI para manejar Solid Edge 2026 Community Edition por COM desde la terminal.

Proyecto independiente, no afiliado ni respaldado por Siemens. Solid Edge es marca de Siemens.

## Requisitos

- Windows.
- Solid Edge 2026 instalado (probado con Community Edition 226.00).
- Python 3.11 y [uv](https://docs.astral.sh/uv/).
- Opcional: [just](https://github.com/casey/just) para la receta de tests.

## Instalación

```powershell
git clone https://github.com/valentinogambino/solidedge-cli.git
cd solidedge-cli
uv sync
uv run se --help
```

Para tener `se` en el PATH: `uv tool install .`. Para correr los tests: `just test` (o `uv run pytest`).

Ejemplos (más abajo hay uno por cada comando):

```powershell
se --json connect
se docs list
se --json export --format step
```

## Licencia

MIT, ver `LICENSE`.

Para verificar F0, abrí Solid Edge y corré `uv run python scripts/smoke.py`.
Los archivos de la prueba quedan en `out/smoke/`.

## Opciones globales

Van antes del comando: `se --json docs list`.

| opción | efecto |
|---|---|
| `--json` | Salida `{ok, data, error}` en una línea por stdout, sin colores. Sin `--json` sale una tabla y los errores van a stderr. Con `--json` también los errores de uso de Typer (subcomando inexistente, argumento faltante, opción o valor inválido) salen como sobre `argumento_invalido`, exit 2. |
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
Verificado en vivo: una instancia lanzada por automatización arranca **oculta** (`Visible=False`) y sigue viva
cuando termina `se`; por eso `--launch` la deja visible (`Visible=True`) y devuelve `"lanzada": true`.

```powershell
se --json status
# {"ok": true, "data": {"conectado": true, "version": "226.00.00.00", "nombre": "Solid Edge", "visible": true, "documentos": 2, "activo": "Pieza.par"}, "error": null}
```
Sin instancia **no** es error: sale exit 0 con `"conectado": false`, para sondear desde un agente.

```powershell
se --json quit --yes
# {"ok": true, "data": {"cerrada": true, "descartados": []}, "error": null}
```
Exige `--yes` (exit 2 sin él, sin cerrar nada). Con documentos con cambios sin guardar se niega (exit 6) salvo `--discard`.
Verificado en vivo: `Application.Quit()` vuelve sin error, el proceso `Edge.exe` termina y después
`se status` da `conectado: false`.

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
`--read-only-doc` **no puede abrir en solo lectura**: `Documents.Open` no tiene ese flag (su
segundo argumento es `DocRelationAutoServer`). El documento se abre normal, con `solo_lectura`
real y un `advertencia` si no quedó en solo lectura; solo queda así si el archivo tiene el
atributo de solo lectura de Windows.

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

En **pieza y chapa** la lectura sin densidad usa `Model.GetPhysicalProperties` (`Status` 1 = hay
propiedades guardadas; 2 = no hay, todo en cero). Un cálculo con `--density` recién se puede leer
sin densidad después de guardar el documento. `GetUserPhysicalProperties` solo devuelve valores
cargados a mano y no sirve. En un **ensamble** no existe cálculo con densidad (`--density` da exit
6, `no_soportado`): la masa sale de los materiales de las piezas con
`PhysicalProperties.GetAssemblyPhysicalProperties` (corre `Update()` si está desactualizado, y
entonces `actualizado: true`); una pieza sin material cuenta con densidad 1 kg/m3 y el ensamble no
informa el área (`area: null`). Verificado: cubo de 50 mm a 7850 kg/m3 da volumen 1.25e-4 m3, área
0.015 m2 y masa 0.98125 kg.

### Ensambles y operaciones

```powershell
se --json asm tree [--depth 10]
# {"ok": true, "data": {"documento": "Conj.asm", "profundidad": 10, "arbol": [{"nombre": "Sub.asm:1", "archivo": "C:\p\Sub.asm", "cantidad": 2, "visible": true, "ensamble": true, "indice": 1, "indices": [1, 2], "hijos": [{"nombre": "tornillo.par:1", "archivo": "C:\p\tornillo.par", "cantidad": 3, "visible": true, "ensamble": false, "hijos": []}]}]}, "error": null}
se --json asm tree --flat
# {"ok": true, "data": {"documento": "Conj.asm", "cantidad": 2, "materiales": [{"archivo": "C:\p\Sub.asm", "cantidad": 2, "ensamble": true}, {"archivo": "C:\p\tornillo.par", "cantidad": 6, "ensamble": false}]}, "error": null}
```
Las ocurrencias hermanas del mismo archivo se agrupan en `cantidad`. `--depth` es la cantidad de
niveles a expandir (1 = solo el primer nivel; lo que queda sin expandir lleva `truncado: true`);
un ciclo se corta con `ciclo: true`. `--flat` multiplica las cantidades a través de los
subensambles. En modo humano el árbol sale con `rich.tree`. Solo ensambles: otro tipo da exit 2.
`Occurrence` no tiene miembro de supresión, así que el nodo no informa `suprimido`.
Los nodos de primer nivel llevan `indice`: la posición 1-based de la ocurrencia en el ensamble, que
es el `<occ>` de `asm ground|move|remove` (si el nodo agrupa varias, `indices` las lista todas;
el nombre de cada una, ej. `caja.par:2`, también sirve de `<occ>`).

#### Armar un ensamble: `asm add|ground|move|remove`

```powershell
se --json asm add C:\p\caja.par [--at 10mm,0,5mm] [--rot 0,0,90deg] [--units mm,deg] [--doc Conj.asm]
# {"ok": true, "data": {"indice": 2, "nombre": "caja.par:2", "archivo": "C:\p\caja.par", "visible": true, "ensamble": false, "fija": true, "posicion": [0.01, 0.0, 0.005], "rotacion": [0.0, 0.0, 1.5707963267948966], "unidades": {"longitud": "m", "angulo": "rad"}}, "error": null}
se --json asm ground caja.par:2 [--release]
# {"ok": true, "data": {"indice": 2, "nombre": "caja.par:2", ..., "fija": true, "changed": false}, "error": null}
se --json asm move 2 --by 5mm,0,0          # desplazamiento relativo
se --json asm move 2 --at 10mm,20mm,0      # posición absoluta (los ángulos quedan)
se --json asm move 2 --rot 0,0,90deg       # ángulos absolutos (la posición queda)
se --json asm remove caja.par:2
# {"ok": true, "data": {"indice": 2, "nombre": "caja.par:2", "archivo": "C:\p\caja.par", "removed": true, "restantes": 1}, "error": null}
```
Todos modifican, aceptan `--doc` y siguen las reglas globales: `--readonly` los bloquea (exit 6) y
`--dry-run` informa el plan sin tocar Solid Edge. Solo ensambles (otro tipo, exit 2).

- `<occ>`: índice 1-based de la ocurrencia de primer nivel (el `indice` de `asm tree`) o su nombre,
  sin distinguir mayúsculas. Si no existe, exit 5.
- `add` inserta una pieza, chapa o ensamble (`.par`, `.psm`, `.asm`, `.pwd`). Sin `--at` ni `--rot`
  va al origen. Un archivo que no existe da exit 5; una extensión no insertable, o el propio
  ensamble, exit 2. Admite el mismo archivo varias veces (cada una es una ocurrencia).
- `--at`, `--by` y `--rot` toman tres valores `X,Y,Z`. Longitudes con unidad (`10mm`) y ángulos
  con unidad (`90deg`); **sin unidad, SI**: metros y radianes, como en el resto de la CLI (ej.
  `--rot 0,0,1.5708` son radianes; para grados escribí `deg`). Posición en coordenadas del
  ensamble; los ángulos son los de Euler que Solid Edge devuelve en `GetTransform`.
- `move` necesita al menos una de `--at` (absoluta), `--by` (relativa; no se combina con
  `--at`) o `--rot` (absoluta). Lo que no se pasa se conserva.
- `ground` es idempotente: si ya está fija no escribe y `changed` es `false`. **Solid Edge crea toda
  ocurrencia ya fija** (cada `add` trae su relación ground), así que `ground` solo cambia algo
  después de soltarla con `--release` (que borra esa relación). Mover una ocurrencia fija funciona
  igual por la API.
- `remove` borra la ocurrencia y sus relaciones; el archivo de la pieza no se toca.
- `data` sale de lo que Solid Edge tiene después de la operación (si no coincide con lo pedido,
  exit 4): `posicion` y `rotacion` en metros y radianes, o en lo que pida `--units` (`mm,deg`); `fija`
  es si la ocurrencia tiene su relación ground.

#### Relaciones 3D: `asm relate` y `asm relations list|delete`

```powershell
se --json edges list --doc caja.par         # índice de cada cara: en cada arista, `caras[].indice`
se --json asm ground 2 --release            # las ocurrencias nacen fijas: soltá una antes
se --json asm relate mate --a 1:3 --b 2:1 [--units mm] [--doc Conj.asm]
# {"ok": true, "data": {"indice": 3, "tipo": "mate", "a": {"ocurrencia": 1, "cara": 3, "tipo_de_cara": "plano"}, "b": {"ocurrencia": 2, "cara": 1, "tipo_de_cara": "plano"}, "offset": 0.0, "estado": "resuelta", "ocurrencias": [{"indice": 1, ..., "fija": true, "posicion": [0.0, 0.0, 0.0]}, {"indice": 2, ..., "fija": false, "posicion": [0.05, 0.0, 0.0]}], "unidades": {"longitud": "m"}}, "error": null}
se --json asm relate align --a caja.par:1:3 --b caja.par:2:3 --offset 5mm
se --json asm relate axial --a 3:1 --b cil.par:2:1
se --json asm relations list [--units mm]
# {"ok": true, "data": {"cantidad": 2, "relaciones": [{"indice": 1, "tipo": "ground", "tipo_codigo": 1959028688, "ocurrencias": [{"indice": 1, "nombre": "caja.par:1"}], "offset": null, "estado": "resuelta", ...}, {"indice": 2, "tipo": "mate", ...}], "unidades": {"longitud": "m"}}, "error": null}
se --json asm relations delete 2
# {"ok": true, "data": {"indice": 2, "tipo": "mate", "ocurrencias": [...], "removed": true, "restantes": 1}, "error": null}
```
`relate`, `relations list` y `relations delete` aceptan `--doc` (solo ensambles; otro tipo, exit 2);
`relate` y `delete` modifican, así que `--readonly` los bloquea (exit 6) y `--dry-run` informa el plan.

- `<occ>:<cara>`: la ocurrencia (índice de `asm tree` o nombre, como en `ground|move|remove`) y el
  **índice 1-based de la cara en el cuerpo de su pieza**, el mismo que `se edges list` informa en
  `caras[].indice` con esa pieza abierta (`cantidad_caras` da el total). Se corta en el último `:`,
  así que `caja.par:2:5` es la cara 5 de `caja.par:2`. Formato inválido, o misma ocurrencia en
  `--a` y `--b`, exit 2; ocurrencia o cara inexistente, exit 5.
- `mate`: caras planas enfrentadas (en contacto, normales opuestas). `align`: caras planas
  alineadas (coplanares, misma normal). `axial`: ejes de dos caras cilíndricas coincidentes.
  Una cara de tipo incompatible (curva en `mate`/`align`, no cilíndrica en `axial`) da exit 2 sin
  tocar Solid Edge.
- `--offset` (longitud; sin unidad, metros; admite negativos) solo vale para `mate` y `align`; con
  `axial`, exit 2. El signo es el de Solid Edge: con `mate`, positivo separa las caras; con `align`,
  `+5mm` deja la cara de `--b` a 5 mm de la de `--a` en el sentido de su normal.
- **Las ocurrencias nacen fijas** y Solid Edge no rechaza la relación entre dos fijas: la crea sin
  resolver (`DetailedStatus` entre fijas) y sin mover nada. `relate` lo detecta, borra la relación
  y sale con exit 4 diciendo que hay que soltar una con `se asm ground <occ> --release`; no la
  suelta solo. Toda relación que quede sin resolver o con un offset distinto del pedido se borra
  igual (exit 4, `details.relacion_borrada`).
- `data` de `relate`: `indice` y `tipo` de la relación, `a` y `b` (ocurrencia, cara y tipo de
  cara), `offset`, `estado` y `ocurrencias` con la posición y rotación resultantes leídas de
  Solid Edge (`--units mm,deg` para mostrarlas en otra unidad).
- `relations list` da por relación `indice` (1-based, orden de `Relations3d`), `tipo` (`ground`,
  `mate`, `align`, `axial` u `otro` con `tipo_codigo`), `ocurrencias` (con su `indice` de `asm
  tree`), `offset` (solo planares) y `estado` (`resuelta`, `entre_fijas`, `insatisfecha`, ...). El
  índice cambia al borrar o agregar relaciones, y soltar una ocurrencia borra su relación ground.
  `relations delete` acepta cualquier relación (también una ground); índice inexistente, exit 5.

```powershell
se --json features list
# {"ok": true, "data": {"cantidad": 2, "operaciones": [{"indice": 1, "nombre": "ExtrudedProtrusion_1", "tipo": "ExtrudedProtrusion", "suprimida": false, "estado": "ok"}, {"indice": 2, "nombre": "ExtrudedCutout_1", "tipo": "ExtrudedCutout", "suprimida": true, "estado": "suppressed"}]}, "error": null}
```
`indice` es 1-based. `tipo` sale de `FeatureTypeConstants` (el entero si no tiene nombre). Solo
pieza y chapa: otro tipo da exit 2. Solid Edge marca el documento como modificado (`Dirty`) apenas
se lee `Features.Count`, y `Dirty` no se puede limpiar: después de `features list` un `docs close`
sin flags se niega y pide `--save` o `--discard`.

```powershell
se --json features suppress 2        # por índice (el de `features list`) o por nombre
# {"ok": true, "data": {"indice": 2, "nombre": "ExtrudedCutout_1", "tipo": "ExtrudedCutout", "suprimida": true, "estado": "suppressed", "changed": true}, "error": null}
se --json features unsuppress ExtrudedCutout_1 --doc Pieza.par
```
Suprimen o reactivan una operación del documento (`Feature.Suppress`). Aceptan `--doc` y modifican:
`--readonly` los bloquea (exit 6) y `--dry-run` informa qué harían. El selector numérico es siempre
un índice; un nombre se compara sin distinguir mayúsculas. Un índice fuera de rango o un nombre que
no existe da exit 5; un documento que no es pieza ni chapa, exit 2. Son idempotentes: si la operación
ya está en el estado pedido no se escribe nada y `changed` es `false`. `suprimida` y `estado` son lo
que Solid Edge informa después de escribir (si no coincide con lo pedido, exit 4). La supresión
cambia el modelo: `se mass` ya no cuenta una operación suprimida.

## Modelado básico (F5)

Todos aceptan `--doc <selector>` (por defecto el activo), valores con unidad (`10mm`, `45deg`; sin
unidad es SI: metros y radianes) y modifican: `--readonly` los bloquea (exit 6) y `--dry-run`
informa qué harían sin tocar COM. Escriben con `DisplayAlerts` apagado. Solo funcionan en `part` y
`sheetmetal` en **modo ordenado**; en un documento sincrónico dan exit 2 con la explicación.

**Planos** (verificado en vivo con la plantilla de Part): `RefPlanes.Item(1)` es `top` (plano XY,
normal +Z), `Item(2)` es `right` (plano YZ, normal +X) e `Item(3)` es `front` (plano XZ, normal
-Y). En el perfil, `x` e `y` son (X, Y) en `top`, (Y, Z) en `right` y (X, Z) en `front`. `--plane`
acepta `top`, `front`, `right` o un índice de `RefPlanes` (1, 2, 3...). La dirección `normal` de
una extrusión o corte va hacia la normal del plano (en `front`, hacia -Y).

**Identificador de perfil**: cada `se sketch` crea un `ProfileSet` y devuelve su índice (1-based) en
`perfil`. `--profile 2` (o `ProfileSet_2`) lo elige después; sin `--profile`, `extrude` y `revolve`
usan el **último** perfil del documento. Un perfil sigue disponible después de usarlo y se puede
reutilizar. `se hole` crea su propio perfil, que pasa a ser el último.

### `se sketch rect` y `se sketch circle`

```powershell
se --json sketch rect --plane top --width 50mm --height 30mm [--at 10mm,5mm] [--centered]
# {"ok": true, "data": {"perfil": 1, "plano": "top", "plano_indice": 1, "tipo": "rect", "dimensiones_si": {"ancho": 0.05, "alto": 0.03, "x": 0.0, "y": 0.0, "centrado": false}, "valido": true, "codigo_end": -103}, "error": null}
se --json sketch circle --plane top --diameter 8mm --at 25mm,15mm       # o --radius 4mm
# {"ok": true, "data": {"perfil": 2, "plano": "top", "plano_indice": 1, "tipo": "circulo", "dimensiones_si": {"radio": 0.004, "diametro": 0.008, "x": 0.025, "y": 0.015}, "valido": true, "codigo_end": 0}, "error": null}
```
`--at X,Y` es la esquina inferior izquierda del rectángulo (o su centro con `--centered`) y el
centro del círculo; por defecto el origen. `Profile.End(igProfileClosed)` devuelve **-103** con un
rectángulo de cuatro líneas aunque es válido (con un círculo da 0): se aceptan ambos y se informan
en `codigo_end`; cualquier otro código es exit 4.

### `se sketch profile`

```powershell
se --json sketch profile perfil.json [--doc <selector>]
Get-Content perfil.json | se --json sketch profile -        # `-` lee la entrada estándar
# {"ok": true, "data": {"perfil": 1, "plano": "top", "plano_indice": 1, "tipo": "perfil", "dimensiones_si": {"x_min": -0.01, "y_min": 0.0, "x_max": 0.06, "y_max": 0.02}, "valido": true, "codigo_end": 0, "entidades": {"lineas": 2, "arcos": 2, "circulos": 0}, "restricciones": {"aplicadas": 11, "por_tipo": {"connect": 4, "horizontal": 2, "tangent": 4, "equal": 1}}}, "error": null}
```
Crea un croquis cerrado de líneas, arcos y círculos con restricciones a partir de un perfil
declarativo en JSON, **sin estado entre comandos** (no hay `sketch begin/end` ni atajos
`sketch line|arc`: cada uno dejaría un perfil abierto inutilizable). El `data` es el de `sketch rect`
(`perfil` se pasa a `extrude --profile` y `revolve --profile`) más `entidades` y `restricciones`
(las realmente aplicadas, incluidas las uniones automáticas). Todo el JSON se valida **antes** de
tocar Solid Edge; `--dry-run` hace solo eso y devuelve el plan en SI (entidades ya expandidas y
restricciones).

Esquema v1 (todo campo desconocido es exit 2):

| campo | |
|---|---|
| `version` | obligatorio, `1` |
| `plane` | `top` (por defecto), `front`, `right` o un índice de `RefPlanes`, como `sketch rect` |
| `units` | unidad de longitud (`m`, `mm`, `cm`, `in`, `ft`) de los números sin unidad; obligatoria si hay alguno |
| `tolerance` | número o string con unidad; por defecto 1e-6 m. Es la tolerancia de coincidencia, de radios y de cumplimiento de restricciones |
| `auto_connect` | por defecto `true`: genera un `connect` por cada par de extremos que coinciden |
| `close` | por defecto y solo `true` (los perfiles abiertos quedan fuera de v1) |
| `entities` | lista no vacía de entidades |
| `constraints` | lista opcional de restricciones |

Coordenadas, largos y radios: un número (en `units`) o un string con unidad (`"50mm"`; el string sin
unidad es exit 2). Un punto es `[x, y]` en el plano del perfil (como en `sketch rect`). Entidades,
todas con un `id` único sin puntos:

| `type` | campos | |
|---|---|---|
| `line` | `from`, `to` | |
| `arc` | `center`, `start`, `end`, `dir` | `ccw` (por defecto) o `cw`: el sentido en que se recorre de `start` a `end`. Los radios a `start` y a `end` tienen que coincidir (dentro de `tolerance`) y `start` no puede ser igual a `end` (para una vuelta completa, `circle`) |
| `circle` | `center`, `radius` | es un lazo por sí mismo |
| `polyline` | `points` (al menos 2) | azúcar: se expande a las líneas `p1.1`, `p1.2`... (id de la polilínea, punto, número de segmento desde 1). Para cerrar una polilínea hay que repetir el primer punto al final |

Restricciones. Referencias: `<id>` para una entidad (un segmento de polilínea es `p1.2`; la
polilínea sola no se puede nombrar) y `<id>.<punto>` para un punto, con `start`/`end` en líneas y
arcos, `center` en arcos y círculos (`"a1.start"`, `"p1.2.end"`).

| `type` | campos | se aplica a |
|---|---|---|
| `connect` | `a`, `b` (puntos) | une dos puntos (`AddKeypoint`) |
| `horizontal`, `vertical` | `on` | una línea |
| `parallel`, `perpendicular` | `a`, `b` | dos líneas |
| `equal` | `a`, `b` | dos líneas (largo) o dos arcos/círculos (radio) |
| `concentric` | `a`, `b` | arcos o círculos |
| `tangent` | `a`, `b` | línea con arco o círculo, o dos arcos/círculos entre sí |

Las restricciones **solo fijan intención**: las coordenadas ya tienen que cumplirlas dentro de
`tolerance`. Si no (o si el tipo no corresponde, o `horizontal` va sobre un arco), es exit 2 sin
tocar Solid Edge; el solver de Solid Edge, si no, movería la geometría. Primero se aplican las
uniones y después el resto en el orden del JSON. Fuera de v1 (exit 2): cotas, perfiles abiertos,
`collinear` y `symmetric`.

Con `close: true`, antes de tocar Solid Edge se verifica que líneas y arcos formen lazos
cerrados (cada vértice con exactamente dos extremos; uno solo es un contorno abierto y tres o más,
un contorno ramificado). Los círculos son lazos propios, así que un círculo dentro de un contorno
es un agujero.

Ejemplo completo (ranura de 50 x 20 mm con extremos redondos: el arco derecho `ccw` y el izquierdo
`cw`, todo tangente; extruida 10 mm da 13141.593 mm3 = (50 x 20 + pi x 10^2) x 10):

```json
{"version": 1, "plane": "top", "units": "mm", "tolerance": 0.001, "auto_connect": true, "close": true,
 "entities": [
   {"id": "l1", "type": "line", "from": [0, 0], "to": [50, 0]},
   {"id": "a1", "type": "arc", "center": [50, 10], "start": [50, 0], "end": [50, 20], "dir": "ccw"},
   {"id": "l2", "type": "line", "from": [50, 20], "to": [0, 20]},
   {"id": "a2", "type": "arc", "center": [0, 10], "start": [0, 0], "end": [0, 20], "dir": "cw"}
 ],
 "constraints": [
   {"type": "horizontal", "on": "l1"}, {"type": "horizontal", "on": "l2"},
   {"type": "tangent", "a": "l1", "b": "a1"}, {"type": "tangent", "a": "a1", "b": "l2"},
   {"type": "tangent", "a": "l2", "b": "a2"}, {"type": "tangent", "a": "a2", "b": "l1"},
   {"type": "equal", "a": "a1", "b": "a2"}
 ]}
```

Errores: JSON inválido, campos desconocidos, ids duplicados, tipos o referencias inexistentes, arco
con radios distintos, coordenadas que no cumplen una restricción o contorno no cerrado, todo exit 2
(y Solid Edge intacto); archivo inexistente, exit 5; `--readonly`, exit 6. **Fallo a mitad** (Solid
Edge rechaza una entidad o una relación, o el cierre): se borra el perfil creado
(`ProfileSet.Delete`) y sale exit 4 con la etapa en `error.details`, p. ej.
`{"etapa": "restricciones", "restriccion": 12, "tipo": "horizontal", "perfil_borrado": true}`
(etapas: `perfil`, `entidades`, `restricciones`, `cierre`). Solid Edge rechaza, por ejemplo, la misma
restricción repetida.

Notas de Solid Edge (verificadas en vivo): el perfil se cierra con `Profile.End(igProfileClosed |
igProfileAllowNested)` (8193). Sin `AllowNested` un lazo dentro de otro da -113 y no extruye. Aun
así, para que un perfil con un lazo adentro de otro (una placa con un círculo) extruya hace falta
que sus extremos estén unidos por relaciones: **con `auto_connect: false` y un círculo adentro, el
perfil cierra pero `extrude` no crea nada** (Solid Edge no da error). `codigo_end` es 0 con los
extremos unidos y -103 sin unir.

### `se extrude`

```powershell
se --json extrude 10mm [--profile 1] [--direction normal|reverse|symmetric] [--cut]
# {"ok": true, "data": {"operacion": "extrusion", "nombre": "ExtrudedProtrusion_1", "distancia_si": 0.01, "direccion": "normal", "perfil": 1, "modelo_base": true, "volumen_si": 1.5e-05}, "error": null}
```
La primera operación crea el modelo base (`Models.AddFiniteExtrudedProtrusion`); las siguientes
agregan al modelo (`ExtrudedProtrusions.AddFiniteMulti`). `symmetric` reparte la distancia total a
ambos lados del plano. Con `--cut` corta (`ExtrudedCutouts.AddFiniteMulti`; sin modelo base es
exit 2) y devuelve `operacion: "corte"` y `volumen_quitado_si`. Solid Edge **no da error** si el corte
no toca material (crea una operación vacía): el comando compara `Body.Volume` antes y después, y si
no cambió deshace la operación (`Feature.Delete`) y sale con exit 2 sugiriendo `--direction reverse`.

### `se revolve`

```powershell
se --json revolve 180deg --axis y [--profile 1]
# {"ok": true, "data": {"operacion": "revolucion", "nombre": "RevolvedProtrusion_1", "angulo_si": 3.14159, "eje": "y", "perfil": 1, "modelo_base": true, "volumen_si": 5.0e-05}, "error": null}
```
El eje se define con `--axis x|y`: la recta `y=0` (`x`) o `x=0` (`y`) del plano del perfil. El comando
agrega al perfil una línea de construcción por el origen (`ToggleConstruction`) y la marca como eje
(`Profile.SetAxisOfRevolution`, que se puede llamar con el perfil ya cerrado); el perfil tiene que
quedar de un solo lado del eje. El ángulo por defecto es `360deg` (de 0 a 360deg). Primera operación:
`Models.AddFiniteRevolvedProtrusion`; después, `RevolvedProtrusions.AddFiniteMulti`.

### `se hole`

```powershell
se --json hole --at 25mm,15mm --diameter 8mm (--depth 5mm | --through) [--plane top] [--direction normal]
# {"ok": true, "data": {"operacion": "agujero", "nombre": "ExtrudedCutout_1", "diametro_si": 0.008, "profundidad_si": null, "pasante": true, "plano": "top", "plano_indice": 1, "x_si": 0.025, "y_si": 0.015, "direccion": "normal", "perfil": 3, "volumen_si": 1.4497e-05, "volumen_quitado_si": 5.0265e-07}, "error": null}
```
Agujero simple: un círculo en el plano y un corte (`ExtrudedCutouts.AddFiniteMulti` o
`AddThroughAllMulti`); no usa la colección `Holes`. Sin modelo base es exit 2. Igual que el corte de
`extrude`, si no quita material se deshace y da exit 2. Un agujero pasante no admite
`--direction symmetric` (Solid Edge no corta nada): exit 2.

### Recorrido en vivo (2026-11-23, Solid Edge 226.00.01.04)

```powershell
se connect; se docs new part
se sketch rect --plane top --width 50mm --height 30mm
se extrude 10mm
se sketch circle --plane top --diameter 8mm --at 25mm,15mm
se hole --at 25mm,15mm --diameter 8mm --through --plane top
se vars list --units mm                                  # ExtrudedProtrusion_1_FiniteDepth = 10 mm
se vars set ExtrudedProtrusion_1_FiniteDepth 20mm
se mass --density 7850 --units mm,g
se docs save-as out\live\f5\caja.par; se export --format step
```
Caja 50 x 30 x 20 mm menos el agujero pasante de 8 mm: volumen esperado 28994.690 mm3 y masa
0.227608 kg (28994.690e-9 m3 x 7850 kg/m3); obtenidos 28994.690 mm3 y 227.608 g (idénticos).
Con 10 mm de alto el volumen era 14497.345 mm3 (esperado 15000 - 502.655). Pieza de revolución:
rectángulo de 20 x 40 mm en `front` desde x = 10 mm, `revolve --axis y` = tubo de radios 10 y 30 mm:
volumen esperado pi (30^2 - 10^2) 40 = 100530.965 mm3 y 789.168 g; obtenidos los mismos.
Una segunda revolución de 180deg sumó 4712.389 mm3 (esperado pi (20^2 - 10^2) 10 / 2).

## Aristas, redondeos y chaflanes

Para redondear o achaflanar hay que elegir aristas por número. `se edges list` las numera y
`se round` / `se chamfer` las usan. Los tres aceptan `--doc` y `--units`, y funcionan en `part` y
`sheetmetal` en modo ordenado con un modelo base (`se extrude` primero); en otro tipo de documento,
o sin modelo, dan exit 2. `round` y `chamfer` modifican: `--readonly` los bloquea (exit 6),
`--dry-run` informa el plan sin tocar COM y escriben con `DisplayAlerts` apagado.

**Los índices de arista cambian después de cada operación que modifica el cuerpo** (un redondeo o un
chaflán agrega aristas y las renumera): hay que volver a correr `se edges list` antes de la
siguiente. Dentro de una misma lectura el índice (1-based) es estable.

### `se edges list`

```powershell
se --json edges list [--units mm] [--doc Pieza.par]
# {"ok": true, "data": {"cantidad": 12, "cantidad_caras": 6, "aristas": [{"indice": 1, "tipo": "linea", "longitud": 20.0, "inicio": [0.0, 0.0, 0.0], "fin": [0.0, 0.0, 20.0], "caras": [{"indice": 1, "tipo": "plano"}, {"indice": 3, "tipo": "plano"}]}, ...], "unidades": {"longitud": "mm"}}, "error": null}
```
`tipo` es `linea`, `arco`, `circulo` u `otra` (elipse, spline...). `longitud`, `inicio` y `fin` van en
las unidades de `--units` (por defecto metros). `caras` son los índices (1-based) de las caras del
cuerpo que toca la arista, con su tipo (`plano`, `cilindro`, `cono`, `esfera`, `toro`, `bspline`,
`otra`); sirven para saber qué aristas comparten una cara. Lo que la API no entrega queda en `null`.

### `se round`

```powershell
se --json round <radio> --edges all|1,3,5|1-4 [--units mm] [--doc Pieza.par]
# {"ok": true, "data": {"operacion": "redondeo", "nombre": "Round_1", "indice": 2, "cantidad_aristas": 4, "aristas": [2, 4, 6, 9], "estado": "ok", "volumen_si": 2.9931e-05, "volumen_quitado_si": 6.867e-08, "radio": 2.0, "unidades": {"longitud": "mm"}}, "error": null}
```
Redondeo de radio constante: una sola operación (`Model.Rounds.Add`) con todas las aristas
pedidas. `--edges` es obligatorio (sin él, exit 2) y acepta `all`, una lista (`1,3,5`), rangos
(`1-4`) o mezclas (`1-3,7`). `radio` es el que leyó Solid Edge de la operación (`GetConstantRadii`),
en las unidades de `--units`; `indice` es el de `se features list`. Radio menor o igual que 0, o con
una unidad que no es de longitud: exit 2. Índice de arista fuera de rango: exit 5.

### `se chamfer`

```powershell
se --json chamfer <distancia> --edges all|1,3,5|1-4 [--angle 30deg] [--units mm,deg] [--doc Pieza.par]
# {"ok": true, "data": {"operacion": "chaflan", "nombre": "Chamfer_2", "indice": 4, "cantidad_aristas": 4, "aristas": [4, 8, 12, 16], "estado": "ok", "volumen_si": 2.9809e-05, "volumen_quitado_si": 4.45e-08, "distancia": 1.0, "angulo": 30.0, "unidades": {"longitud": "mm", "angulo": "deg"}}, "error": null}
```
Sin `--angle` es un chaflán de distancias iguales (`Chamfers.AddEqualSetback`) y `angulo` sale
`null`. Con `--angle` (entre 0 y 90 grados; sin unidad, radianes) es distancia + ángulo
(`Chamfers.AddSetbackAngle`), que necesita una cara de referencia: se usa la de menor índice entre
las caras que comparten **todas** las aristas elegidas; si no hay ninguna (por ejemplo `all` en una
caja) es exit 2 sin tocar el modelo. Distancia menor o igual que 0: exit 2.

**Qué cara toma de referencia** (verificado en vivo, 2026-11-24): la distancia corre **sobre la cara de
referencia** y el otro cateto, sobre la cara vecina, mide distancia x tan(ángulo). En una caja de
50 x 30 x 20 mm, `chamfer 4mm --angle 30deg --edges 7` (arista entre las caras 2, el frente y=0, y 5,
la tapa): la referencia es la cara 2; el material quitado (230.94 mm3) tiene su centroide en y = 0.770 mm
y z = 18.667 mm, o sea catetos de 4 mm sobre la cara 2 (hacia abajo) y 2.309 mm sobre la tapa.

### Si Solid Edge no puede hacer la operación

Un radio o una distancia demasiado grandes no dan error en la API: Solid Edge crea la operación con
estado `failed`, y mientras exista las operaciones siguientes también fallan. `round` y `chamfer`
leen el estado después de crearla; si falló la borran (`Feature.Delete`) y devuelven exit 4
(`com_error`) con el modelo como estaba. `error.details` dice `operacion_fallida`, `borrada`
(`false` si el borrado también falló: ahí hay que borrarla a mano), `aristas` y `estado`.

```powershell
se --json round 500mm --edges all
# {"ok": false, "data": null, "error": {"code": "com_error", "message": "Solid Edge no pudo crear el redondeo con esas aristas (...): la operación quedó fallida y se borró, así que el modelo quedó como estaba.", "details": {"operacion_fallida": "Round_4", "borrada": true, "aristas": [1, 2, 3, ...], "estado": "failed"}}}
```

### Recorrido en vivo (2026-11-23, Solid Edge 226.00.01.04)

Caja de 50 x 30 x 20 mm: `edges list` da 12 aristas rectas (4 de 20, 4 de 30 y 4 de 50 mm) y 6
caras planas. `round 2mm` en las 4 verticales quitó 68.673 mm3 (esperado
4 (1 - pi/4) 2^2 20 = 68.673); después hay 24 aristas, con arcos. `chamfer 1mm` en las 4 rectas de la
base y `chamfer 1mm --angle 30deg` en las 4 rectas de la tapa (releyendo los índices) bajaron cada
vez el volumen de `se mass`. Un redondeo de 500 mm y un chaflán de 500 mm dieron exit 4 y dejaron
`features list` y el volumen sin cambios. Prueba: `tests/test_vivo_redondeos.py`.

## Escape a COM y scripts

### `se com get|set|invoke`

```powershell
se --json com get ActiveDocument.Name
# {"ok": true, "data": {"ruta": "ActiveDocument.Name", "valor": "Part1"}, "error": null}
se --json com get ActiveDocument.Models.Item(1).ExtrudedProtrusions --list
# {"ok": true, "data": {"ruta": "ActiveDocument.Models.Item(1).ExtrudedProtrusions", "valor": {"tipo": "coleccion", "cantidad": 1, "items": [{"indice": 1, "tipo": "objeto_com", "repr": "<COMObject Item>", "nombre": "ExtrudedProtrusion_1"}], "truncado": false}}, "error": null}
se --json com set DisplayAlerts false
# {"ok": true, "data": {"ruta": "DisplayAlerts", "valor": false, "valor_actual": false}, "error": null}
se --json com invoke Documents.Item 1
# {"ok": true, "data": {"ruta": "Documents.Item", "argumentos": [1], "resultado": {"tipo": "objeto_com", "repr": "<COMObject Item>", "nombre": "Part1"}}, "error": null}
```
La ruta parte de la `Application`. **Sintaxis** (parser propio y estricto, sin `eval`): segmentos
separados por punto; cada uno es un identificador (`[A-Za-z][A-Za-z0-9_]*`) con una llamada opcional
de argumentos literales entre paréntesis: enteros (`1`, `-2`), decimales (`0.5`), textos entre comillas
simples o dobles (`"Nombre"`, con una barra invertida delante de la comilla o de otra barra como únicos escapes), `true`, `false` y `null`.
Cualquier otra cosa (operadores, corchetes, nombres sueltos, un `_` inicial) es exit 2. Los
argumentos sueltos de `invoke` y el valor de `set` se parsean igual; en PowerShell un texto lleva
las comillas dentro de otras: `'"Nombre"'`. Con unidades no: `set` y `invoke` reciben literales
(en SI), no `10mm`.

- `get` es de lectura (funciona con `--readonly`) y solo admite llamadas a `Item(...)`; llamar a
  cualquier otro método es `invoke` (exit 2). Un objeto COM sale como `{tipo: "objeto_com", repr,
  nombre?}` (`nombre` si tiene `Name`); una colección **no se enumera sola**: con `--list` (y
  `--limit N`, 50 por defecto) devuelve `{tipo: "coleccion", cantidad, items, truncado}`.
- `set` e `invoke` modifican: `--readonly` los bloquea (exit 6) y `--dry-run` muestra la ruta
  resuelta (`segmentos`) sin ejecutar. En `invoke` los argumentos van sueltos o entre paréntesis en
  la última parte de la ruta, no los dos.
- Un segmento `Quit` se rechaza en los tres subcomandos con exit 6 (usá `se quit --yes`). Un miembro que
  no existe o seguir la ruta sobre un valor es exit 2; un error de la API es exit 4.

### `se run <script.py> [--allow-scripts] [-- args...]`

```powershell
se --json run C:\scripts\leer.py --allow-scripts -- uno dos
# {"ok": true, "data": {"script": "C:\\scripts\\leer.py", "resultado": {"version": "226.00.01.04", "documentos": 0, "args": ["uno", "dos"]}}, "error": null}
```
**Advertencia: el script corre con tus permisos y puede hacer cualquier cosa** (borrar archivos,
cerrar Solid Edge, llamar a la red). Por eso sin `--allow-scripts` `se run` **siempre** falla con
exit 6 y no lee ni ejecuta el archivo. Con el flag: `--readonly` lo bloquea (exit 6), `--dry-run`
informa qué script correría sin ejecutarlo, un archivo inexistente es exit 5, y un script sin `main`
es exit 2. El script define `main(app, args)` (`app` es la `Application` de late binding y `args` la
lista de textos después de `--`); corre dentro del hilo STA de `se` y lo que devuelve (datos planos)
va en `data.resultado`. Si lanza una excepción (o no compila) sale exit 1 con el traceback resumido en
`error.details.traceback`.

## Exportar y Draft

Los tres comandos escriben archivos (`export` además abre y cierra documentos en un lote), así que
cuentan como que modifican: `--readonly` los bloquea (exit 6) y `--dry-run` informa qué harían
sin tocar Solid Edge ni el disco. Corren con `DisplayAlerts` apagado (se restaura siempre).

**Estado de la validación:** F4 se validó en vivo el 2026-11-23 contra Solid Edge 2026 Community
Edition 226.00.01.04 (ver la tabla de supuestos al final). Cada llamada a Solid Edge está aislada
en una función pequeña de `src/se_cli/core/`.

**Marca de agua (verificada mirando los archivos):** el **PDF** lleva la leyenda "Solid Edge
Community Edition" en gris claro, abajo a la izquierda de cada hoja, dibujada con trazos (no es
texto: buscar la cadena en el PDF no la encuentra). El **DXF** (de un Draft y del desarrollo de una
chapa) no la trae, ni como texto ni como geometría; el PNG tampoco. Los resultados de `pdf` y `dxf`
traen `"marca_de_agua": "presente"` o `"ausente"` y una `nota`.

### Formatos y tipos de documento

| `--format` | alias | extensión de salida | documentos que admite |
|---|---|---|---|
| `step` | `stp` | `.stp` (también acepta `.step` en `--out`) | `part`, `sheetmetal`, `assembly` |
| `stl` | | `.stl` | `part`, `sheetmetal`, `assembly` |
| `x_t` | `parasolid` | `.x_t` | `part`, `sheetmetal`, `assembly` |
| `igs` | `iges` | `.igs` (también `.iges`) | `part`, `sheetmetal`, `assembly` |
| `pdf` | | `.pdf` | `draft` |
| `dxf` | | `.dxf` | `draft` |
| `png` | | `.png` | `part`, `sheetmetal`, `assembly`, `draft` (la ventana encuadrada con `Fit`, 1920x1080; un Draft puede salir con el rotulo recortado por la proporcion 16:9) |

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
# {"ok": true, "data": {"draft": "C:\\p\\Pieza.dft", "modelo": "C:\\p\\Pieza.par", "hoja": {"nombre": "A3", "ancho": 0.42, "alto": 0.297, "origen": "solicitada", "fondo": "A3-Sheet"}, "escala": "1:2", "vistas": [{"nombre": "front", "orientacion": "igFrontView", "x": 0.1125, "y": 0.10425}, {"nombre": "top", "orientacion": "igTopView", "x": 0.1125, "y": 0.22275}, {"nombre": "right", "orientacion": "igRightView", "x": 0.3075, "y": 0.10425}, {"nombre": "iso", "orientacion": "igTopFrontRightView", "x": 0.3075, "y": 0.22275}], "abierto": false, "escala_auto": true, "pdf": "C:\\p\\Pieza.pdf", "pdf_bytes": 20480, "marca_de_agua": "presente", "nota": "Community Edition agrega la leyenda 'Solid Edge Community Edition' en gris claro, abajo a la izquierda de cada hoja. Va dibujada con trazos, no como texto."}, "error": null}
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
- `--sheet`: `A5` a `A0` apaisadas. Sin esto se usa la hoja de la plantilla (A2 en la ISO Metric,
  o A3 si no se puede leer). Además del tamaño se reemplaza el fondo de la hoja (marco y cuadro de
  rotulación) por el `A<n>-Sheet` de la plantilla (`hoja.fondo`); la ISO Metric solo trae A4, A3,
  A2 y A1, así que en A5 y A0 `fondo` es `null` y el marco sigue siendo el de A2.
- Las vistas se reparten en una grilla de celdas sin superposición: la frontal abajo a la
  izquierda, la superior encima, la derecha al lado y la isométrica en la esquina libre. Se deja un
  margen de 15 mm y 30 mm abajo para el cuadro de rotulación.

### `se draft parts-list` y `se draft dim`

```powershell
se --json draft parts-list --view 1 --balloons
# {"ok": true, "data": {"vista": 1, "modelo": "C:\p\Conj.asm", "filas": 1, "globos": true, "globos_agregados": 1}, "error": null}
se --json draft dim --view 1 --auto
# {"ok": true, "data": {"vista": 1, "cotas_antes": 0, "cotas_despues": 1, "cotas_agregadas": 1}, "error": null}
```
Trabajan sobre el Draft activo o `--doc <selector>`; `--view N` es la vista de la hoja activa
(1-based, por defecto 1, en el orden en que se agregaron). Un documento que no es Draft o `--view`
menor que 1 da exit 2; una vista que no existe, exit 5. Los dos modifican el Draft (no lo guardan)
y respetan `--readonly` y `--dry-run`.

- `parts-list [--view N] [--balloons] [--doc]`: inserta la lista de piezas de la vista, que tiene que
  ser de un `.asm` (con una vista de pieza Solid Edge no se queja y arma una lista de una fila, así
  que se rechaza antes con exit 2). `filas` es `PartsList.Rows.Count` (las ocurrencias repetidas
  se agrupan: dos cajas iguales dan una fila) y `globos_agregados` la diferencia de
  `Sheet.Balloons.Count`; ambos son `null` si la API no los da. Un rechazo de Solid Edge sale con
  exit 4.
- `dim --view N --auto [--doc]`: recupera las cotas del modelo en la vista. `--auto` es obligatorio
  y el único modo (sin él, exit 2). Las cotas se cuentan en toda la hoja (`Sheet.Dimensions`), así
  que `cotas_agregadas` es la diferencia; repetirlo da 0. Solo recupera las cotas del modelo que
  se ven en esa vista: en una caja extruida, la frontal da la altura de la extrusión y la
  superior no suma las del croquis.

### `se sheetmetal flat-dxf`

```powershell
se --json sheetmetal flat-dxf C:\p\Chapa.psm --out C:\salida\chapa.dxf
# {"ok": true, "data": {"entrada": "C:\\p\\Chapa.psm", "documento": "Chapa.psm", "tipo": "sheetmetal", "formato": "dxf", "salida": "C:\\salida\\chapa.dxf", "ok": true, "bytes": 4096, "duracion_s": 0.7, "marca_de_agua": "ausente", "nota": "El DXF no trae la leyenda de Community Edition."}, "error": null}
```
Exporta el desarrollo (flat pattern) de una chapa. Toma un archivo `.psm` (si no está abierto se
abre y se cierra sin guardar), `--doc <selector>` o el documento activo. Un documento que no es
chapa da exit 2. Usa el desarrollo que la chapa **ya tiene** (`Models.SaveAsFlatDXFEx` con
`UseFlatPatternModel=True`, sin elegir cara, arista ni vértice); si no tiene, sale con exit 5 y
sugiere `--create`. Misma regla de `--overwrite` y de verificación de tamaño que `export`.

#### `--create`

```powershell
se --json sheetmetal flat-dxf --create --out C:\salida\chapa.dxf
# {"ok": true, "data": {"entrada": "C:\\p\\Chapa.psm", "documento": "Chapa.psm", "tipo": "sheetmetal", "formato": "dxf", "salida": "C:\\salida\\chapa.dxf", "ok": true, "bytes": 34405, "duracion_s": 3.8, "marca_de_agua": "ausente", "nota": "El DXF no trae la leyenda de Community Edition.", "desarrollo_creado": true, "documento_guardado": true, "cara": {"indice": 5, "area_si": 0.0048, "criterio": "cara plana de mayor area"}, "entidades_dxf": 5}, "error": null}
```
Si la chapa no tiene desarrollo, lo crea por API (`FlatPatternModels.Add(modelo)` y
`FlatPatterns.Add(arista, cara, vértice)`), **guarda la chapa** (con cualquier cambio pendiente), la
cierra, la reabre y recién ahí exporta (en una misma sesión el DXF puede salir sin entidades).

- Cara: la **cara plana de mayor área** del primer modelo (`Face.Geometry.Type == igPlane`; en un
  empate, la de menor índice). La arista es la primera de esa cara y el vértice su vértice inicial.
- Precondiciones (si no se cumplen, no se toca nada): la chapa tiene que estar guardada en disco
  (si no, exit 2) y no ser de solo lectura (si no, exit 6); el DXF de destino no puede existir sin
  `--overwrite` (exit 6).
- Si la chapa ya tenía desarrollo no hace nada extra: `desarrollo_creado: false`,
  `documento_guardado: false`, `cara: null`.
- Verifica que el DXF tenga entidades (`entidades_dxf`); si sale vacío es exit 4 y no deja el archivo
  (con `--overwrite` se conserva el anterior).
- Después de reabrir, la chapa queda abierta y activa si lo estaba (o se reactiva el documento que
  estaba activo); si el comando la abrió por ruta, se cierra al terminar.
- `--dry-run` informa la acción (`"create": true`) sin tocar nada; `--readonly` da exit 6.

Verificado en vivo (2026-11-23): una chapa sincrónica de 100 x 50 x 1 mm con una brida de 30 mm
(radio interno 1 mm) da un DXF de 100 x 79.09 mm con 5 entidades; área x espesor coincide con el
volumen de la chapa (7.9356e-6 m3) dentro del 1 %.

### Supuestos de la API (verificados en vivo)

Validados el 2026-11-23 (croquis con arcos y relaciones 2D, el 2026-11-24) contra Solid Edge 2026 Community Edition 226.00.01.04.

| qué | llamada | resultado |
|---|---|---|
| conexión | `GetActiveObject("SolidEdge.Application")` en un hilo STA | verificado |
| `Documents.Add` / `FullName` de un documento nuevo | `Add("SolidEdge.<Tipo>Document")` | verificado; `FullName` viene sin carpeta (`ruta: null`) |
| `Documents.Open(ruta, flag)` solo lectura | segundo argumento = `igReadOnly` | **corregido**: ese argumento es `DocRelationAutoServer`, no hay flag; solo el atributo de Windows da solo lectura |
| `Dirty = False` antes de `Close` | para evitar el diálogo | no soportado (E_FAIL, solo lectura); alcanza `DisplayAlerts=False` + `Close(False)` |
| `Variables.Query` / `Add` / `Value` / `Formula` | `Variables.Query("*")`, `Add(nombre, valor, unidad)` | verificado, incluido `--formula` y `--force` |
| `doc.Properties` y `Custom` | conjuntos `SummaryInformation`, `Custom`, ... | verificado; hay entradas sin nombre (se omiten) y las fechas vienen en hora local sin zona |
| `GetUserPhysicalProperties` | masa sin densidad | **corregido**: solo devuelve valores cargados a mano; se usa `Model.GetPhysicalProperties` |
| `ComputePhysicalPropertiesWithSpecifiedDensity` | pieza y chapa, kwargs con buffers | verificado (cubo 50 mm, 7850 kg/m3: 0.98125 kg) |
| masa de un ensamble | `doc.ComputePhysicalPropertiesWithSpecifiedDensity` | **corregido**: no existe; se usa `PhysicalProperties.Update()` + `GetAssemblyPhysicalProperties()` (sin densidad ni área) |
| `Occurrence`, `GetRangeBox`, `Features` | `asm tree`, `features list` | verificado; leer `Features.Count` ensucia el documento |
| `Feature.Suppress = True/False` | `features suppress`, `features unsuppress` | verificado en pieza ordenada con extrusión y corte; el `Status` pasa a `suppressed` y vuelve a `ok`, y la masa deja de contar la operación |
| `Occurrences.AddByFilename(ruta)` / `AddWithTransform(ruta, x, y, z, rx, ry, rz)` | `asm add` | verificado en ensamble nuevo guardado con una caja extruida; posición en metros, ángulos de Euler en radianes; el MCP usa además `AddWithMatrix`, que no hace falta |
| `Occurrence.GetTransform()` / `PutTransform(x, y, z, rx, ry, rz)` | `asm add`, `asm move` | verificado: la terna que devuelve `GetTransform` es la que acepta `PutTransform` (ida y vuelta exacta, también con rotaciones en X, Y y Z a la vez) |
| `Occurrence.Move(dx, dy, dz)` | `asm move --by` | verificado: suma a la posición sin tocar los ángulos |
| `Relations3d`, `AddGround(occ)`, `Relation.Delete()` | `asm ground`, `asm ground --release` | verificado; **corregido**: la relación ground es de tipo `igGroundRelation3d` (1959028688), no `Type = 0` como dice el MCP; toda ocurrencia nace fija (una relación por ocurrencia, `Relation.Occurrence` apunta a ella); `AddGround` sobre una ya fija no duplica pero reordena las relaciones, por eso se mira antes; mover (`Move`, `PutTransform`) una ocurrencia fija funciona |
| `Occurrence.Delete()` | `asm remove` | verificado: baja `Occurrences.Count`, se llevan las relaciones, el archivo queda |
| `AssemblyDocument.CreateReference(occ, cara)` | `asm relate` | verificado: la cara sale de `OccurrenceDocument.Models.Item(1).Body.Faces(igQueryAll)` (mismo orden que `edges list`); `Relations3d.Add*` no acepta caras sueltas, solo estas referencias |
| `Relations3d.AddPlanar(ref1, ref2, normalsAligned, punto1, punto2)` | `asm relate mate\|align` | verificado en cajas de 50x30x20 mm: **los dos puntos son obligatorios** (sin ellos, "Invalid number of parameters"); sirve `Face.Geometry.GetRootPoint([0,0,0])` (también el origen, no hace falta que caiga en la cara); `normalsAligned=True` es **mate** (caras en contacto) y `False` es **align**; la relación creada lee `NormalsAligned` al revés de lo pasado (mate lee False) |
| `Relations3d.AddAxial(ref1, ref2, normalsAligned)` | `asm relate axial` | verificado con dos cilindros de 20 mm: quedan coaxiales con `True` o `False` (ejes paralelos); se usa `True`. El MCP dice que acepta ocurrencias: da E_FAIL, hacen falta referencias de cara |
| `PlanarRelation3d.Offset` (escritura) | `asm relate --offset` | verificado: se escribe tras crear la relación y mueve la ocurrencia suelta (mate +5 mm: x=55 mm; align +5 mm: x=5 mm); el MCP dice que `AddPlanar` no admite offset, y es cierto, se pone después |
| relación entre dos ocurrencias fijas | `asm relate` | verificado: `AddPlanar` NO falla, devuelve una relación con `Status` solved y `DetailedStatus` 4 (`BetweenFixed`) sin mover nada; la CLI la borra y da exit 4 con la pista de `ground --release` |
| `Relation.Type` (planar -2058948880, axial 1472929712, ground 1959028688), `Occurrence1`/`Occurrence2`, `DetailedStatus`, `Delete()` | `asm relations list\|delete` | verificado; la ground trae `Occurrence` (las otras `Occurrence1/2`); `Offset` solo existe en la planar; el MCP documenta mal los tipos ("Type = 2 Planar") |
| STEP, STL, Parasolid, IGES, PDF, DXF | `doc.SaveCopyAs(ruta)`, el formato sale de la extensión | verificado en pieza, chapa, ensamble y Draft; STEP con cabecera ISO-10303-21, STL binario con 12 triángulos por cubo, `.x_t` con cabecera Parasolid, IGES con sección de inicio |
| PNG | `View.SaveAsImage(ruta, 1920, 1080)` | verificado en pieza, chapa y ensamble (con `View.Fit()` antes); **corregido** en Draft: su `SheetWindow` no tiene `View`, `Fit` y `SaveAsImage` son de la ventana |
| Draft nuevo | `Documents.Add("SolidEdge.DraftDocument")` | verificado (hoja A2 por defecto) |
| Hoja | `ActiveSheet.SheetSetup.SheetSizeOption = igIso<A>Wide` | verificado; **corregido**: además hay que reemplazar el fondo (`ActiveSheet.Background = Sections.BackgroundSection.Sheets.Item("A3-Sheet")`) o el marco y el rotulo salen recortados |
| Enlace y vistas | `ModelLinks.Add(ruta)`; `DrawingViews.AddPartView`, `AddSheetMetalView`, `AddAssemblyView` con `(enlace, orientación, escala, x, y, 0)` | verificado: los tres existen y `x, y` es el centro de la vista; las vistas quedan dentro de la hoja y sin superponerse |
| Caja del modelo | `Models.Item(1).Body.GetRange([0]*3, [0]*3)`; ensamble `Occurrence.GetRangeBox` | verificado (devuelve mínimo y máximo); la escala `auto` es razonable |
| Lista de piezas y globos | `Draft.PartsLists.Add(vista, "", autoGlobos, 1)`; `PartsList.Rows.Count`, `Sheet.Balloons.Count` | verificado en la vista de un ensamble con dos ocurrencias iguales: 1 fila y 1 globo con `autoGlobos=1`, ninguno con 0; **diferencia con el MCP**: `PartsLists.Add` también acepta una vista de pieza (lista de una fila), por eso se valida `View.ModelLink.FileName` antes |
| Cotas automáticas | `DrawingView.RetrieveDimensions()` (sin argumentos); `Sheet.Dimensions.Count` | verificado: la vista frontal de una caja suma 1 cota, repetirlo suma 0; `AddConnectedAnnotationsToView` no se probó |
| Desarrollo | `FlatPatternModels.Count`; `Models.SaveAsFlatDXFEx(ruta, None, None, None, True)` | verificado con un desarrollo guardado en el archivo; sin desarrollo da exit 5 (ver arriba) |
| `Application.Quit` | `se quit --yes` | verificado: vuelve sin error, `Edge.exe` termina y `status` da `conectado: false` |
| `connect --launch` | `Dispatch("SolidEdge.Application")` | verificado: arranca **oculta** (`Visible=False`) y sigue viva al terminar `se`; se le pone `Visible=True` |
| Planos de la plantilla Part | `RefPlanes.Item(1..3)` | verificado: 1 = top (XY, +Z), 2 = right (YZ, +X), 3 = front (XZ, -Y) |
| Perfil | `ProfileSets.Add()`, `Profiles.Add(plano)`, `Lines2d.AddBy2Points`, `Circles2d.AddByCenterRadius`, `End(igProfileClosed)` | verificado: `End` da -103 con un rectángulo y 0 con un círculo; el perfil sigue en `ProfileSets` y es reutilizable |
| Arco de un perfil | `Arcs2d.AddByCenterStartEnd(cx, cy, sx, sy, ex, ey)` | verificado midiendo `StartAngle`/`SweepAngle`: **siempre antihorario de start a end** (centro (0,0), start (10,0), end (0,10) mm: barrido 90°; start (0,20), end (20,0): 270°). Un arco `cw` se crea con start y end intercambiados; el volumen de una ranura con un arco `ccw` y otro `cw` coincide con el analítico |
| Keypoints para `Relations2d.AddKeypoint(obj1, kp1, obj2, kp2)` | línea: 0 = inicio, 1 = fin, 2 = medio; arco: 0 = centro, 1 = inicio, 2 = fin, 3 = medio; círculo: 0 = centro | verificado moviendo la geometría que el solver desplaza al unir dos puntos que no coinciden; **corregido**: el typelib (centro 0, inicio 1, fin 2) acierta y el MCP (arco 0 = inicio, 1 = fin, 2 = medio) no. Un keypoint 3 en una línea da E_FAIL. En un arco `cw` el `start` del JSON es el keypoint 2 (fin real) y el `end` el 1 |
| Relaciones 2D | `Relations2d.AddHorizontal(l)`, `AddVertical(l)`, `AddParallel(a, b)`, `AddPerpendicular(a, b)`, `AddEqual(a, b)`, `AddConcentric(a, b)`, `AddTangent(a, b)` | verificado: reciben solo los objetos (sin puntos ni keypoints) y el orden de `a`/`b` no importa (tangentes línea-arco y arco-línea en una ranura); `AddEqual` sirve entre líneas, arcos y círculos (radio). **Si la geometría no cumple la relación el solver la mueve en silencio** (un `AddKeypoint` entre puntos lejanos arrastra la línea; un `AddConcentric` mueve el arco): por eso `sketch profile` exige antes que las coordenadas ya la cumplan. `AddHorizontal` sobre un arco da E_FAIL, y repetir una relación ya creada también (`0x80020009`) |
| Borrar un perfil | `ProfileSet.Delete()` | verificado: borra el perfil **antes de `End`**, **después de un `End` bueno** y **después de un `End` que devolvió -103** (perfil abierto): baja `ProfileSets.Count`; sirve de limpieza ante un fallo a mitad de `sketch profile` (verificado también con una relación que Solid Edge rechazó) |
| Cierre con lazos anidados | `Profile.End(igProfileClosed \| 8192)` | verificado: `igProfileAllowNested` (8192) no está en el typelib; sin él un círculo dentro de un contorno da -113 y `AddFiniteExtrudedProtrusion` no crea nada (sin error). Con 8193 y los extremos unidos por `AddKeypoint` da 0 y extruye con el agujero (volumen exacto); con los extremos sin unir da -103 y tampoco extruye. `End` también devuelve -103 con un contorno abierto, así que el cierre se valida en la CLI |
| Extrusión | `Models.AddFiniteExtrudedProtrusion` (primera), `ExtrudedProtrusions.AddFiniteMulti` (siguientes) | verificado, incluido `symmetric` (la distancia es el total) |
| Cortes y agujeros | `ExtrudedCutouts.AddFiniteMulti`, `AddThroughAllMulti` | verificado; un corte que no toca material **no da error** (se detecta con `Body.Volume`); `AddThroughAllMulti` con `igSymmetric` no corta; se deshace con `Feature.Delete` |
| Revolución | `Models.AddFiniteRevolvedProtrusion`, `RevolvedProtrusions.AddFiniteMulti`, `Profile.SetAxisOfRevolution` | verificado (volumen de un tubo exacto); el eje se puede agregar con el perfil ya cerrado |
| Volumen | `Models.Item(1).Body.Volume` | verificado; el `Body` hay que pedirlo de nuevo después de cada operación |
| Aristas del cuerpo | `Body.Edges(igQueryAll)` | verificado: da las 12 aristas de una caja sin repetir las compartidas; **corregido**: el MCP dice que `Body.Edges` no anda en late binding y recorre `Face.Edges` (cada arista sale dos veces) |
| Datos de una arista | `Geometry.Type`, `IsClosed`, `GetEndPoints(v1, v2)`, `GetParamExtents()` + `GetLengthAtParam(min, max)`, `GetFaces()` | verificado; **corregido**: `Edge.Length`, `Edge.Faces` y `Edge.Name` no existen; `GetFaces()` devuelve `(n, (caras...))` y esas caras se comparan con `==` contra `Body.Faces(igQueryAll)` para saber su índice; un círculo completo tiene `IsClosed` y un arco no |
| Redondeo | `Model.Rounds.Add(n, [aristas], [radios])` | verificado con una lista de Python de aristas (una operación para todas); `GetConstantRadii()` devuelve `(n, radios)`; el redondeo agrega aristas (12 pasan a 24 con 4 redondeadas) y renumera |
| Chaflán | `Model.Chamfers.AddEqualSetback(n, [aristas], distancia)`, `AddSetbackAngle(cara, n, [aristas], distancia, angulo)` | verificado, también con varias aristas en una llamada; leídos con `ChamferSetbackValue1` y `ChamferSetbackAngle`; con distancia 4 mm y 30 grados sobre una arista de 50 mm quitó 230.94 mm3 (catetos de 4 y 4 tan 30 mm), con cualquiera de las dos caras de la arista como referencia; con una arista vieja (de antes de una operación) la llamada levanta una excepción |
| Operación imposible | `Status == igFeatureFailed` tras `Rounds.Add` / `Chamfers.Add*` | verificado: radio de 500 mm sobre una caja **no da error**: crea `Round_n` fallida, deja el volumen igual y hace fallar las operaciones nuevas hasta borrarla; `Feature.Delete()` la quita y el modelo vuelve a funcionar |
| Desarrollo de chapa | `FlatPatternModels.Add(modelo)`, `FlatPatterns.Add(arista, cara, vértice)`, `Face.Geometry.Type == igPlane` | verificado en chapa con un doblez; en la sesión sincrónica probada el DXF salió con entidades aun sin reabrir, pero se reabre igual |
| Brida de chapa (solo para armar la prueba) | `ModelingMode = seModelingModeSynchronous` antes del tab + `Flanges.AddSync` | verificado; en modo ordenado `Flanges.Add*` no resuelve |
| `se com` | `getattr` / `setattr` sobre late binding | verificado con `Documents.Item(...)`, `Models.Item(1)...`, `DisplayAlerts` |
| `se run` | `main(app, args)` en el hilo STA | verificado con un script de solo lectura |
| hresult de "ocupado" | `RPC_E_CALL_REJECTED` / `RPC_E_SERVERCALL_RETRYLATER` | no se vio ninguno durante las pruebas |

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
