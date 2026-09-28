# tools/cli/ — la CLI `silicium`

Implémentation de la commande `./silicium` (le fichier `Network/silicium` n'est
plus qu'un point d'entrée ; `python -m tools.cli` fait la même chose).

**Pourquoi ici et pas dans `tools/dev/` ?** La CLI sert aussi en production :
l'app desktop lance le nœud avec `silicium node start`, et ses scripts de
packaging copient `tools/` **sans** `tools/dev/`. Les commandes purement
développeur (`test`, `check`, `workload …`, `tui`) vivent donc ici aussi ; les
modules qu'elles importent depuis `tools/dev/` sont importés à l'intérieur des
fonctions, jamais au chargement.

| Module | Contenu |
| --- | --- |
| `main.py` | `main()` : TUI par défaut, sinon exécution de la commande |
| `registry.py` | Arbre des commandes (`build_registry`) et parseur argparse |
| `framework.py` | `CommandSpec`, `CommandGroup`, `CommandRegistry`, journal structuré JSONL par exécution |
| `context.py` | `EnvConfig`, `Context`, réglages MCP |
| `constants.py` | Chemins, valeurs par défaut, listes de choix |
| `proc.py` | `run`, `run_capture`, couleurs, readline optionnel |
| `docker.py` | Santé Docker, WSL, `docker compose` |
| `interactive.py` | Shell interactif (`silicium shell`), complétion |
| `commands/checks.py` | `test`, `check`, `doctor`, `smoke`, `budget`, `clean` |
| `commands/services.py` | `setup`, `start`, `stop`, `status`, `logs`, `exec`, `alias`, `history` |
| `commands/ledger.py` | `ledger list/wipe/export/import` |
| `commands/mcp.py` | `mcp serve`, `mcp print-config` |
| `commands/tui.py` | `tui` |
| `node/start.py` | `node start` (nœud Python, ou `p2p_node` expérimental) |
| `node/api.py` | `node submit-*`, `node get-*`, Solana, jobs |
| `workload/manifest.py` | Lecture des manifestes, filtres, presets |
| `workload/commands.py` | `workload list/show/queue` |
| `workload/lint.py` | `workload lint`, `workload fixtures` |
| `workload/golden.py` | `workload alignment`, `workload golden` |

Chaque module importe explicitement ce qu'il utilise. Pour remplacer une
fonction dans un test, il faut la remplacer dans le module qui l'appelle ;
`tests/test_silicium_test_cli.py` fournit `cli.patch(...)`, qui la remplace
dans tous les modules de la CLI.
