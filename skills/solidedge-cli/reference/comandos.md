# Comandos de `se`

Referencia de comandos y opciones, contrastada con `se <grupo> <sub> --help`. Ante una diferencia, el `--help` real y el `README.md` del repo `solidedge-cli` mandan. En los ejemplos se omite `--json --timeout 120` para abreviar: en la práctica van siempre, antes del comando (`se --json --timeout 120 docs list`).

## Contenido

- Opciones globales
- Sesión: `connect`, `status`, `quit`
- Documentos: `docs`
- Variables, propiedades y material: `vars`, `props`, `material`
- Masa: `mass`
- Croquis: `sketch`
- Sólidos: `extrude`, `revolve`, `hole`, `edges`, `round`, `chamfer`, `features`
- Ensambles: `asm`
- Exportar: `export`
- Planos: `draft`
- Chapa: `sheetmetal`
- Escape a COM: `com`, `run`
- Servidor MCP (`se-mcp`)

## Opciones globales

Van antes del comando.

| opción | efecto |
|---|---|
| `--json` | Una línea `{ok, data, error}` por stdout, sin colores. También los errores de uso salen como sobre `argumento_invalido` (exit 2). Sin `--json` sale una tabla y los errores van a stderr. |
| `--readonly` | Bloquea todo comando que modifica (exit 6, `solo_lectura`), sin tocar Solid Edge. |
| `--dry-run` | Los comandos que modifican informan qué harían (`"dry_run": true`). Los argumentos se validan igual. |
| `--timeout SEG` | Máximo de segundos esperando una llamada COM (exit 7 al vencer). También `SE_TIMEOUT`. Sin esto espera sin límite. |
| `--version` | Versión de `se`. |

## Sesión

- `se connect [--launch]`: se engancha a Solid Edge; sin instancia, exit 3. `--launch` lo arranca (modifica) y lo deja visible (`"lanzada": true`).
- `se status`: `conectado`, `version`, `visible`, `documentos`, `activo`. Sin instancia, exit 0 y `conectado: false`.
- `se quit --yes [--discard]`: cierra Solid Edge. Sin `--yes`, exit 2. Con documentos con cambios sin guardar se niega (exit 6) salvo `--discard`. Confirmar siempre con el usuario.

## Documentos

- `se docs list`: `indice`, `nombre`, `ruta`, `tipo` (`part`, `assembly`, `draft`, `sheetmetal`, `weldment` o `desconocido`), `modificado`, `activo`, `solo_lectura`. `ruta` es `null` si el documento nunca se guardó.
- `se docs active`: el activo; sin documento, exit 5.
- `se docs open <ruta> [--read-only-doc]`: si ya estaba abierto lo activa (`ya_abierto: true`). Ruta inexistente: exit 5. `--read-only-doc` no abre en solo lectura de verdad (la API no lo soporta): mirá `solo_lectura` y `advertencia`.
- `se docs new <tipo> [--template <ruta>]`: `part`, `assembly`, `draft`, `sheetmetal` o `weldment` (este exige `--template`). Tarda 2 a 4 s. La salida trae el documento creado (`data.nombre`, `indice`, `tipo`...): guardá el `nombre` para los comandos siguientes (`docs close <nombre>`). Si vence el timeout, mirá `error.details.documento_pudo_crearse`: con `true` puede haber un documento sobrante (`docs list`, y `docs close <nombre> --discard` con confirmación).
- `se docs save [<doc>]`: un documento nunca guardado da exit 2 y pide `save-as`.
- `se docs save-as <destino> [<doc>] [--overwrite]`: si el destino existe y no hay `--overwrite`, exit 6. Con `--overwrite` el anterior se aparta y se restaura si el guardado falla. Destino en uso: exit 6 con el original intacto; abierto en Solid Edge, `details.motivo = "archivo_en_uso"`; en uso por otro programa, `details.winerror` (32 o 33) y, con otro código, `motivo: "acceso_denegado"`.
- `se docs close [<doc>] [--save | --discard]`: con cambios y sin flag se niega (exit 6). `--all` exige `--yes`; si algún documento tiene cambios y no hay flag, no cierra ninguno. `--discard` pide confirmación del usuario.

## Variables, propiedades y material

Todos aceptan `--doc`, salvo `material list` (solo `--library`).

- `se vars list [--filter "Largo*"] [--units mm]`: variables y cotas (`es_cota`). Comodines `*` y `?`.
- `se vars get <nombre> [--units mm]`: inexistente, exit 5.
- `se vars set <nombre> [<valor>] [--formula "Ancho*2"] [--force] [--units ...]`: devuelve `{nombre, antes, despues}`. Una variable de solo lectura, o con fórmula cuando se da un valor, da exit 6 salvo `--force`. Una unidad de otra dimensión (`45deg` en una distancia): exit 2.
- `se vars add <nombre> <valor> [--unit-type distance|angle|mass|scalar|area|volume|...] [--units ...]`: variable de usuario; si ya existe, exit 6. El tipo se deduce de la unidad si no se pasa.
- `se props get [<nombre>] [--set SummaryInformation|ProjectInformation|Custom]`: sin nombre, lista todas. Inexistente: exit 5; en varios conjuntos pide `--set` (exit 2).
- `se props set <nombre> <valor> [--set Custom] [--save]`: no guarda el documento sin `--save`. En `Custom` crea la propiedad; en otro conjunto, una inexistente da exit 5.
- `se material list [--library Materials|Materials-DIN]`: materiales por biblioteca (por defecto, todas). Biblioteca inexistente: exit 5.
- `se material get`: el material del documento (`null` si no tiene).
- `se material set <nombre> [--library ...]`: asigna material y densidad a una pieza o chapa (sin distinguir mayúsculas). **No guarda el documento.** Nombre inexistente: exit 5 (con `details.parecidos`). Solo pieza y chapa. Si el usuario pide "acero" a secas, `Steel` de `Materials` es el genérico (7833 kg/m3); si pide uno específico (inoxidable, estructural, galvanizado, una norma), buscalo con `material list --library Materials` y, si hay duda, preguntale.

## Masa

`se mass [--density <kg/m3>] [--units mm,g] [--doc]`: `masa`, `volumen`, `area`, `densidad`, centros, inercia. Pieza, chapa y ensamble.

- Sin `--density` lee lo guardado en el modelo (lectura pura, `actualizado: false`). Una pieza sin material da exit 2 con `details.causa = "sin_material"`: asigná uno con `material set` (camino recomendado) o pasá `--density`.
- Con `--density` recalcula, lo que modifica el estado del documento (lo bloquea `--readonly`). En ensamble no existe: exit 6. En un ensamble, una pieza sin material cuenta con densidad 1 kg/m3 (`data.piezas_sin_material`, `data.advertencia`) y `area` es `null`.

## Croquis

Planos: `top` (XY), `right` (YZ), `front` (XZ) o el índice de `RefPlanes` (1, 2, 3). Cada `sketch` devuelve `perfil` (número que se pasa a `--profile`).

- `se sketch rect --width <v> --height <v> [--plane top] [--at x,y] [--centered]`: `--at` es la esquina inferior izquierda, o el centro con `--centered`.
- `se sketch circle (--radius <v> | --diameter <v>) [--plane top] [--at x,y]`: `--at` es el centro.
- `se sketch profile <perfil.json | ->`: líneas, arcos y círculos con restricciones. Esquema completo en `sketch-profile.md`.

## Sólidos

Solo `part` y `sheetmetal` en modo ordenado. Sin `--profile`, `extrude` y `revolve` usan el último perfil.

- `se extrude <distancia> [--profile N] [--direction normal|reverse|symmetric] [--cut]`: la primera operación crea el modelo base. Con `--cut` corta; un corte que no toca material da exit 2 y se deshace (probá `--direction reverse`). En una chapa sin base, exit 6: usar `sheetmetal tab`.
- `se revolve [<ángulo>] --axis x|y [--profile N]`: ángulo por defecto `360deg`; el perfil tiene que quedar de un solo lado del eje.
- `se hole --at x,y --diameter <v> (--depth <v> | --through) [--plane top] [--direction normal|reverse|symmetric]`: agujero simple (crea su propio perfil). Un pasante no admite `symmetric`.
- `se edges list [--units mm]`: aristas (`indice`, `tipo`, `longitud`, `caras[].indice`) y `cantidad_caras`.
- `se round <radio> --edges all|1,3,5|1-4 [--units ...]`: radio constante, una sola operación. `--edges` es obligatorio.
- `se chamfer <distancia> --edges all|1,3,5|1-4 [--angle 30deg] [--units ...]`: sin `--angle`, distancias iguales; con `--angle`, distancia + ángulo (las aristas tienen que compartir una cara; si no, exit 2).
- `se features list`: operaciones en orden (solo pieza y chapa). Informa `modificado_por_lectura`.
- `se features suppress|unsuppress <índice|nombre>`: idempotentes. Una operación sincrónica no se puede suprimir (exit 6).

Todos aceptan `--doc`. Un radio o chaflán demasiado grande da exit 4 y la operación fallida se borra.

## Ensambles

Solo `assembly` (otro tipo, exit 2). `<occ>` es el `indice` de `asm tree` o el nombre (`caja.par:2`). Todos aceptan `--doc`; los que posicionan, `--units`.

- `se asm tree [--depth 10] [--flat]`: árbol de ocurrencias, o lista de materiales por archivo con `--flat`.
- `se asm add <archivo> [--at x,y,z] [--rot rx,ry,rz]`: inserta `.par`, `.psm`, `.asm` o `.pwd`. Nace fijo. Sin unidad, metros y radianes.
- `se asm ground <occ> [--release]`: fija o suelta. Idempotente (`changed`).
- `se asm move <occ> (--at x,y,z | --by dx,dy,dz) [--rot rx,ry,rz]`: `--at` absoluto, `--by` relativo (no van juntos).
- `se asm remove <occ>`: borra la ocurrencia y sus relaciones, no el archivo.
- `se asm relate mate|align|axial --a <occ>:<cara> --b <occ>:<cara> [--offset 5mm]`: la cara es el índice de `edges list` en la pieza (`caja.par:2:5` = cara 5 de `caja.par:2`). `mate`: planas enfrentadas; `align`: planas alineadas; `axial`: ejes de dos caras cilíndricas. `axial` no admite `--offset`; un offset negativo va como `--offset=-2mm`.
- `se asm relations list`: `indice`, `tipo`, `ocurrencias`, `offset`, `estado` (`resuelta`, `entre_fijas`, `insatisfecha`...).
- `se asm relations delete <indice>`: acepta también una relación ground.

## Exportar

`se export [entradas...] --format step|stl|x_t|igs|pdf|dxf|png [--out <ruta>] [--overwrite] [--recursive] [--doc]`

| `--format` | alias | admite |
|---|---|---|
| `step` | `stp` | `part`, `sheetmetal`, `assembly` |
| `stl` | | `part`, `sheetmetal`, `assembly` |
| `x_t` | `parasolid` | `part`, `sheetmetal`, `assembly` |
| `igs` | `iges` | `part`, `sheetmetal`, `assembly` |
| `pdf`, `dxf` | | solo `draft` |
| `png` | | todos (1920 px de lado mayor) |

- Sin entradas exporta el documento activo (o `--doc`); tiene que estar guardado o llevar `--out` con ruta de archivo. Sin `--out` sale junto al origen.
- Si la salida existe y no hay `--overwrite`: exit 6. Un formato que no encaja con el tipo de documento: exit 2.
- Lote: con entradas (archivos, carpetas o globs; `se` expande el `*`) exporta cada una; `--out` tiene que ser una carpeta (se crea) y `--recursive` baja por subcarpetas. Un archivo ya abierto se usa sin cerrarlo; si no, se abre, se exporta y se cierra sin guardar. Si falla alguno, exit 1 (`lote_con_fallos`) con `error.details.resultados` y `resumen`.
- El PDF de Community Edition lleva marca de agua; DXF y PNG no.

## Planos

- `se draft from-part <modelo> [--out <.dft>] [--views front,top,right,iso] [--scale auto|1:2|2:1|0.5] [--sheet A5..A0] [--template <.dft>] [--pdf] [--overwrite] [--keep-open]`: crea el Draft con las vistas de un `.par`, `.psm` o `.asm`, lo guarda (junto al modelo por defecto) y lo cierra salvo `--keep-open`. Vistas válidas: `front`, `top`, `right`, `left`, `bottom`, `back`, `iso`. Nunca modifica el modelo. `--sheet` A5 y A0 generan el fondo (`hoja.fondo_generado`).
- `se draft dim [--view N] --auto [--doc]`: cotas del modelo en una vista del Draft activo (`--auto` es obligatorio; solo recupera las que se ven en esa vista). No guarda el Draft.
- `se draft parts-list [--view N] [--balloons] [--doc]`: lista de piezas de una vista de un `.asm` (con una vista de pieza, exit 2). No guarda el Draft.

`--view` es 1-based, en el orden en que se agregaron las vistas (por defecto 1).

## Chapa

- `se sheetmetal tab [--profile N] [--direction normal|reverse] [--sync] [--doc]`: crea la base desde un perfil cerrado (por defecto, el último); el espesor es el del material (variable `MaterialThickness`: `vars set` antes del tab). Solo `sheetmetal` sin base (si no, exit 2; sin perfiles, exit 5). No acepta una cara existente. Con `--sync` la base queda en modo sincrónico (`data.modo = "sincronico"`), que es el que necesita `flange`; después, `edges list` anda pero `sketch`, `extrude`, `hole`, `round` y `chamfer` piden modo ordenado.
- `se sheetmetal flange --edge N --length L [--angle 90] [--direction normal|reverse] [--radius R] [--measure face|opposite] [--units] [--doc]`: levanta una brida sobre una arista recta (índice de `edges list`). Solo sobre base sincrónica: con base ordenada, exit 6 `causa: base_ordenada` (crear la base con `tab --sync`). `--length` se mide según `--measure`: con `face` (por defecto) desde el plano de la cara que contiene la arista hasta el borde libre, sobre la cara interior de la pared (a 90° la altura total sobre la cara opuesta es largo + espesor); la pared recta mide `L − r·cot(ángulo/2)` y tiene que quedar positiva (a 90°, `--length` mayor que el radio). Con `opposite` se mide desde el plano de la cara opuesta (a 90° la altura total es el largo): la pared recta mide `L − (r + espesor)·cot(ángulo/2)` y `--length` tiene que superar `(r + espesor)·cot(ángulo/2)` (a 90°, radio más espesor); la base y el doblez no cambian. `data.medida` informa la elegida; otro valor: exit 2. `--angle` es el ángulo entre la pared y la base (el doblez barre 180° − ángulo). `normal` deja la pared dentro de la huella de la base; `reverse`, fuera: el largo de la pared es el mismo y cambia cuánto se recorta la base (`W − r·cot(ángulo/2)` con `reverse`, y además `− espesor/sen(ángulo)` con `normal`; a 90° y radio 1 mm de 1 mm de espesor: 49 mm contra 48 mm), así que `reverse` suma `ancho·espesor²/sen(ángulo)` de volumen. Sin `--radius` usa `BendRadius` del documento (`data.radio_origen` = `documento` o `explicito`). El sentido de levante lo fija la arista: una de la cara superior levanta hacia arriba. Parámetros que Solid Edge rechaza: exit 4 `causa: brida_rechazada`; arista inexistente: exit 5; arista no recta: exit 2.
- `se sheetmetal flat-dxf [<archivo.psm>] [--out <.dxf|carpeta>] [--overwrite] [--create] [--doc]`: exporta el desarrollo. Sin desarrollo, exit 5 salvo `--create`, que lo crea, **guarda la chapa**, la cierra, la reabre y exporta (exige chapa guardada y no de solo lectura). Si Solid Edge no puede desarrollarla, exit 6 sin guardar.
- Los agujeros en la cara doblada no se pueden hacer con la base sincrónica: `hole` pide modo ordenado.

## Escape a COM

Con confirmación del usuario, salvo `com get`.

- `se com get <ruta> [--list] [--limit 50]`: lectura (sirve con `--readonly`). La ruta parte de `Application` (`ActiveDocument.Name`, `Documents.Item(1).Name`). Una colección no se enumera sola: usar `--list`.
- `se com set <ruta> <valor>` y `se com invoke <ruta> [argumentos...]`: modifican. Parser estricto sin `eval`; valores en SI y literales (`10`, `0.5`, `"texto"`, `true`, `false`, `null`), no `10mm`. `Quit` está denegado (exit 6).
- `se run <script.py> --allow-scripts [-- args...]`: el script define `main(app, args)`. Sin el flag, exit 6 sin leer el archivo. No tiene timeout.

## Servidor MCP (`se-mcp`)

17 tools sobre las mismas funciones que la CLI, con el mismo `{ok, data, error}`. Cada tool valida sus argumentos contra un esquema (claves de más o tipos erróneos se rechazan antes de tocar Solid Edge). Todas aceptan `timeout` (segundos, `0 < t <= 3600`); sin él rige `SE_TIMEOUT` del servidor o, si no, 120 s. Al vencer devuelve `ocupado` y el servidor sigue vivo.

| tool | equivale a |
|---|---|
| `status`, `connect` | `se status`, `se connect` (no lanza Solid Edge) |
| `docs_list`, `docs_open`, `docs_save` | `se docs list`, `open`, `save` |
| `vars_get`, `vars_set` | `se vars get`, `set` |
| `mass` | `se mass` |
| `material` | `se material get`; con `name`, `se material set` |
| `export` | `se export` de un documento: solo `step`, `stl`, `pdf`, `dxf` |
| `features_list` | `se features list` |
| `sketch_profile` | `se sketch profile` |
| `extrude` | `se extrude` |
| `sheetmetal_tab` | `se sheetmetal tab` |
| `sheetmetal_flange` | `se sheetmetal flange` (incluye `measure`: `face` u `opposite`) |
| `asm_add`, `asm_tree` | `se asm add`, `se asm tree` |

No están `com`, `run` ni `quit`. Lo que no tiene tool (`revolve`, `hole`, `round`, `chamfer`, `draft`, `props`, `asm relate`, `sheetmetal flat-dxf`...) se hace por la CLI.
