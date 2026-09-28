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
| `src/main.rs` | Binaire : arguments, écriture du PPM |

## Construire et tester

```bash
cargo build --release -p silicium-raytracer   # binaire dans Network/target/release/
cargo test -p silicium-raytracer
```

L'app desktop (`Fusion/apps/silicium-node/scripts/prepare-runtime*`) construit ce
binaire et l'installe dans `Network/bin/raytracer/`.

## Évolution prévue

Ajouter à la bibliothèque le découpage en tuiles, le hash des jalons, la
vérification, le réassemblage et l'export PNG, pour remplacer
`workloads/raytracer/*.py`.
