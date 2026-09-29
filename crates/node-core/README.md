# node-core (`silicium_node_core`)

Bibliothèque partagée par les nœuds : elle ne fait aucune entrée/sortie réseau
elle-même.

## Modules

| Module | Contenu |
| --- | --- |
| `p2p` | `TaskEnvelope`, `DhtRecordEnvelope` : ce qui circule entre pairs (tâches, enregistrements DHT) |
| `taskbook` | Journal d'événements de tâches signé Ed25519, chaîné par auteur, avec détection de trous et de forks |
| `dag` | Graphe de dépendances entre tâches |
| `dispatch` | Sélection d'un nœud pour une tâche (échantillonnage de Thompson) |
| `beta` | Postérieure Beta utilisée pour la réputation / l'affinité |
| `affinity` | Clé et enregistrement d'affinité matériel ↔ tâche |
| `hardware` | Profil matériel du nœud (`HardwareBucket`) |
| `runtime` | Exécution d'une tâche en WASM (feature `runtime-wasm`) ou en conteneur OCI (Docker) |
| `sandbox` | Chemins confinés dans un dossier du nœud (`resolve`, `safe_component`) |

## Features

- `runtime-wasm` (désactivée par défaut) : active `wasmtime` pour exécuter des
  modules WASM.

## Tests

```bash
cargo test -p silicium_node_core
cargo test -p silicium_node_core --features runtime-wasm
```

## Limites connues

- `p2p::TaskEnvelope::runtime_envelope` fait confiance aux champs runtime : ne
  l'appeler que sur une tâche locale ou passée par
  `TaskEnvelope::sanitize_remote` (qui refuse les images OCI, retire dossier de
  travail et environnement, et confine les chemins).
