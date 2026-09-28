# Workload `calcul/rendering/raytracer-fragment`

Rendu d'une tuile d'une scène `.cfg` par le raytracer natif
(`crates/raytracer`, binaire `silicium-raytracer`).

- **Entrée** : la scène (référence P2P `scene_p2p_ref`) et la spécification du
  fragment (`x_start`, `x_end`, `y_start`, `y_end`, `verification_batch_rows`).
- **Sortie** : la tuile en PPM (P6), publiée sur le réseau, et le manifeste des
  jalons de vérification (hash des pixels par bloc de lignes).
- **Exécution sur un nœud** : `workloads.raytracer.node_tasks:compute_fragment`.
- **Orchestration d'un job complet** (découpage, vérification, réassemblage) :
  `workloads/raytracer/run_network_job.py`.
- **Vérification** : `verification/rendering/raytracer-fragment`.
