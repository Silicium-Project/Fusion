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

Chaque étape donne exactement les résultats de `workloads/raytracer/raytracer_workload.py`
(même plan de tuiles, mêmes hash de jalons et d'engagement, même image
réassemblée ; le PNG contient les mêmes pixels, la compression peut différer).
Les tests `tests/python_parity.rs` lisent `tests/fixtures/python_parity.json`,
régénéré par `python3 tools/dev/quality/raytracer_parity_fixtures.py`.

## Construire et tester

```bash
cargo build --release -p silicium-raytracer   # binaire dans Network/target/release/
cargo test -p silicium-raytracer
```

L'app desktop (`Fusion/apps/silicium-node/scripts/prepare-runtime*`) construit ce
binaire et l'installe dans `Network/bin/raytracer/`.

## Évolution prévue

Brancher cette chaîne dans le nœud Rust (découpage et réassemblage côté
émetteur) ; la copie Python de `workloads/raytracer/` sera alors supprimée.
Les reçus signés (`tools/receipt_verification.py`) restent à porter.
