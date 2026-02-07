# Worker

Ce module simule un **worker** capable d'exécuter localement des fragments
produits par `splitter`. Il réutilise directement `fragment::FragmentExecutor`
et expose une CLI simple pour consommer une file de tâches ou exécuter un
fragment précis.

## Compilation

```bash
cd worker
make
```

Le binaire `worker` est généré dans ce dossier. Il accepte les options
suivantes :

```
worker --summary <summary.json> --task <partition_id> [--input reg=val ...]
worker --summary <summary.json> [--queue queue.txt] [--output json]
       [--mode auto|emu|native|dynamo] [--connector direct|http]
worker --drrun <binaire> [--drrun-arg <arg> ...]
```

- `--summary` : chemin vers le `summary.json` produit par `splitter`.
- `--task` : identifier d’un fragment à exécuter (répétable).
- `--queue` : fichier texte contenant une tâche par ligne
  (`partition reg=val ...`), commentaires via `#`. Si omis et aucun `--task`
  n'est fourni, le worker dérive automatiquement un ordre topologique à partir
  du `summary`.
- `--input` : valeurs par défaut pour les tâches ajoutées via `--task`.
- `--mode` : `auto` (par défaut, priorité Dynamo > natif > ému), `emu` pour
  l'émulation pure, `native` pour exécuter les fragments nativement,
  `dynamo` pour externaliser chaque fragment dans un conteneur DynamoRIO.
- `--connector` : méthode de liaison avec le backend (`direct` par défaut pour
  lancer localement/Docker, `http` pour anticiper un orchestrateur externe).
- `--connector-endpoint` : URL cible lorsque le connecteur HTTP est activé.
- `--runner-binary` / `--runner-launcher` : chemins alternatifs pour le runner
  Dynamo (binaire embarqué ou script de lancement).
- `--output` : `text` (défaut) ou `json`.
- `--log` : capture la sortie standard détectée (`puts`/`printf`) dans un
  fichier unique.
- `--reset-state` : force la réinitialisation des registres/mémoire entre chaque
  tâche (par défaut le worker conserve l'état, ce qui permet à un fragment de
  relire les écritures mémoire/régistres des précédents). Même lorsque les
  fragments sont exécutés de manière détachée, le worker reconstruit la mémoire
  en réappliquant uniquement les zones modifiées (diffs capturés dans
  `memory_patches`), ce qui évite de transporter toute la RAM. Le reporter
  liste ces patchs mémoire (adresse + octets avant/après) pour faciliter le
  débogage.

Si aucune file ni tâche n'est fournie, l'ordre d'exécution est dérivé du
`summary` (topo-sort des dépendances).

## Types de tâches

Le worker supporte désormais plusieurs **types de tâches**. Le binaire reste la
forme la plus générale, mais d'autres types existent pour des checks simples.

Types supportés :
- `binary` (par défaut) : exécute un fragment à partir du `summary.json`.
- `health` (alias `check`) : tâche non-binaire qui renvoie un statut minimal.

### Sélection via queue

Dans un fichier `--queue`, ajoutez `type=...` :

```
func_3_main type=binary rax=0x10
health_check type=health
```

Si `type` est absent, le worker assume `binary`.

## Politique OS des fragments

Le worker peut être configuré pour décider comment traiter les fragments Linux/Windows
en fonction de la plateforme et des préférences d'exécution.

Actions disponibles :
- `native` : exécute localement (si supporté).
- `wsl` : délègue au backend WSL (Windows).
- `skip` : ignore la partition.
- `error` : refuse la partition (échec explicite).
- `queue` : marque la partition comme mise en file.

### Configuration CLI / env

```
--linux-fragments native|wsl|skip|error|queue
--windows-fragments native|wsl|skip|error|queue
```

Variables d’environnement :
```
SILICIUM_LINUX_FRAGMENTS
SILICIUM_WINDOWS_FRAGMENTS
```

## Triggers WSL

Pour activer dynamiquement la délégation WSL, des triggers peuvent être configurés :

```
--wsl-enable / --wsl-disable
--wsl-min-reward <v>
--wsl-min-jobs <n>
--wsl-reward <v>
--wsl-available-jobs <n>
```

Variables d’environnement :
```
SILICIUM_WSL_ENABLE
SILICIUM_WSL_MIN_REWARD
SILICIUM_WSL_MIN_JOBS
SILICIUM_WSL_REWARD
SILICIUM_WSL_AVAILABLE_JOBS
```

La décision (`wsl_enabled` + raison) est exposée dans la télémétrie et les rapports.

### Sélection via JSON

Les payloads JSON (connecteur/runner) acceptent un champ `type` :

```
{
  "type":"health",
  "partition_id":"health_check",
  "asm_path":"",
  "binary_path":"",
  "mode":"emu",
  "fd_redirections":[],
  "inputs":[],
  "register_state":[],
  "memory":[]
}
```

### Télémétrie commune

Tous les rapports incluent maintenant une base commune de télémétrie :
- `task_id`, `type`, `status`
- `started_at_ms`, `finished_at_ms`, `duration_ms`
- `warnings` (liste)

Ces champs sont ajoutés au JSON de sortie du `Reporter` en plus des informations
spécifiques à l'exécution de fragments.

## Tests unitaires

```bash
make test
```

Les tests réutilisent l'image Docker `silicium/cpp-tests` (buildée pour
`splitter`/`fragment-executor`) et montent un cache `ccache` partagé dans
`.cache/cpp-tests/ccache`. La première compilation prend ~15 s, puis les
relances se font en moins d'une seconde tant que les sources n'ont pas changé.

## Exécution complète via DynamoRIO

Pour tester un binaire complet (avec les vrais appels `printf`, `puts`, syscalls,
etc.), il est possible d'utiliser [DynamoRIO](https://dynamorio.org/) directement
depuis le worker :

1. Construire l'image Docker locale (une fois pour toutes) :
   ```bash
   docker build -t dynamorio-runner infra/docker/dynamorio-runner
   ```
2. Lancer un binaire via `drrun` :
   ```bash
   ./worker/worker \
     --drrun ./demo/hello_demo \
     --drrun-arg "--flag=42"
   ```

Le worker exécute alors `drrun -- ./demo/hello_demo ...` à l'intérieur du
conteneur `dynamorio-runner`, capture la sortie standard et relaie toute erreur.
Ce mode ne partitionne pas encore les fragments : il sert à valider rapidement
les appels système/libc réels sans devoir stubber chaque fonction.

### Backend DynamoRIO pour les fragments

Outre l'exécution d'un binaire complet via `--drrun`, le worker peut
désormais déléguer **chaque fragment** à DynamoRIO. Le flux est le suivant :

1. Construire l'image Docker `dynamorio-runner` (si ce n'est pas déjà fait).
   L'image embarque désormais `dynamo_fragment_runner` précompilé (utilisant la
   même glibc/libstdc++ que le conteneur).
2. Lancer le worker avec `--mode dynamo` :

   ```bash
   ./worker/worker \
     --summary demo/worker/summary.json \
     --queue demo/worker/queue.txt \
     --mode dynamo
   ```

Pour chaque tâche, le worker sérialise l'état courant (registres, patchs
mémoires) en JSON, puis lance `drrun -- /opt/dynamo-runner/dynamo_fragment_runner`
dans le conteneur `dynamorio-runner`. Ce runner applique la LUT locale (mêmes
adresses virtuelles reconstruites uniquement à partir des zones modifiées),
exécute le fragment en **mode natif** sous DynamoRIO et renvoie la capture
complète (`ExecutionResult`). L'état est rejoué côté orchestrateur avant la
prochaine tâche, garantissant que les fragments détachés puissent relire les
écritures mémoire/régistres précédentes.

> 💡 Le backend `dynamo` nécessite Docker + l'image `dynamorio-runner`, mais la
> CLI reste identique à celle du mode émulé (`--task`, `--queue`, `--input`, etc.).
> Utilisez `--runner-binary <path>` si vous souhaitez surcharger le binaire
> utilisé à l'intérieur du conteneur (par défaut `/opt/dynamo-runner/dynamo_fragment_runner`).
> `--runner-launcher <path>` permet de remplacer le script d'invocation (par défaut
> `worker/scripts/dynamo_runner.sh`) si vous préférez un autre runtime que Docker.
> Le lanceur Docker active `SYS_PTRACE`, désactive le profil seccomp, monte automatiquement
> le workspace avec `:Z` (re-labellisation SELinux) et, par défaut, passe `-native_exec_managed_code`
> à `drrun` afin d'autoriser l'exécution du code JIT produit par le worker. Ajustez
> `DYNAMO_RUNNER_OPTS` (options `docker run`), `DYNAMO_RUNNER_VOLUME_SPEC` (chemin
> + options du volume, `/workspace:Z` par défaut), `DYNAMO_RUNNER_DRRUN_FLAGS`
> (flags supplémentaires pour `drrun`), `DYNAMO_RUNNER_DRRUN_BIN` (chemin vers `drrun`)
> et `DYNAMO_RUNNER_MODE=native|drrun` (défaut: `native`, mettre `drrun` pour forcer
> l'instrumentation DynamoRIO) si nécessaire.

### Connecteurs modulaires

Le worker agit comme un “connecteur” entre la planification locale et différents
backends d'exécution. Deux modes sont câblés :

1. `--connector direct` (défaut) : exécute les fragments localement (émulateur) ou
   lance `drrun` via Docker pour le backend Dynamo.
2. `--connector http` : délègue l'exécution à un endpoint HTTP qui reçoit un
   payload JSON et renvoie un `ExecutionResult`. Utilisez
   `--connector-endpoint https://localhost:9000/run` pour définir la cible.

Cette abstraction permet d'introduire ultérieurement un “runner” externe sans
changer la logique du worker (sérialisation JSON des registres/mémoires).

### Contrat HTTP (payload)

Requête `POST` (JSON) :

```
{
  "type":"binary",
  "partition_id":"func_main",
  "asm_path":"/path/func_main.asm",
  "binary_path":"/path/func_main.bin",
  "mode":"emu",
  "fd_redirections":[{"fd":1,"capture":true,"input":"","alias":"stdout"}],
  "inputs":["rax=0x1"],
  "register_state":["rbx=0x2"],
  "memory":["0x1000:deadbeef"]
}
```

Réponse `ExecutionResult` :

```
{
  "success":true,
  "error":"",
  "stdout":"ok",
  "stderr":"",
  "fd_outputs":{"1":{"data":"6f6b","alias":"stdout"}},
  "initial_regs":["rax=0x1"],
  "final_regs":["rax=0x2"],
  "memory_patches":["0x1000:beef"],
  "instructions":12,
  "memory_accesses":4
}
```

### Test rapide : lecture sur `stdin`

Pour vérifier que le mode `--drrun` relaie bien l'entrée standard à travers
Docker/DynamoRIO, un petit programme d'exemple est fourni
(`demo/worker/stdin_demo.c`). Compile-le puis pipe du texte :

```bash
gcc -O0 -g demo/worker/stdin_demo.c -o demo/worker/stdin_demo
echo "salut réseau" | ./worker/worker --drrun demo/worker/stdin_demo
```

La sortie attendue ressemble à :

```
Echo stdin: salut réseau
```

Grâce à l'option `-i` passée à `docker run`, l'entrée standard du worker est
redirigée vers le conteneur et jusqu'au binaire instrumenté par DynamoRIO.

## Démo mémoire

Le dossier `demo/worker/` contient deux fragments factices :

- `writer.asm` pousse une valeur sur la pile,
- `reader.asm` la dépile.

Un `summary.json` minimal et une file `queue.txt` sont fournis. Pour tester le
transfert d'état (mémoire + registres) :

```bash
./worker/worker \
  --summary demo/worker/summary.json \
  --queue demo/worker/queue.txt
```

La sortie montre que `reader` récupère bien la valeur écrite par `writer`
grâce au mécanisme de diff mémoire. Ajoutez `--reset-state` si vous souhaitez
revenir à un worker stateless.
