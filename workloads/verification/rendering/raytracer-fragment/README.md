# Workload `verification/rendering/raytracer-fragment`

Vérification probabiliste d'un fragment rendu par
`calcul/rendering/raytracer-fragment` : le vérificateur re-rend un jalon tiré
au hasard (un bloc de lignes de la tuile) et compare le hash de ses pixels à
celui annoncé par le calculateur.

- **Entrée** : la scène (`scene_p2p_ref`) et le défi JSON (`strategy`,
  `milestone`, `commitment_hash`, `challenge_nonce`). Si `source_output_ref`
  est fourni, le fragment d'origine est récupéré et son engagement contrôlé.
- **Stratégies** : `random-row-milestone-v1`, `random-tile-row-milestone-v2`.
- **Exécution sur un nœud** :
  `workloads.raytracer.node_tasks:verify_fragment_milestone`.
