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
