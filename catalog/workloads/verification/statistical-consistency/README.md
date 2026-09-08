# Verification · Statistical consistency

- **Objectif** : re-exécuter un sous-ensemble d'une simulation (Monte Carlo, ML inference) pour vérifier que les statistiques globales sont cohérentes.
- **Entrées** : `config.json`, `subset_seed`, résultats déclarés (`chunk.json`).
- **Étapes** :
  1. relancer la simulation pour `k` itérations ;
  2. comparer les moyennes/variances et calculer un z-score ;
  3. produire un verdict (`accept`, `reject`, `suspect`) signé.
