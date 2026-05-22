# Splitter

Ce dossier contient uniquement le découpeur/désassembleur (`splitter`).  
L'exécuteur vit désormais dans `../executor` et est invoqué automatiquement par les cibles `make demo`, `make run`, etc.

- `splitter` désassemble un exécutable (ELF ou PE), reconstruit les fonctions, analyse leurs dépendances, détecte certaines boucles et génère des fragments autonomes (ASM et code machine) accompagnés d'un fichier `summary.json`.
- `../executor/fragment_executor` émule l'exécution de ces fragments (mode sécurisé ou natif).

Les scripts s'appuient sur `objdump`/`readelf` (binutils) pour la phase de désassemblage et ciblent principalement Linux x86_64.

## Architecture rapide

- Pipeline compose de phases independantes (desassemblage, analyse, partitionnement, artefacts).
- Chaque phase expose ses entrees/sorties via `IPipelinePhase::Inputs()` / `Outputs()`.
- Les effets de bord (shell, env, systeme de fichiers) passent par `SystemContext` pour faciliter les tests.
- Selection des strategies via factories (`DisassemblerFactory`, `InstructionAnalyzerFactory`).
- L'analyse des instructions est centralisee dans la phase `Analysis` (disassembleur neutre, analyseur configurable).


## Contenu principal

- `splitter.cpp` : découpeur/désassembleur de binaires, génère `.asm`, `.bin`, wrappers C et `summary.json`.
- `../executor/fragment_executor.cpp` : exécuteur de fragments avec émulateur de registres et mode natif expérimental.
- `splitter` et `../executor/fragment_executor` : binaires générés (Linux).

## Prérequis

- Linux x86_64 (le mode natif de `fragment_executor` repose sur `mmap`).
- Un compilateur C++17 (`g++` 10+ recommandé).
- binutils (`objdump`, `readelf`) disponibles dans le `PATH`.
- Accès en lecture à l'exécutable à analyser.

## Compilation

- `make` : compile `splitter` (et déclenche `make` dans `../executor` au besoin).
- `make clean` : supprime les binaires générés et la sortie de démo.

Si vous préférez compiler manuellement :

```bash
g++ -std=c++17 -O2 splitter.cpp -o splitter
cd ../executor && g++ -std=c++17 -O2 fragment_executor.cpp -o fragment_executor
```

## Tests unitaires

```bash
make test
```

Nettoyage des artefacts de couverture avant relance :

```bash
make test-clean
```

Comme pour `executor`, la première exécution construit automatiquement
l'image Docker `silicium/cpp-tests` (compilateurs + googletest). Une fois l'image
présente en local, les tests s'exécutent en quelques secondes. Vous pouvez
surcharger l'image en exportant `CPP_TEST_IMAGE=<tag>` avant d'appeler `make test`.
Un cache `ccache` partagé (`.cache/cpp-tests/ccache`) est monté dans le conteneur :
après la première compilation (~15 s), les itérations suivantes retombent sous la
seconde tant que les sources restent inchangées.

## Démo automatisée

Une cible `make demo` prépare un binaire jouet (`demo/fragment/hello.c`), lance le partitionnement puis exécute les fragments en mode émulation :

```bash
make demo
```

Pour choisir l'algo de hash dans la demo :

```bash
DEMO_HASH=std make demo
```

La sortie console montre :

- l’exécution de `splitter` sur `run_build/hello_demo`,
- la génération des partitions dans `run_output/demo/`,
- l’exécution séquentielle des fragments via `fragment_executor` (avec l’impression des registres modifiés).
- les appels à `puts`/`printf` détectés pendant l’émulation sont rejoués pour capturer la sortie standard attendue dans `fragment_executor.log`, sans les messages de l’exécuteur.

Une cible `make demo-native` relance la même chaîne mais tente le mode `--native`. Celui-ci mappe le code machine et peut planter selon votre environnement ; la cible ignore l’échec mais laissez-la uniquement pour vos propres expérimentations.

⚠️ Le mode natif ne recrée pas la PLT/GOT du binaire original. Les fragments qui appellent des fonctions externes (ex. `puts@plt`) provoqueront donc un segfault lors d’une exécution isolée (`--native` sur un seul `.asm`). Ce mode sert uniquement à tester des fragments totalement autonomes ou à expérimenter une exécution complète via `--summary` associée au binaire d’origine.

Pour automatiser compilation + découpage/exécution à partir d’un fichier source C/C++ :

```bash
make run PROGRAM=./chemin/vers/source.c        # mode émulation
make run-native PROGRAM=./chemin/vers/source.c # mode natif (risqué)
```

Extensions supportées : `.c`, `.cc`, `.cxx`, `.cpp`. Les binaires intermédiaires sont placés dans `run_build/`.  
Variables optionnelles : `OUT=<dir>` pour choisir le dossier de partitions, `LOG=<fichier>` pour fixer le fichier de capture (`fragment_executor.log` par défaut).

Pour vérifier rapidement le comportement original (sans partitionnement) :

```bash
make run-binary PROGRAM=./chemin/vers/source.c ARGS="arg1 arg2"
```

Ensuite, utilisez les redirections shell habituelles (`< input.txt`, pipes…) pour fournir `stdin`.

## Utilisation

### 1. Découper un binaire

```bash
./splitter ./chemin/vers/binaire --output-dir partitions [--hash fnv|std] [--resolver ldd|readelf] [--indexer nm|objdump]
```

Résultats générés par défaut :

- `disassembly_full.asm` : désassemblage complet pour inspection.
- `partitions/<id>.asm` : code assembleur Intel de chaque fragment.
- `partitions/<id>.bin` : code machine brut (pour le mode natif).
- `partitions/<id>_wrapper.c` : squelette C pour intégrer le fragment.
- `partitions/summary.json` : métadonnées (dépendances, registres, parallélisabilité, chemins de fichiers).

Options de hachage et de scan :
- `--hash fnv|std` ou `SPLITTER_HASH_ALGO` pour choisir l'algorithme (par d?faut FNV).
- `--resolver ldd|readelf` ou `SPLITTER_LIB_RESOLVER` pour s?lectionner le d?tecteur de biblioth?ques.
- `--indexer nm|objdump` ou `SPLITTER_SYMBOL_INDEXER` pour s?lectionner l'indexeur de symboles.

Cas "no-bytes" : si aucun octet n'est extractible (binaire minimal/sections vides),
les hashes sont calcul?s sur une entr?e vide et restent stables. Valeurs actuelles :
- FNV : `0xcbf29ce484222325`
- std : `0x9e3779b97f4a7c15`



### 2. Exécuter des fragments

- Exécution sécurisée (émulateur) sur un ou plusieurs fichiers ASM :

  ```bash
  ../executor/fragment_executor partitions/func_3_main.asm --input rax=0x100 rbx=42
  ```

- Exécution en chaîne à partir du `summary.json` produit par `splitter` :

  ```bash
  ../executor/fragment_executor --summary partitions/summary.json --input rax=0x0
  ```

  L'outil reconstruit l'ordre d'exécution via un tri topologique et injecte les valeurs `--input` requises par chaque fragment.

- Mode natif (JIT) :

  ```bash
  ../executor/fragment_executor --summary partitions/summary.json --native
  ```

  ⚠️ Ce mode mappe le code machine en mémoire exécutable. Les fragments qui appellent la PLT (ex. `puts`) dépendront d’un environnement identique au binaire original et peuvent crasher lorsqu’ils sont lancés isolément.

Ajoutez l'option `--log fichier.log` pour enregistrer **uniquement** la sortie standard produite par les fragments (détection basique de `puts`/`printf` incluse).

Les valeurs passées à `--input` peuvent être décimales ou hexadécimales (`0x...`). Après chaque fragment, l'outil affiche les registres modifiés et l'état global.

## Exemple de flux de travail

1. Compiler ou copier un binaire cible (ELF x86_64).
2. `./splitter ./a.out --output-dir partitions_test`
3. Inspecter `partitions_test/summary.json` et les fichiers ASM générés.
4. `./fragment_executor --summary partitions_test/summary.json --input rax=0x0`
5. Ajuster les entrées ou exécuter des fragments isolés selon les besoins.

Les dossiers `partitions/` et `partitions_test/` fournis servent d'exemples reproductibles pour valider la chaîne.

## Limitations connues

- L'émulateur d'instructions couvre un sous-ensemble d'opcodes x86_64 courants (`mov`, `add`, `sub`, `xor`, `inc`, `dec`, `push`, `pop`, `ret`, `nop`). Les instructions inconnues sont ignorées, ce qui peut tronquer certains effets de bord.
- La détection de boucles/parallélisabilité reste heuristique.
- Le mode natif n'est implémenté que sous Linux et ne capture pas automatiquement l'état mémoire ; il est principalement destiné à des expérimentations locales.

## Travaux prévus

- Ajout d’un format de snapshot (registres + plages mémoire écrites) pour transporter l’état d’un fragment à l’autre et simuler la mémoire partagée.
- Étendre l’analyse pour détecter les dépendances mémoire implicites et verrouiller les zones conflictuelles.
- Introduire un score de fiabilité par nœud (audits, fragments de test) qui influence les récompenses et la planification.
- Intégrer la mesure de consommation énergétique (via prises connectées) et l’intensité carbone locale pour valoriser les kWh “verts”.
- Simuler la spécialisation du réseau (pools CPU, GPU, stockage froid) dans l’orchestrateur et le démonstrateur local.

## Dépannage rapide

- **`Erreur: objdump introuvable`** : installez `binutils` (`sudo apt install binutils` sur Debian/Ubuntu).
- **Sorties vides ou partielles** : vérifiez que le binaire cible n'est pas stripé de toutes les symboles et que `objdump -d` le prend bien en charge.
- **`--input` ignoré** : `fragment_executor` signale les registres fournis mais non consommés par les fragments déclarés dans le `summary.json`.

## Ressources complémentaires

Les fichiers `.asm`, `.bin` et `summary.json` générés constituent des points de départ pour brancher vos propres analyses, visualisations ou pipelines d'exécution.
