# Verification · Hash audit

- **Objectif** : vérifier l'intégrité d'un artefact produit par un calcul.
- **Entrées** : artefact (`segment.mp4`, `result.json`, etc.) + hash attendu + métadonnées (taille, codec).
- **Tâches** :
  1. recalculer l'empreinte (SHA-256 ou BLAKE3) ;
  2. vérifier la cohérence des métadonnées (FFprobe, JSON schema) ;
  3. produire un rapport signé.

Tous les nodes sauf les producteurs initiaux peuvent exécuter cette vérification.
