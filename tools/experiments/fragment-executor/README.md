# Fragment executor

Ce sous-module compile uniquement l'exécuteur de fragments (`fragment_executor`). Il est invoqué depuis `../splitter` (cibles `make demo`, `make run`, etc.).

## Compilation

```bash
cd tools/experiments/fragment-executor
make
```

Le binaire `fragment_executor` est créé dans ce dossier.

## Tests unitaires

```bash
make test
```

La première exécution construit automatiquement l'image Docker `silicium/cpp-tests`
qui embarque `g++`, `cmake` et `googletest`. Cette étape peut prendre une à deux
minutes mais n'est effectuée qu'une seule fois. Les exécutions suivantes
réutilisent l'image et démarrent en quelques secondes. Vous pouvez remplacer
l'image par défaut en définissant `CPP_TEST_IMAGE=<tag>` avant d'appeler `make test`.
Un cache `ccache` persistant est monté dans `.cache/cpp-tests/ccache` : la
première compilation prend ~15 s mais les relances retombent ensuite sous la
seconde tant que les sources ne changent pas.

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
