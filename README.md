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

## Códigos de salida

Son estables entre versiones; los fija un test (`tests/test_errores.py`).

| exit | significado | `error.code` |
|---|---|---|
| 0 | ok | |
| 1 | error interno o no clasificado | `interno` |
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
