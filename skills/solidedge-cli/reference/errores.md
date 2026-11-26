# Errores y trampas

Cada fila: qué se ve, el exit, la causa y qué hacer. Los exit codes y su `error.code` están en la tabla de `SKILL.md`; acá va el detalle. Leé siempre `error.message` y `error.details`: suelen traer la causa y un `hint`.

## Contenido

- Conexión y uso
- Modelado
- Ensambles
- Archivos y guardado
- Exportar, planos y chapa
- Masa y lecturas
- Timeout y diálogos modales

## Conexión y uso

| qué se ve | exit | causa | qué hacer |
|---|---|---|---|
| `no_conectado` | 3 | no hay Solid Edge abierto | pedirle al usuario que lo abra, o `se connect --launch` solo después de preguntarle o avisarle (lo arranca visible en su máquina; modifica) |
| `No such option: --json` | 2 | una opción global quedó después del comando | globales antes: `se --json --timeout 120 docs list` |
| `argumento_invalido` con un valor negativo | 2 | `-5mm` se lee como opción | `se vars set Largo -- -5mm`; en una opción, `--offset=-5mm` |
| `1,5mm` rechazado | 2 | el decimal es el punto | `1.5mm` |
| unidad de otra dimensión (`45deg` en una distancia) | 2 | la variable es de distancia | usar una unidad de su dimensión |
| un valor "sale mal por mil" | 0 | un valor sin unidad es SI (metros) | escribir `mm`, `deg`, `g` siempre |
| `--timeout` rechazado | 2 | fuera de `0 < SEG <= 3600` o no numérico | corregir el valor |
| `--readonly` bloquea | 6 | el comando modifica | sacar `--readonly` si el usuario quiere el cambio |

## Modelado

| qué se ve | exit | causa | qué hacer |
|---|---|---|---|
| el comando dice modo sincrónico, o tipo de documento inválido | 2 | el modelado anda solo en `part` y `sheetmetal` ordenados | crear el documento con `docs new part\|sheetmetal`, no en un ensamble ni en sincrónico |
| `extrude` o `revolve` como primera operación de una chapa | 6 | la base de una chapa es un Tab | `sheetmetal tab` (hint en `error.details`) |
| `hole` o corte sin modelo base | 2 | no hay sólido que cortar | crear la base primero (`extrude`, o `sheetmetal tab` en chapa) |
| `sheetmetal tab` rechazado | 2 | no es `sheetmetal`, es sincrónico o ya tiene base | para agregar material, `extrude` |
| `sheetmetal tab` sin perfiles | 5 | falta el croquis | `sketch` antes |
| corte o agujero que no quita material | 2 | no toca el sólido; la operación se deshace | `--direction reverse`, o revisar `--at` y `--plane` |
| agujero pasante con `symmetric` | 2 | Solid Edge no corta nada | `normal` o `reverse` |
| radio o chaflán demasiado grande | 4 | Solid Edge deja la operación en estado `failed`; la CLI la borra (`details.borrada`) | probar un valor menor; si `borrada` es `false`, borrarla a mano |
| `round` o `chamfer` con un índice de arista inexistente | 5 | los índices cambiaron tras una operación | rehacer `edges list` |
| `chamfer --angle` con aristas sin cara común | 2 | necesita una cara de referencia compartida | elegir aristas de una misma cara |
| `extrude` no crea nada con un círculo dentro de otro perfil | 0 | `sketch profile` con `auto_connect: false` | dejar `auto_connect: true` |
| `features suppress` de una operación sincrónica | 6 | la API no lo permite | ninguna salida por la CLI; avisar al usuario |
| `features list` deja el documento sin guardar | 0 | Solid Edge lo marca modificado al leer (`modificado_por_lectura: true`, con `advertencia`) | para cerrar, `docs close --save` o `--discard`; este último con confirmación y sin pérdida real |
| `vars set` sobre variable de solo lectura o con fórmula | 6 | protegida | `--force` solo si el usuario lo pide; la API decide si lo acepta |
| `vars add` de un nombre existente | 6 | ya existe | usar `vars set` |

## Ensambles

| qué se ve | exit | causa | qué hacer |
|---|---|---|---|
| `asm relate` entre dos ocurrencias | 4 | las ocurrencias nacen fijas y Solid Edge no resuelve una relación entre dos fijas; la CLI borra la relación | `asm ground <occ> --release` en una y repetir |
| `asm relate` con `relacion_borrada` | 4 | la relación quedó sin resolver o con otro offset | revisar caras y offset; `asm relations list` |
| cara incompatible (curva en `mate`/`align`, plana en `axial`) | 2 | tipo de cara | elegir caras planas o cilíndricas según el tipo |
| `--offset` con `axial` | 2 | `axial` no lo admite | quitarlo |
| mismas ocurrencias en `--a` y `--b` | 2 | una relación necesita dos ocurrencias distintas | corregir `--a` o `--b` |
| `asm *` sobre otro tipo de documento | 2 | solo ensambles | `--doc` al ensamble |
| `asm add` de un archivo inexistente | 5 | ruta mal | ruta absoluta que exista |
| `asm relate` o `edges list` ven otro documento | 0 | cambió el documento activo (`docs open`) | pasar `--doc` en cada comando |

## Archivos y guardado

| qué se ve | exit | causa | qué hacer |
|---|---|---|---|
| `docs save` de un documento nuevo | 2 | nunca se guardó | `docs save-as <ruta>` |
| `save-as`, `export` o `draft from-part` con destino existente | 6 | sin `--overwrite` Solid Edge abriría un modal | otra ruta, o `--overwrite` con OK del usuario |
| `--overwrite` sobre un archivo en uso | 6 | abierto en Solid Edge: `details.motivo = "archivo_en_uso"` y `details.abierto_en_solid_edge`; en uso por otro programa: `details.winerror` (32 o 33), y con otro código (como 5) `motivo: "acceso_denegado"` | cerrarlo (`docs close <doc>`) y repetir; el original quedó intacto |
| `docs close` con cambios | 6 | sin `--save` ni `--discard` | `--save`; `--discard` solo con confirmación del usuario |
| `docs close --all` rechazado | 2 | falta `--yes` | agregar `--yes`; con cambios pendientes y sin flag no cierra ninguno |
| ruta absoluta de 260 caracteres o más | 2 | límite de Solid Edge | ruta más corta |
| `docs new weldment` | 2 | exige plantilla (sin ella Solid Edge puede abrir un modal) | `--template <ruta a una plantilla>` |
| `docs open --read-only-doc` abre editable | 0 | la API no lo soporta | mirar `solo_lectura` y `advertencia`; el archivo solo queda de solo lectura si tiene ese atributo en Windows |
| `docs new` vence el timeout | 7 | `Documents.Add` no se cancela a mitad | `error.details.documento_pudo_crearse`: revisar `docs list` y cerrar el sobrante (`docs close <nombre> --discard`, con confirmación del usuario) |

## Exportar, planos y chapa

| qué se ve | exit | causa | qué hacer |
|---|---|---|---|
| formato que no encaja con el documento | 2 | `pdf` y `dxf` son solo de Draft | exportar desde el Draft; el desarrollo de chapa va por `sheetmetal flat-dxf` |
| export de un documento vacío a `stl`, `x_t` o `igs` (en un ensamble vacío, `stl` e `igs`; su `x_t` sale) | 6 | `details.causa = "documento_vacio"` | modelar algo antes (`step` sí sale vacío) |
| `export` falla con `E_FAIL` y sin causa | 4 | Solid Edge no explica | revisar el mensaje; `error.details.scode` y `hresult` para el informe |
| export de un documento sin guardar | 2 | falta ruta de salida (ver `error.message`) | `docs save-as` antes, o `--out` con ruta de archivo |
| lote con un fallo | 1 | `lote_con_fallos`: el resto sí se exportó | ver `error.details.resultados` y `resumen`; repetir los fallidos |
| `draft parts-list` rechazado | 2 | la vista no es de un `.asm` | `--view` de un ensamble |
| `draft dim` agrega 0 cotas | 0 | ya estaban, o no se ven en esa vista | probar otra vista |
| cotas o lista de piezas que no están en el `.dft` guardado | 0 | `draft dim` y `parts-list` no guardan el Draft | `docs save` del Draft |
| una vista pisa el rótulo | 0 | el layout reserva 30 mm y el rótulo ISO mide 50.8 mm | `--scale` menor (por ejemplo `1:2`) |
| PDF con leyenda "Solid Edge Community Edition" | 0 | Community Edition | no se quita; DXF y PNG no la traen |
| `sheetmetal flat-dxf` sin desarrollo | 5 | la chapa no lo tiene | repetir con `--create` (guarda, cierra y reabre la chapa) |
| `flat-dxf --create` rechazado por Solid Edge | 6 | no se puede desarrollar (por ejemplo, base que no es un Tab) | rehacer la chapa con `sheetmetal tab`; la chapa no se guardó; si quedó un desarrollo vacío en la sesión, cerrarla con `docs close <doc> --discard` |
| `flat-dxf --create` sobre chapa sin guardar o de solo lectura | 2 o 6 | exige chapa guardada y editable | `save-as` antes |

## Masa y lecturas

| qué se ve | exit | causa | qué hacer |
|---|---|---|---|
| `mass` pide densidad o dice `sin_material` | 2 | la pieza no tiene material (`details.causa`) | `material set <nombre>`; o `--density <kg/m3>` |
| `mass --density` en un ensamble | 6 | no existe cálculo con densidad en ensambles | asignar material a las piezas |
| masa de un ensamble con `advertencia` | 0 | piezas sin material cuentan 1 kg/m3 | asignarles material (`piezas_sin_material` las lista) |
| `material set` con un nombre que no existe | 5 | `details.parecidos` lista nombres parecidos | `material list` y usar uno de ahí |
| `material set` y la masa no cambia en el archivo | 0 | `material set` no guarda | `docs save` |
| `com get` devuelve un objeto sin contenido | 0 | una colección no se enumera sola | `--list` |

## Timeout y diálogos modales

El procedimiento ante un exit 7 está en la sección Timeout de `SKILL.md`. Para no provocar modales:

- Los comandos de `se` apagan `DisplayAlerts` y validan antes lo que abriría un diálogo (destino existente, weldment sin plantilla). Seguí sus mensajes en vez de saltearlos.
- No uses `se com invoke` para comandos de interfaz (`StartCommand` abre diálogos que `se` no puede cerrar).
- Con `--timeout`, una llamada única más larga que el plazo se corta aunque no haya modal (por ejemplo, un `docs new` lento): subí el valor y, antes de repetir, mirá el estado real (`status`, `docs list`): no reintentes a ciegas.
- Si vence el timeout con `--overwrite`, el archivo previo no se restaura ni se borra: queda apartado en `error.details.apartado`.
- Si el hilo COM quedó `abandonada` (`details.cancelacion`), `DisplayAlerts` puede quedar apagado hasta el próximo comando que escriba.
