# Calcul · ML inference

- **Objectif** : produire des embeddings ou labels pour un lot de données en utilisant un modèle fourni (ONNX, ggml, safetensors…).
- **Entrées** : `model.bin`, `batch.json`, options (`dtype`, `device`).
- **Sorties** : `embeddings.json` + `embeddings.hash`.
- **Vérification** : `verification/hash-audit` (intégrité) + `verification/statistical-consistency` (resampling sur un sous-ensemble aléatoire).
