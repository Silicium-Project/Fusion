# raytracer (`silicium-raytracer`)

Moteur de rendu natif, **utilisé en production** par tous les nœuds de calcul.
Rendu déterministe (sphères, plans, lumières ponctuelles, réflexions récursives,
ombres, reflets de Phong), parallélisé par lignes.

## Utilisation

```bash
silicium-raytracer <scene.cfg> --output <rendu.ppm> \
  [--x-start N --x-end N --y-start N --y-end N] \
  [--threads N] [--progress-file progress.json]
```

- Sortie : PPM binaire (P6).
- `--x-*` / `--y-*` : ne rend qu'une tuile rectangulaire.
- `--threads` ou `SILICIUM_RAYTRACER_THREADS` : nombre de threads (défaut : nombre
  de CPU logiques).
- Scène d'exemple : `workloads/raytracer/examples/demo-scene.cfg`.

Le déterminisme est une exigence : deux nœuds doivent produire les mêmes octets
pour qu'une vérification par un autre pair fonctionne.

## Organisation du code

La crate fournit une bibliothèque (`silicium_raytracer`) et le binaire
`silicium-raytracer` qui l'utilise.

| Fichier | Contenu |
| --- | --- |
| `src/lib.rs` | Constantes (`EPSILON`, `MAX_DEPTH`) et liste des modules |
| `src/math.rs` | `Vec3`, `Ray` |
| `src/scene.rs` | `Scene`, `Primitive`, `Material`, `Light`, intersections |
| `src/parser.rs` | Lecture des fichiers `.cfg` |
| `src/trace.rs` | Lancer de rayons (ombres, Phong, réflexions) |
| `src/render.rs` | `RenderOptions`, rendu multi-thread d'une tuile, progression |
| `src/pipeline/` | Chaîne des tuiles : `tiles` (découpage centre → bords), `milestones` (engagement par blocs de lignes), `sampling` (vérification probabiliste), `reassemble`, `png`, `ppm` |
| `src/main.rs`, `src/commands.rs` | Binaire : rendu, ou une étape de la chaîne (sortie JSON) |

## Étapes de la chaîne (binaire)

```bash
silicium-raytracer split scene.cfg [--fragments N] [--target-pixels N] [--max-fragments N] [--output plan.json]
silicium-raytracer milestones tuile.ppm --x-start X --y-start Y [--batch-rows 20]
silicium-raytracer verify tuile.ppm --manifest jalons.json --seed S [--reputation 50]   # code 2 si échec
silicium-raytracer reassemble --fragment a.ppm --x-start 0 --y-start 0 --fragment b.ppm ... --output rendu.ppm [--png rendu.png]
silicium-raytracer validate tuile.ppm [--width W] [--height H] [--expected-hash H]
```

`split` et `reassemble` sont la **seule** implémentation du découpage et du
réassemblage : l'orchestrateur (`workloads/raytracer/run_network_job.py`) les
appelle via `SILICIUM_PIPELINE_BIN`, et le déploiement construit le binaire
(`Fusion/deploy/compose/deploy.sh`). Les autres étapes donnent exactement les
résultats du code Python encore utilisé par les nœuds (mêmes hash de jalons et
d'engagement, mêmes erreurs PPM, même validation de fragment).

Les tests `tests/python_parity.rs` lisent `tests/fixtures/python_parity.json`,
régénéré par `python3 tools/dev/quality/raytracer_parity_fixtures.py`. Les cas
de découpage, d'estimation et de réassemblage y sont figés (le code Python qui
les produisait a été supprimé).

## Construire et tester

```bash
cargo build --release -p silicium-raytracer   # binaire dans Network/target/release/
cargo test -p silicium-raytracer
```

L'app desktop (`Fusion/apps/silicium-node/scripts/prepare-runtime*`) construit ce
binaire et l'installe dans `Network/bin/raytracer/`.

## Évolution prévue

Passer aussi en Rust la vérification des fragments et des jalons côté
orchestrateur, puis brancher la chaîne dans le nœud Rust ; les fonctions Python
correspondantes de `workloads/raytracer/` seront alors supprimées. Les reçus
signés (`tools/receipt_verification.py`) restent à porter.
