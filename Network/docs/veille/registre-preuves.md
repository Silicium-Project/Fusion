# Registre des preuves internes

Ce registre permet de retrouver rapidement les artefacts à ouvrir pendant une
revue ou une soutenance. Les chemins sont relatifs au dossier `Network/`.

| Affirmation démontrée | Artefact vérifiable | Nature de la preuve |
| --- | --- | --- |
| Silicium interagit avec un programme Anchor et expose une interface SDK | `solana-layer/docs/solanaLayer_complete_with_storage.md`, `solana-layer/silicium-sdk/SILICIUM_SDK_README.md` | Documentation d'architecture et d'intégration |
| Les parcours Solana sont testables sur Devnet | `solana-layer/scripts/devnet_trace_fragments.ts`, `solana-layer/scripts/devnet_compact_trace.ts` | Scripts d'expérimentation et traces |
| La confirmation Devnet a été renforcée par polling HTTP | commit `cff4c13` | Évolution de l'implémentation issue des essais |
| Les traces compactes sont exécutées de façon asynchrone | commit `e4f6713`, tests dans `../Site/BackEnd-main/internal/silicium/runner_test.go` | Implémentation et test automatisé |
| La distribution multinœud utilise des réclamations parallèles bornées | commit `faacf64`, `tools/network_node.py`, `tests/test_network_node.py` | Code et scénarios automatisés |
| La vérification des fragments est indépendante | commit `d19efe1`, `tests/test_network_node.py` | Règle métier couverte par des tests |
| L'équité de traitement du raytracer a été améliorée | commits `e97dd53`, `1cb9e9e` | Itérations sur un cas réel |
| Les performances ont des garde-fous versionnés | `docs/performance-budgets.md`, `docs/performance-budgets.json`, `tools/perf_budget.py` | Protocole, seuils et outil de mesure |
| Les logs structurés transportent la latence et les décisions de routage | `docs/logging-schema.md`, `docs/mcp-connector-spec.md` | Contrat de télémétrie documenté |
| Les limites de plateforme et d'exécution sont connues | `docs/windows-support.md`, documentation des composants | Analyse des contraintes et portabilité |

## Commandes de démonstration

Afficher l'évolution d'une décision :

```bash
git show --stat cff4c13
git show --stat faacf64
git show --stat d19efe1
git show --stat e4f6713
```

Lister les profils de performance :

```bash
python tools/perf_budget.py --list
```

Produire un rapport de performance sans modifier les seuils :

```bash
python tools/perf_budget.py --profile pytest_core_windows --output veille-benchmark.json
```

Le rapport JSON généré doit être archivé avec la date, le hash du commit testé et
les caractéristiques de la machine. Ne pas présenter les seuils budgétaires comme
des résultats mesurés : ce sont des garde-fous, pas des benchmarks historiques.

