# Workloads catalogue

Ce dossier (`catalog/workloads`) centralise les profils officiels distribués aux calculateurs et vérificateurs.

Le réseau Silicium distingue désormais **deux familles** de profils :

1. `calcul/` – tâches qui produisent une valeur (encodage, simulation, rendu, etc.).
2. `verification/` – tâches indépendantes qui valident les résultats des calculs correspondants (hash re-check, recomputation ponctuelle, analyses statistiques).

Chaque profil est versionné dans son propre sous-dossier et contient :

| Fichier | Rôle |
| --- | --- |
| `manifest.yaml` | Contrat machine-lisible (nom, version, exigences CPU/GPU/RAM, commande à exécuter, artefacts attendus). |
| `README.md` | Contexte fonctionnel, format des entrées/sorties, méthodes de certification, métriques de paiement. |
| `examples/` *(optionnel)* | Jeux de données ou scripts pour tester localement. |

## Manifest schema (aperçu)

```yaml
schema_version: 1
id: calcul/video-encoding/h264
version: 0.1.0
engine: container
command: ffmpeg -i {input} -c:v libx264 -preset slow {output}
resources:
  cpu: 4
  gpu: optional
  memory: 4Gi
taxonomy:
  category: calcul
  domain: video
  complexity: high
  resource_profile: gpu_optional
  determinism: deterministic
  tags:
    - transcoding
    - cpu
    - deterministic
validation:
  hash: sha256
  redundancy: quorum
payment:
  unit: fragment
  estimated_cost: 0.001 # en token Silicium
```

Schéma de référence versionné:

- `catalog/workloads/schema/workload-manifest-v1.schema.json`
- `schema_version: 1` est obligatoire dans chaque `manifest.yaml`

Les devices téléchargent le manifest correspondant au job pour savoir quel binaire lancer et comment reporter la preuve (hash, logs, temps).

## Profils disponibles

### calcul/

- `video-encoding/` : transcodage H.264/H.265/AV1 en fragments.
- `math-simulation/` : tâches scientifiques génériques.
- `monte-carlo/` : versions lourdes à haute itération pour seeding massif.
- `ml-inference/` : embeddings, classification de lots.
- `rendering/` : frames Blender/3D.
- `data-compression/` : archivage et hashing segmenté.
- `libm/` : micro-profils mathématiques (`sin/`, `exp/`, ... ) utilisés pour
  résoudre les dépendances externes des fragments ASM.

### verification/

- `hash-audit/` : recalcul des empreintes SHA/BLAKE et vérification des métadonnées.
- `statistical-consistency/` : reproduction partielle d’une simulation Monte Carlo, calcul de z-scores.
- `rendering-spotcheck/` : rerender de frames aléatoires et comparaison pixel/histogramme.

Ajoutez un profil en créant un sous-dossier dans la famille adaptée, puis fournissez `manifest.yaml` + `README.md`. Les manifests texte servent de base à ce qui sera sérialisé/signé côté blockchain avant d’être envoyé dynamiquement aux devices.

## Taxonomy vocabulary (v1)

Required fields under `taxonomy`:

- `category`: `calcul` | `verification`
- `domain`: `compression` | `integrity` | `math` | `ml` | `rendering` | `simulation` | `statistics` | `video`
- `complexity`: `low` | `medium` | `high`
- `resource_profile`: `cpu_light` | `cpu_heavy` | `gpu_optional` | `gpu_required` | `memory_light` | `memory_heavy`
- `determinism`: `deterministic` | `bounded_stochastic` | `stochastic`
- `tags`: approved tag list from the v1 schema (`workload-manifest-v1.schema.json`)

CLI selection filters:

- `./silicium workload list --category calcul --domain rendering`
- `./silicium workload list --determinism stochastic --tag monte_carlo`
- `./silicium workload show calcul/libm/sin --domain math --tag libm`
