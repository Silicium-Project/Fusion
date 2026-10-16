# llm (`silicium-llm`)

Le « Traitement par IA » de Silicium, hors plomberie réseau : une consigne
appliquée par un modèle de langue épinglé, exécuté par Ollama chez les
workers, à chaque élément d'une liste.

Le nœud (`p2p_node`, workload `ai/llm/qwen2.5-1.5b-instruct`) et le binaire
`silicium-llm` utilisent exactement ce code : même prompt, mêmes options,
mêmes contrôles.

Conception détaillée (formats, vérification, sécurité, exploitation) :
[`docs/architecture/llm-workload.md`](../../docs/architecture/llm-workload.md).

## Modules

| Module | Rôle |
| --- | --- |
| `model` | Modèle épinglé (dépôt, commit, SHA-256 du GGUF), nom dans Ollama, options de décodage (glouton) |
| `request` | Demande du site (`silicium-llm-request/1`), limites, nettoyage des textes (NFC, contrôle, jetons spéciaux) |
| `batch` | Lot canonique (`silicium-llm-batch/1`) et découpage en fragments d'éléments entiers |
| `prompt` | Prompt ChatML exact (mode `raw` d'Ollama), schéma JSON des sorties contraintes, lecture d'une réponse |
| `answers` | Réponses d'un fragment (`silicium-llm-answers/1`) et leurs contrôles |
| `similarity` | Similarité de deux réponses (ROUGE-L, égalité des catégories), taille d'échantillon, seuils de vérification |
| `result` | Assemblage : `answers.jsonl`, `answers.csv`, `result.json` |
| `ollama` | Client HTTP d'Ollama : version, présence du modèle, import du GGUF, génération |
| `compute` | Réponse à un élément (workers et vérificateurs) |
| `testing` | Faux Ollama (fonctionnalité `test-ollama`, jamais dans une release) |

## Ligne de commande

```bash
silicium-llm prepare request.json batch.jsonl           # vérifie une demande, écrit son lot
silicium-llm run batch.jsonl answers.jsonl \
  --ollama http://127.0.0.1:11434 --gguf qwen2.5-1.5b-instruct-q4_k_m.gguf
silicium-llm compare batch.jsonl a.jsonl b.jsonl        # calibrage de la vérification
silicium-llm fake-ollama --bind 127.0.0.1:11435         # avec --features test-ollama
```

Le GGUF se télécharge depuis
`https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/91cad51170dc346986eccefdc2dd33a9da36ead9/qwen2.5-1.5b-instruct-q4_k_m.gguf`
(SHA-256 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`).

## Tests

```bash
cargo test -p silicium-llm
```
