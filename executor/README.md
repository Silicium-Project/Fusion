# Fragment executor

Ce sous-module compile l'exécuteur de fragments (`fragment_executor` / `fragment_emulator`).
Il est invoqué depuis `../splitter` (cibles `make demo`, `make run`, etc.).

## Compilation

```bash
cd executor
make
```

Les binaires et bibliothèques sont générés dans ce dossier.

## Tests unitaires

```bash
make test
```

La première exécution construit automatiquement l'image Docker `silicium/cpp-tests`
qui embarque `g++`, `cmake` et `googletest`.

## Utilisation directe

```bash
./fragment_executor --summary ../splitter/run_output/demo/summary.json \
  --input rax=0x0 \
  --log fragment_executor.log \
  --structured-log fragment_executor.ndjson
```

Options utiles :

- `--native` : exécution native (pas de repli ému, peut crasher selon les fragments).
- `--log <file>` : capture la sortie standard/erreur des fragments.
- `--structured-log <file.ndjson>` : écrit les événements structurés NDJSON (schema v1).
