# Test de charge multi-instances

`tools/load_test.py` démarre le chemin de production complet : un scheduler
`network_node.py`, un serveur MCP, puis une instance conteneurisée par worker.
Les workers s’enregistrent sur le scheduler, réclament les tâches avec des
requêtes signées groupées, exécutent des workloads CPU intégrés et renvoient le
résultat au scheduler par `/results/dispatch`.

Le test nominal demandé (plusieurs dizaines d’instances) est :

```bash
cd Network
python3 tools/load_test.py --workers 32 --tasks 256 --batch-size 4 \
  --report .silicium/load-tests/32-workers.json
```

Progression recommandée :

```bash
python3 tools/load_test.py --workers 8  --tasks 64  --batch-size 4
python3 tools/load_test.py --workers 16 --tasks 128 --batch-size 4
python3 tools/load_test.py --workers 32 --tasks 256 --batch-size 4
python3 tools/load_test.py --workers 64 --tasks 512 --batch-size 8
```

Qualification de montée en charge sur le profil hétérogène :

```bash
python3 tools/load_test.py --workers 100 --tasks 400 --batch-size 8 \
  --report .silicium/load-tests/100-workers.json
python3 tools/load_test.py --workers 300 --tasks 1200 --batch-size 8 --no-build \
  --report .silicium/load-tests/300-workers.json
```

Le profil crée des workers `compute`, `verify`, `storage`, `audit` et
`resource` avec des combinaisons réalistes. Les workloads synthétiques sont
affectés aux rôles calculables (`compute`/`verify`) ; les autres profils sont
néanmoins soumis à la pression d'inscription, de heartbeat, de gossip et de
sélection de pairs.

Le rapport JSON contient les tâches terminées/échouées, le débit, les
latences p50/p95, la répartition par worker, les métriques P2P et le nombre de
claims groupés. `--keep` conserve le projet Compose pour diagnostiquer les
logs (`docker compose ... logs`). `--no-build` réutilise une image déjà
construite.

Le profil du harnais borne aussi la concurrence HTTP du scheduler/workers et
le fan-out d'anti-entropie (`16`/`8` par défaut dans un nœud, `64`/`8` dans le
profil de charge) afin que le maillage ne dérive pas en tempête O(N²).

Ce test mesure des instances conteneurisées isolées. Pour une qualification
VPS/VM, on réutilise les mêmes paramètres sur plusieurs hôtes et on compare
ensuite les rapports ; les résultats d’un seul worker ne servent pas de
benchmark réseau.
