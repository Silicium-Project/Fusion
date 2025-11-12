# Worker

Ce module simule un **worker** capable d'exécuter localement des fragments
produits par `splitter`. Il réutilise directement `fragment::FragmentExecutor`
et expose une CLI simple pour consommer une file de tâches ou exécuter un
fragment précis.

## Compilation

```bash
cd tools/worker
make
```

Le binaire `worker` est généré dans ce dossier. Il accepte les options
suivantes :

```
worker --summary <summary.json> --task <partition_id> [--input reg=val ...] [--native]
worker --summary <summary.json> --queue queue.txt [--output json]
```

- `--summary` : chemin vers le `summary.json` produit par `splitter`.
- `--task` : identifier d’un fragment à exécuter (répétable).
- `--queue` : fichier texte contenant une tâche par ligne
  (`partition reg=val ...`), commentaires via `#`.
- `--input` : valeurs par défaut pour les tâches ajoutées via `--task`.
- `--native` : active le mode natif (dangereux, mappe les `.bin` en mémoire).
- `--output` : `text` (défaut) ou `json`.
- `--log` : capture la sortie standard détectée (`puts`/`printf`) dans un
  fichier unique.
- `--reset-state` : force la réinitialisation des registres/mémoire entre chaque
  tâche (par défaut le worker conserve l'état, ce qui permet à un fragment de
  relire les écritures mémoire/régistres des précédents). Même lorsque les
  fragments sont exécutés de manière détachée, le worker reconstruit la mémoire
  en réappliquant uniquement les zones modifiées (diffs capturés dans
  `memory_patches`), ce qui évite de transporter toute la RAM.

Exemple de file :

```
# partition  registre=valeur
func_0_deregister_tm_clones
func_3_main rax=0x1337
```

## Tests unitaires

```bash
make test
```

Les tests réutilisent l'image Docker `silicium/cpp-tests` (buildée pour
`splitter`/`fragment-executor`) et montent un cache `ccache` partagé dans
`.cache/cpp-tests/ccache`. La première compilation prend ~15 s, puis les
relances se font en moins d'une seconde tant que les sources n'ont pas changé.
