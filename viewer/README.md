# Fragment Viewer (Qt)

Petit visualiseur Qt des fragments/partitions issus de `summary.json`.

## Dépendances
- Qt 5 ou Qt 6 (modules Widgets) + CMake >= 3.16

## Build
```bash
cmake -S viewer -B build/viewer
cmake --build build/viewer
```

### Build via Docker (environnement stable)
```bash
docker build -t fragment-viewer -f viewer/Dockerfile .
# le binaire est dans l'image sous /src/viewer/build/fragment_viewer
# pour le récupérer :
docker create --name fv fragment-viewer
docker cp fv:/src/viewer/build/fragment_viewer ./fragment_viewer
docker rm fv
```

## Usage
```bash
./build/viewer/fragment_viewer /chemin/vers/summary.json
```

L’interface affiche un graphe simple des fragments avec leurs dépendances. Les nœuds parallélisables sont colorés en vert, les séquentiels en jaune. Glisser pour naviguer, molette pour zoomer.
