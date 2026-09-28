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

## Construire et tester

```bash
cargo build --release --manifest-path crates/raytracer/Cargo.toml
cargo test --manifest-path crates/raytracer/Cargo.toml
```

L'app desktop (`Fusion/apps/silicium-node/scripts/prepare-runtime*`) construit ce
binaire et l'installe dans `Network/bin/raytracer/`.

## Évolution prévue

Devenir aussi une bibliothèque (découpage en tuiles, hash des jalons,
vérification, réassemblage, PNG) pour remplacer `workloads/raytracer/*.py`.
`src/main.rs` (~670 lignes) sera alors découpé en modules.
