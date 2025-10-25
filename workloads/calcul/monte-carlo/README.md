# Calcul · Monte Carlo intensif

- **Objectif** : lancer des simulations Monte Carlo haut volume (10⁶ à 10⁹ itérations) pour des besoins scientifiques ou financiers.
- **Entrées** : `mc_config.json` (seed global, taille de batch, fonctions d'intérêt) + `chunk_id`.
- **Sorties** : `chunk_<id>.json` (estimations, intervalles de confiance) + `chunk_<id>.hash`.
- **Exigences** : CPU vectorisé, possibilité d'utiliser GPU CUDA/OpenCL.  
- **Vérification** : profil `verification/statistical-consistency` (rejeu sur un sous-ensemble) + `verification/hash-audit` pour l'intégrité.

Commande type :

```bash
python montecarlo.py \
  --seed ${SEED} \
  --iterations ${ITERATIONS} \
  --observable payoff \
  --out chunk_${CHUNK_ID}.json
sha256sum chunk_${CHUNK_ID}.json > chunk_${CHUNK_ID}.hash
```
