# Fragment executor

Ce sous-module compile uniquement l'exécuteur de fragments (`fragment_executor`). Il est invoqué depuis `../splitter` (cibles `make demo`, `make run`, etc.).

## Compilation

```bash
cd tools/experiments/fragment-executor
make
```

Le binaire `fragment_executor` est créé dans ce dossier.

## Utilisation directe

```bash
./fragment_executor --summary ../splitter/demo/output/summary.json \
  --input rax=0x0 \
  --log fragment_executor.log
```

Options utiles :

- `--native` : exécution native (risquée) des fragments.
- `--log <file>` : capture la sortie standard détectée (`puts`/`printf`).

En pratique, vous utiliserez ce binaire via `tools/experiments/splitter/Makefile`, qui se charge d'enchaîner partitionnement et exécution.
