# Recetas

Flujos completos, en PowerShell. Cada comando lleva `--json --timeout 120` antes del subcomando. Las rutas `C:\p\...` y `C:\salida\...` son de ejemplo: usá las del usuario. Si una receta falla, cada error tiene su causa en `errores.md`; las opciones de cada comando, en `comandos.md`.

## Contenido

- Pieza con material y masa
- Plano con vistas y cotas
- Chapa y DXF
- Ensamble con relaciones
- Exportar (formatos, `--overwrite`, lotes)

Antes de cualquier receta: `se --json --timeout 120 status` y `docs list`, y avisar al usuario si tenía documentos abiertos. Las carpetas de destino tienen que existir (un destino en carpeta inexistente da exit 2; solo el lote de `export` crea su `--out`): `New-Item -ItemType Directory -Force C:\p, C:\salida`. `--overwrite` pisa archivos del usuario: solo con su OK.

## Pieza con material y masa

```powershell
se --json --timeout 120 docs new part
se --json --timeout 120 sketch rect --plane top --width 100mm --height 50mm
se --json --timeout 120 extrude 10mm
se --json --timeout 120 hole --at 50mm,25mm --diameter 8mm --through
se --json --timeout 120 edges list --units mm            # elegir por longitud y caras
se --json --timeout 120 round 2mm --edges <índices de edges list>   # los de la lectura anterior, no copiar a ciegas
se --json --timeout 120 material list --library Materials
se --json --timeout 120 material set Steel
se --json --timeout 120 mass --units mm,g                # lee el material: no hace falta --density
se --json --timeout 120 docs save-as C:\p\caja.par
```

- `material set` asigna el material y su densidad pero **no guarda**: el `save-as` del final lo guarda. Con material, `mass` sin `--density` da el valor real (acero de 7833 kg/m3: un prisma liso de 100 x 50 x 10 mm pesa 0.39165 kg; con el agujero y el redondeo de esta receta da algo menos). Usá `--density` solo si el usuario pide una densidad que no es la del material.
- Para otro lado del plano, `extrude --direction reverse` o `symmetric`. Para cambiar una medida después, `vars list --units mm` y `vars set <nombre> 20mm`: el modelo se recalcula.
- Verificá con `features list` (operaciones en orden y su estado) y comprobá la masa contra el volumen esperado cuando el usuario lo conozca.

## Plano con vistas y cotas

```powershell
se --json --timeout 120 draft from-part C:\p\caja.par --views front,top,right,iso --scale auto --sheet A3 --keep-open
se --json --timeout 120 draft dim --view 1 --auto       # vista 1 = front
se --json --timeout 120 draft dim --view 2 --auto       # vista 2 = top
se --json --timeout 120 docs save                       # draft dim no guarda el Draft
se --json --timeout 120 export --format pdf             # junto al .dft
```

- `from-part` crea y guarda `caja.dft` junto al modelo, y sin `--keep-open` lo cierra: en ese caso, `docs open C:\p\caja.dft` antes de acotar. `--pdf` genera el PDF en el acto, pero antes de las cotas; para un PDF acotado, exportalo al final (con `--overwrite` si ya existe, y con OK del usuario).
- `draft dim --auto` solo recupera las cotas del modelo que se ven en esa vista: en una caja extruida, la frontal da el alto de la extrusión y la superior no suma las del croquis. Repetirlo da 0 cotas nuevas.
- Ensamble: `draft from-part C:\p\conj.asm --keep-open`, luego `draft parts-list --view 1 --balloons` (lista de piezas y globos), y `docs save`.
- `--sheet` acepta A5 a A0 (A5 y A0 generan el fondo). Con escalas grandes una vista puede pisar el rótulo.
- El PDF de Community Edition lleva marca de agua en el borde inferior izquierdo; no se puede quitar.

## Chapa y DXF

```powershell
New-Item -ItemType Directory -Force C:\salida         # el destino tiene que existir
se --json --timeout 120 docs new sheetmetal
se --json --timeout 120 sketch rect --width 100mm --height 50mm
se --json --timeout 120 sheetmetal tab                   # base: espesor del material
se --json --timeout 120 hole --at 50mm,25mm --diameter 8mm --through
se --json --timeout 120 docs save-as C:\p\Chapa.psm
se --json --timeout 120 sheetmetal flat-dxf --create --out C:\salida\chapa.dxf
```

- La base de la chapa es `sheetmetal tab`, nunca `extrude`. Solo anda en `sheetmetal` ordenado y sin base previa; no acepta una cara existente. Para agregar material después, `extrude`.
- `flat-dxf --create` crea el desarrollo si falta, **guarda la chapa, la cierra y la reabre** antes de exportar: avisale al usuario si hay cambios sin guardar que se van a guardar con ella. Exige la chapa guardada en disco (de ahí el `save-as`). Si el desarrollo ya existe, no toca nada y exporta.
- Con un desarrollo hecho, `flat-dxf C:\p\Chapa.psm --out C:\salida\chapa.dxf` basta. Agregá `--overwrite` si el DXF ya existe y el usuario lo autoriza.
- Bridas: no hay comando. Con confirmación del usuario, `se run <script.py> --allow-scripts` con `Flanges.AddSync` sobre una base hecha en modo sincrónico; los agujeros en la cara doblada se hacen después, en modo ordenado, con `hole`.
- El DXF no lleva marca de agua.

## Ensamble con relaciones

Precondición: `caja.par` y `tapa.par` existen y están guardados (receta de pieza); `asm add` de un archivo inexistente da exit 5.

```powershell
se --json --timeout 120 docs new assembly
se --json --timeout 120 docs save-as C:\p\conj.asm
se --json --timeout 120 asm add C:\p\caja.par --doc conj.asm
se --json --timeout 120 asm add C:\p\tapa.par --at 0,0,20mm --doc conj.asm
se --json --timeout 120 asm tree --doc conj.asm
se --json --timeout 120 docs open C:\p\caja.par                       # edges list necesita la pieza abierta
se --json --timeout 120 edges list --doc caja.par --units mm          # índice de cara: caras[].indice
se --json --timeout 120 docs open C:\p\tapa.par
se --json --timeout 120 edges list --doc tapa.par --units mm
se --json --timeout 120 asm ground 2 --release --doc conj.asm          # las ocurrencias nacen fijas
se --json --timeout 120 asm relate mate --a 1:3 --b 2:1 --doc conj.asm # <occ>:<cara>
se --json --timeout 120 asm relations list --doc conj.asm
se --json --timeout 120 mass --doc conj.asm --units mm,g
se --json --timeout 120 docs save conj.asm
```

- Cada `docs open` cambia el documento activo: por eso los comandos de ensamble llevan `--doc conj.asm`.
- `<occ>:<cara>` es la ocurrencia (índice de `asm tree` o nombre) y el índice de cara de la pieza. `caja.par:2:5` es la cara 5 de `caja.par:2`.
- Tipos: `mate` (caras planas enfrentadas), `align` (planas alineadas), `axial` (ejes de dos caras cilíndricas). `--offset 5mm` solo en `mate` y `align`; negativo, `--offset=-5mm`.
- Una relación entre dos ocurrencias fijas da exit 4 y se borra sola: soltá una con `asm ground <occ> --release` y repetí. Si una relación queda mal, `asm relations delete <indice>` (los índices cambian al borrar).
- `asm move <occ> --by 5mm,0,0` reubica una ocurrencia; `asm remove <occ>` la borra sin tocar el archivo de la pieza.
- `mass` en un ensamble sale de los materiales de las piezas; las que no tienen cuentan 1 kg/m3 (`piezas_sin_material` y `advertencia` lo avisan).

## Exportar

```powershell
New-Item -ItemType Directory -Force C:\salida         # el destino tiene que existir (el lote la crea sola)
se --json --timeout 120 export --format step                             # documento activo, junto al archivo
se --json --timeout 120 export --format stl --out C:\salida\caja.stl --overwrite   # --overwrite: con OK del usuario
se --json --timeout 120 export --format pdf --doc Plano.dft --out C:\salida\plano.pdf
se --json --timeout 120 --dry-run export C:\p\piezas --format step --recursive --out C:\salida   # ver qué haría
se --json --timeout 120 export C:\p\piezas --format step --recursive --out C:\salida             # el lote
```

- Formatos: `step`, `stl`, `x_t`, `igs` de pieza, chapa y ensamble; `pdf` y `dxf` solo de un Draft; `png` de cualquiera. El DXF del desarrollo de una chapa sale con `sheetmetal flat-dxf`.
- Sin `--overwrite`, una salida existente da exit 6 (Solid Edge abriría un diálogo modal). Con `--overwrite`, el archivo previo se aparta y se restaura si falla. Si está en uso, exit 6 con el original intacto.
- El documento tiene que estar guardado o llevar `--out` con ruta de archivo. Sin `--out`, sale junto al origen.
- Lote: entradas (archivos, carpetas o globs) con `--out` carpeta. Un archivo que falla no corta el lote, pero el exit es 1 (`lote_con_fallos`): leé `error.details.resultados` para ver cuáles. Los archivos que no estaban abiertos se abren, se exportan y se cierran sin guardar; los que estaban abiertos quedan como estaban.
- Por MCP, `export` solo hace `step`, `stl`, `pdf` y `dxf` de un documento.
