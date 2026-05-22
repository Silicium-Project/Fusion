# Fragment Viewer (Qt)

Small Qt viewer for fragments/partitions produced by `summary.json`.

## Dependencies
- Qt 5 or Qt 6 (Widgets) + CMake >= 3.16

## Build
```bash
cmake -S viewer -B build/viewer
cmake --build build/viewer
```

### Build via Docker (stable environment)
```bash
docker build -t fragment-viewer -f viewer/Dockerfile .
# the binary is in the image under /src/viewer/build/fragment_viewer
docker create --name fv fragment-viewer
docker cp fv:/src/viewer/build/fragment_viewer ./fragment_viewer
docker rm fv
```

## Usage
```bash
./build/viewer/fragment_viewer /path/to/summary.json
```

The UI shows a simple dependency graph. Drag to pan, mouse wheel to zoom.

## Translations (Qt .ts/.qm)
The viewer loads `.qm` catalogs from a `translations/` directory next to the executable.

- Locale selection order:
- `SILICIUM_LOCALE` (example: `fr-FR`, `en-US`)
- system locale via Qt (`QLocale::system()`)
- File naming: `fragment_viewer_<locale>.qm` (example: `fragment_viewer_fr_FR.qm`)

If you have Qt tools installed (`lupdate`/`lrelease`), the CMake project exposes:
- `fragment_viewer_lupdate` to refresh `.ts` files from source strings
- `fragment_viewer_translations` to compile `.ts` into `.qm` and copy them next to the binary
