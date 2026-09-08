# Calcul · Data compression

- **Objectif** : compresser/archiver des lots (CSV, images, code) avec `tar + zstd` ou équivalent.
- **Entrées** : dossier à traiter + paramètres (`level`, `chunk_id`).
- **Sorties** : archive compressée + hash.
- **Vérification** : `verification/hash-audit` (recalcul hash) + possibilité de décompression aléatoire (`verification/statistical-consistency` pour vérifier l'intégrité partielle).
