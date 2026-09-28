# compute-daemon (`compute_daemon`)

Service HTTP local qui calcule et vérifie des tuiles de raytracer pour le nœud.
Écoute sur `127.0.0.1:9090` (adresse fixe dans le code).

## Configuration

| Variable | Rôle |
| --- | --- |
| `SILICIUM_RAYTRACER_BIN` | Chemin du binaire `silicium-raytracer` (obligatoire) |

## API

| Méthode | Route | Corps | Réponse |
| --- | --- | --- | --- |
| `GET` | `/health` | — | `{"status":"ok"}` |
| `POST` | `/compute` | `scene_path`, `output_path`, `x_start`/`x_end`/`y_start`/`y_end` optionnels | `status`, `hash` (SHA-256 des pixels du PPM), `error` |
| `POST` | `/verify` | `ppm_path`, `manifest` (jalons + hash attendus), `seed`, `reputation` | `verified`, taux d'échantillonnage, jalons en échec |

La vérification est probabiliste : le taux d'échantillonnage des jalons baisse
avec la réputation (100 % à 0, 20 % à 100) et passe à une vérification complète
en cas d'échec.

## Tests

```bash
cargo test --manifest-path crates/compute-daemon/Cargo.toml
```

## Limites connues

- Chemins de fichiers acceptés tels quels depuis la requête.
- Pas de timeout sur le processus du raytracer, pas d'authentification.
- Pas de `Cargo.lock` versionné.
