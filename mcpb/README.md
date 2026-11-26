# Solid Edge para Claude Desktop

Extensión local para Solid Edge 2026 en Windows x64. Al configurarla,
seleccioná el ejecutable de Python 3.11 x64. El paquete incluye el servidor
y sus dependencias. Abrí Solid Edge antes de usar las herramientas. La opción **Timeout (s)**
(por defecto 120) fija cuántos segundos espera cada herramienta una respuesta de Solid Edge; al
vencer devuelve `ocupado` sin cerrar Solid Edge, y cada herramienta acepta un `timeout` propio.

Herramientas (16): `status`, `connect`, `docs_list`, `docs_open`, `docs_save`,
`vars_get`, `vars_set`, `mass`, `material`, `export`, `features_list`, `sketch_profile`,
`extrude`, `sheetmetal_tab`, `asm_add` y `asm_tree`. En una chapa nueva, la
base se crea con `sheetmetal_tab` (no con `extrude`).
