# compute-daemon (`compute_daemon`)

Service HTTP local qui calcule et vérifie des tuiles de raytracer pour le nœud.
La logique des tuiles (PPM, jalons, vérification) vient de la bibliothèque
`silicium_raytracer::pipeline`.

## Configuration

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SILICIUM_COMPUTE_BIND` | `127.0.0.1:9090` | Adresse d'écoute ; hors loopback, le jeton est obligatoire |
| `SILICIUM_RAYTRACER_BIN` | — | Binaire `silicium-raytracer` (obligatoire pour `/compute`) |
| `SILICIUM_COMPUTE_ROOT` | `$SILICIUM_DATA_DIR/work`, sinon `./work` | Dossier de travail : tous les chemins des requêtes sont relatifs à lui |
| `SILICIUM_COMPUTE_TIMEOUT_S` | `300` | Timeout du rendu (le processus est tué au-delà) |
| `SILICIUM_COMPUTE_TOKEN` | — | Jeton `Authorization: Bearer` exigé par `/compute` et `/verify` |

## API

| Méthode | Route | Corps | Réponse |
| --- | --- | --- | --- |
| `GET` | `/health` | — | `{"status":"ok"}` |
| `POST` | `/compute` | `scene_path`, `output_path` (relatifs), `x_start`/`x_end`/`y_start`/`y_end`, `batch_rows` optionnels | `status`, `hash` (SHA-256 des pixels), `width`, `height`, `milestones` (engagement de jalons), `error` |
| `POST` | `/verify` | `ppm_path` (relatif), `manifest` (jalons), `seed`, `reputation` | `verified`, taux d'échantillonnage, jalons en échec |

La vérification est probabiliste : le taux d'échantillonnage des jalons baisse
avec la réputation (100 % à 0, 20 % à 100) ; un échec demande une vérification
complète (`escalated_to_full`).

Un chemin absolu, avec `..` ou un lecteur Windows est refusé.

## Tests

```bash
cargo test -p compute_daemon
```

## Limites connues

- Le PPM de sortie est relu en entier en mémoire.
