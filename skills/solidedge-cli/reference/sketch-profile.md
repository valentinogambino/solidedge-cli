# `se sketch profile` — esquema v1

Crea un perfil cerrado de líneas, arcos y círculos con restricciones desde JSON, sin estado entre comandos.

En los ejemplos se omite `--json --timeout 120` por brevedad; en la práctica van siempre, antes del comando.

```powershell
se --json sketch profile perfil.json [--doc <selector>]
Get-Content perfil.json | se --json sketch profile -
```

El `data` es el de `sketch rect` (`perfil`, `plano`, `dimensiones_si`, `valido`, `codigo_end`) más `entidades` y `restricciones` (las aplicadas, incluidas las uniones automáticas). Pasá `perfil` a `extrude --profile` o `revolve --profile`. `--dry-run` (global, antes del comando) valida y devuelve el plan en SI sin tocar Solid Edge.

## Campos de primer nivel

Todo campo desconocido es exit 2.

| campo | |
|---|---|
| `version` | obligatorio, `1` |
| `plane` | `top` (por defecto), `front`, `right` o índice de `RefPlanes` |
| `units` | `m`, `mm`, `cm`, `in`, `ft`: unidad de los números sin unidad (obligatoria si hay alguno) |
| `tolerance` | número o string con unidad; por defecto 1e-6 m |
| `auto_connect` | por defecto `true`: un `connect` por cada par de extremos coincidentes |
| `close` | solo `true` (perfiles abiertos fuera de v1) |
| `entities` | lista no vacía |
| `constraints` | lista opcional |

Un punto es `[x, y]` en el plano del perfil; los números van en `units` o como string con unidad (`"50mm"`; un string sin unidad es exit 2).

## Entidades (cada una con `id` único, sin puntos)

| `type` | campos | nota |
|---|---|---|
| `line` | `from`, `to` | |
| `arc` | `center`, `start`, `end`, `dir` | `ccw` (por defecto) o `cw`; radios a `start` y `end` iguales dentro de `tolerance`; `start` distinto de `end` |
| `circle` | `center`, `radius` | lazo propio; dentro de un contorno es un agujero |
| `polyline` | `points` (al menos 2) | se expande a `p1.1`, `p1.2`...; para cerrarla, repetir el primer punto al final |

## Restricciones

Referencias: `<id>` para una entidad (`p1.2` es un segmento de polilínea) y `<id>.<punto>` para un punto (`start`/`end` en líneas y arcos, `center` en arcos y círculos).

| `type` | campos | se aplica a |
|---|---|---|
| `connect` | `a`, `b` (puntos) | une dos puntos |
| `horizontal`, `vertical` | `on` | una línea |
| `parallel`, `perpendicular` | `a`, `b` | dos líneas |
| `equal` | `a`, `b` | dos líneas (largo) o dos arcos/círculos (radio) |
| `concentric` | `a`, `b` | arcos o círculos |
| `tangent` | `a`, `b` | línea con arco o círculo, o dos arcos/círculos |

Las restricciones solo fijan intención: las coordenadas ya tienen que cumplirlas dentro de `tolerance` (si no, exit 2 sin tocar Solid Edge). Fuera de v1: cotas, perfiles abiertos, `collinear`, `symmetric`.

## Ejemplo: ranura de 50 x 20 mm con extremos redondos

Extruida 10 mm da 13141.593 mm3.

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

## Errores

- Exit 2 (Solid Edge intacto): JSON inválido, campos desconocidos, ids duplicados, referencias inexistentes, arco con radios distintos, coordenadas que no cumplen una restricción, contorno no cerrado.
- Exit 5: archivo inexistente. Exit 6: `--readonly`.
- Exit 4: Solid Edge rechaza algo a mitad; el perfil creado se borra y `error.details` trae la `etapa` (`perfil`, `entidades`, `restricciones`, `cierre`).
- Con `auto_connect: false` y un círculo dentro de otro lazo, el perfil cierra pero `extrude` no crea nada (sin error): dejá `auto_connect` en `true`.
