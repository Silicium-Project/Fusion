# Verification · Rendering spot-check

- **Objectif** : re-render quelques frames aléatoires pour confirmer l'exactitude du rendu initial.
- **Entrées** : scène (`scene.blend`), paramètres (`frame_id`, `seed`), image d'origine + hash.
- **Process** :
  1. rerender la frame avec un seed différent ;
  2. calculer la différence en pixel/histogramme ;
  3. produire un rapport signé (accept/recompute).
