---
name: solidedge-cli
description: 'Opera Solid Edge 2026 desde la terminal con la CLI `se` (COM, solo Windows): documentos, variables y cotas, propiedades, material y masa, croquis, extrusiones, revoluciones, agujeros, redondeos y chaflanes, ensambles y relaciones, planos (draft) con vistas y cotas, chapa y desarrollo DXF, y exportación a STEP, STL, PDF, DXF o PNG. Usar cuando el usuario pida "creá una pieza en Solid Edge", "exportá a STEP", "sacá la masa", "armá el ensamble", "hacé el plano con vistas y cotas", "cambiá la variable Largo", "sacá el DXF de la chapa" o automatizar Solid Edge por línea de comandos o por el servidor MCP se-mcp. No sirve para otros CAD.'
compatibility: Windows con Solid Edge 2026 instalado y la CLI `se` en el PATH (`uv tool install .` desde el repo solidedge-cli; Python 3.11 y uv).
---

# solidedge-cli (`se`)

`se` maneja Solid Edge 2026 Community Edition (uso no comercial) por COM. Cada invocación es un proceso nuevo: se engancha a la instancia abierta, hace lo suyo y se suelta. Trabaja sobre la sesión real del usuario. Solo `se connect --launch` arranca Solid Edge.

## Seguridad (leer antes de operar)

- Antes de un comando que **modifique o cierre** documentos, avisale al usuario si ya tenía documentos abiertos. Mirá `se --json docs list` primero.
- Piden **confirmación explícita del usuario**, siempre: `se com set`, `se com invoke`, `se run`, `se quit` y `se docs close --discard`.
- `se run` está bloqueado (exit 6) salvo `--allow-scripts`; el script corre con los permisos del usuario. `se com` rechaza el segmento `Quit`.
- `se connect --launch` arranca Solid Edge en la máquina del usuario: preguntale o avisale antes de lanzarlo.
- `--overwrite` pisa archivos del usuario: se usa solo con su OK.
- Ante la duda, probá con `--dry-run` (informa qué haría, valida los argumentos) o `--readonly` (bloquea todo lo que modifica, exit 6).
- No cierres ni descartes documentos que no abriste vos.
- Un diálogo modal en Solid Edge deja a `se` esperando: por eso `--timeout 120` va siempre (ver Timeout).

## Flujo de trabajo

Copiá esta checklist y tachala:

```
- [ ] 1. `se --json --timeout 120 status`; si no está conectado, `connect` (`connect --launch` solo tras avisarle al usuario)
- [ ] 2. `docs list`: ver qué tiene abierto el usuario y avisarle antes de modificar
- [ ] 3. Operar de a un comando por vez, siempre con `--json --timeout 120`
- [ ] 4. Leer el exit code y `ok` de cada salida antes del paso siguiente
- [ ] 5. Verificar lo hecho (`mass`, `features list`, `vars list`, `docs list`)
- [ ] 6. Guardar o exportar con ruta absoluta y decirle al usuario qué archivos quedaron
```

## Reglas de uso

1. `--json`, `--timeout`, `--dry-run` y `--readonly` son opciones globales y van **antes** del comando: `se --json --timeout 120 docs list`. La salida es un objeto `{"ok", "data", "error"}`; en error trae `error.code`, `error.message` y a veces `error.details`.
2. `status` sin Solid Edge no es error: exit 0 con `conectado: false`. Cualquier otro comando sin Solid Edge da exit 3.
3. Leé el exit code antes que el texto:

| exit | significado | `error.code` |
|---|---|---|
| 0 | ok | |
| 1 | interno, o lote de `export` con fallos | `interno`, `lote_con_fallos` |
| 2 | uso o argumento inválido (Solid Edge intacto) | `argumento_invalido` |
| 3 | Solid Edge no conectado | `no_conectado` |
| 4 | error COM | `com_error` |
| 5 | no encontrado (documento, variable, archivo) | `doc_no_encontrado` |
| 6 | bloqueado (`--readonly`, `se run`) o no soportado | `solo_lectura`, `no_soportado` |
| 7 | ocupado tras reintentos, o `--timeout` vencido (`error.details.motivo = "timeout"`) | `ocupado` |

4. Unidades: un valor sin unidad es SI (metros, radianes, kg). Escribí `mm`, `deg`, `g` explícitos (`10mm`, `45deg`); decimal con punto. Un negativo va después de `--` (`se vars set Largo -- -5mm`) o, en una opción, como `--offset=-0.002`. `--units mm,deg,g` solo cambia cómo se muestran los resultados.
5. `<doc>` y `--doc` aceptan índice (1-based, el de `docs list`), nombre o ruta; sin él, el documento activo.
6. Usá rutas absolutas en `save-as`, `export`, `asm add` y `draft from-part`.
7. El modelado (`sketch`, `extrude`, `hole`, `round`...) anda solo en `part` y `sheetmetal` en modo ordenado, no sincrónico.

## Tres trampas que cambian el orden de los pasos

- Los índices de arista y cara **cambian después de cada operación** (`round`, `chamfer`, `extrude`): rehacé `se edges list` antes de la siguiente.
- Las ocurrencias de ensamble **nacen fijas**: soltá una con `asm ground <occ> --release` antes de `asm relate`.
- La base de una chapa se crea con `se sheetmetal tab`, no con `extrude`.

El resto de los errores conocidos, con causa y salida, está en [reference/errores.md](reference/errores.md).

## Timeout y diálogos modales

`--timeout SEG` (`0 < SEG <= 3600`; si no, exit 2) tiene como alternativa la variable `SE_TIMEOUT`; el flag gana. Mide inactividad (segundos sin arrancar una llamada COM nueva), no la duración total, y no aplica a `se run`. Sin timeout, un modal deja a `se` esperando para siempre.

Ante un exit 7 con `error.details.motivo = "timeout"`:

1. Pedile al usuario que mire si hay un diálogo modal abierto en Solid Edge y lo cierre. Solid Edge no se cerró y la operación pudo completarse o quedar a medias.
2. Mirá el estado real con `status` y `docs list`. No reintentes a ciegas: `se` nunca reintenta solo.
3. Si fue `docs new`, mirá `error.details.documento_pudo_crearse`: con `true` puede haber un documento sobrante; cerralo con `docs close <nombre> --discard` (con confirmación del usuario).
4. Si fue con `--overwrite`, el archivo previo quedó apartado: su ruta está en `error.details.apartado`.

Un exit 7 sin `motivo = "timeout"` es Solid Edge ocupado tras 10 reintentos: esperá y probá `status`.

## Referencias

Leé solo la que haga falta:

| necesidad | archivo |
|---|---|
| sintaxis y opciones de un comando, campos de salida | [reference/comandos.md](reference/comandos.md) |
| recetas completas (pieza con masa, plano, chapa y DXF, ensamble, export) | [reference/recetas.md](reference/recetas.md) |
| un error, un exit code raro o un comportamiento inesperado | [reference/errores.md](reference/errores.md) |
| croquis con arcos, tangencias y restricciones (`sketch profile`) | [reference/sketch-profile.md](reference/sketch-profile.md) |

Si algo no coincide con estos archivos, mandan `se <grupo> --help` y el `README.md` del repo `solidedge-cli`.

## Servidor MCP

`se-mcp` (extra `mcp`) expone 16 tools con el mismo `{ok, data, error}`: `status`, `connect`, `docs_list`, `docs_open`, `docs_save`, `vars_get`, `vars_set`, `mass`, `material`, `export`, `features_list`, `sketch_profile`, `extrude`, `sheetmetal_tab`, `asm_add`, `asm_tree`. Cada una acepta `timeout` (segundos); sin él rige `SE_TIMEOUT` o 120. No expone `com`, `run` ni `quit`. Las tools que modifican (`vars_set`, `docs_save`, `docs_open`, `extrude`, `sketch_profile`, `sheetmetal_tab`, `asm_add`, `export` y `material` al asignar) llevan el mismo aviso previo al usuario, y el MCP no tiene `--dry-run` ni `--readonly`. En el cliente las tools aparecen con el prefijo del servidor (`Servidor:herramienta`). Detalle en [reference/comandos.md](reference/comandos.md#servidor-mcp-se-mcp).
