# Catalogue IA (workloads `ai/hf/…`)

Une tâche du Hub Hugging Face (classer des textes, traduire, transcrire de
l'audio, détecter des objets…) appliquée à chaque élément d'une liste, par un
modèle choisi dans le catalogue. Le code connaît les tâches, jamais un
modèle : le modèle arrive avec le travail, sous forme d'une fiche figée.

| | |
| --- | --- |
| Workloads | `ai/hf/<tâche>/<clé du modèle>` (un par modèle) |
| Code | Network : `crates/p2p-node/src/workload/hf/` (réseau), `crates/embedding/src/model/store/pinned.rs` (fichiers épinglés) ; BackEnd : `internal/catalog` (catalogue, fiches) ; Fusion : `apps/silicium-ai-runtime` (runtime IA) |
| État | Dev, étape 1 du plan du catalogue. Testé avec un faux runtime et un faux Hub (nœud) et avec de petits modèles locaux (runtime) |

Les workloads existants ne changent pas : `ai/llm/…` (traitement par IA,
Ollama) et `ai/embedding/…` (recherche dans des documents) gardent leurs pages.

## 1. Vue d'ensemble

```
BackEnd catalog ── fiche silicium-model/1 (dépôt, commit, fichiers + empreintes, chargement)
     │
Site ── demande silicium-hf-request/1 {task, model: fiche, parameters, items} ──▶ BackEnd ──▶ nœud éditeur
                                                    1. prépare : vérifie la fiche, lot canonique
                                                    2. découpe en fragments d'éléments entiers
Travailleur : ensure_ready → télécharge les fichiers épinglés (hash) → les range dans
              <data>/ai/hf/models/<clé>/ → le runtime charge le modèle → exécute ses éléments
Vérificateur : refait un échantillon tiré de son acceptation, compare avec la métrique de la tâche
Éditeur : assemble answers.jsonl + result.json
```

## 2. La fiche du modèle (`silicium-model/1`)

Écrite par `internal/catalog` à partir de l'API du Hub. Champs, dans cet ordre :
`format, key, digest, repository, revision, task, library, runtime, loader,
files[{path, size, sha256 | git_oid}], total_bytes, parameters?,
hardware_class, licence, custom_code_declared?`.

- `digest` = SHA-256 du JSON de la fiche avec `key` et `digest` vides, champs
  optionnels vides omis, sans échappement HTML. Le nœud le recalcule
  (`manifest.rs`) : un vecteur de test commun existe des deux côtés
  (`golden_test.go`, `digest_matches_the_backend`).
- `key` = `<owner--name>-<12 premiers caractères du digest>` : un autre commit
  ou un autre fichier est un autre modèle, donc un autre workload.
- Le nœud réapplique les règles : runtime `python`, bibliothèque
  `transformers` / `sentence-transformers` / `timm`, chemins sûrs, ni code
  (`.py`…) ni pickle (`.bin`, `.pt`…), empreintes bien formées, taille
  ≤ `SILICIUM_AI_MAX_MODEL_GB` (24 par défaut).
- Fichiers LFS : SHA-256 du contenu ; petits fichiers : hash git
  (`blob <taille>\0<contenu>`), le seul que le Hub donne.

## 3. Formats

- **Demande** `silicium-hf-request/1` : `{format, task, model, parameters,
  items}` ; `items` = les `inputs` du schéma de la tâche sur le Hub ; fichiers
  en `{"$bytes": "<base64>"}`. ≤ 20 000 éléments, ≤ 8 Mo par élément, 60 Mo
  au total.
- **Lot** `silicium-hf-batch/1` : ligne d'en-tête `{format, task, model,
  parameters, item_count}`, puis une ligne `{"id", "inputs"}` par élément.
  Un fragment = une plage d'octets de lignes entières (16 éléments par défaut,
  `SILICIUM_HF_ITEMS_PER_FRAGMENT`, 128 fragments au plus).
- **Réponses** d'un fragment : une ligne `{"id", "output"}` par élément.
- **Résultat** : `<workload_storage>/hf/<job>/answers/answers.jsonl` et
  `result.json` (`silicium-hf-result/1` : tâche, modèle, `item_count`,
  paramètres).

## 4. Tâches et vérification

19 tâches pour l'étape 1 (celles qui tournent sur un processeur). Un
vérificateur refait un échantillon (3 à 8 éléments) et compare :

| Métrique | Tâches | Seuils (moyenne / chaque élément) |
| --- | --- | --- |
| même étiquette en tête | text-, zero-shot-, image-, zero-shot-image-, audio-classification, fill-mask | 0,66 / — |
| ROUGE-L des mots | translation, summarization, text-generation, image-to-text | 0,6 / 0,2 |
| 1 − WER | automatic-speech-recognition | 0,7 / 0,3 |
| cosinus | feature-extraction, image-feature-extraction | 0,98 / 0,95 |
| écart des scores | sentence-similarity | 0,8 / 0,5 |
| accord des paires | text-ranking | 0,85 / 0,6 |
| F1 (entité, mot) | token-classification | 0,8 / 0,5 |
| F1 des mots de la réponse | question-answering | 0,7 / 0,3 |
| réponse identique | table-question-answering | 0,66 / — |
| F1 des boîtes (même étiquette, IoU ≥ 0,5) | object-detection | 0,7 / 0,3 |

**Seuils provisoires**, à calibrer sur deux vraies machines (CPU et GPU).

## 5. Runtime IA

`apps/silicium-ai-runtime` (Fusion) : serveur local sur `127.0.0.1:11436`
(`SILICIUM_AI_RUNTIME_URL` pour le nœud, `SILICIUM_AI_RUNTIME_TOKEN`
optionnel). Hors ligne, sans réseau sortant, sans code venant des modèles,
seulement les dossiers du nœud. Voir son `README.md`.

Sans `SILICIUM_AI_RUNTIME_URL`, ou si le runtime ne répond pas ou ne fait pas
la tâche, le nœud ne prend ni ne vérifie ces tâches.

## 6. Modèles « chauds »

Un modèle dont les fichiers sont sur le nœud est annoncé dans son profil
(`capacity.ai_models` du battement de cœur, visible dans `GET /v1/peers`). Le
BackEnd s'en servira pour le prix (moins cher quand assez de travailleurs ont
déjà le modèle). Au démarrage, le nœud retrouve les modèles préparés
(`.silicium-ready` dans le dossier du modèle).

## 7. Tests

- `cargo test -p p2p_node workload::hf` : fiche (vecteur commun avec le
  BackEnd, règles), métriques, et un travail complet avec un faux runtime et
  un faux Hub (préparation, calcul, vérification qui refuse des réponses
  modifiées, assemblage) ; un modèle dont les fichiers ne correspondent pas
  n'est jamais prêt.
- `cargo test -p silicium-embedding pinned` : téléchargement et contrôle des
  fichiers épinglés (SHA-256 et hash git).
- `apps/silicium-ai-runtime` : `python -m pytest -q` (petits modèles locaux).

Pas encore testé : un vrai modèle du Hub de bout en bout sur deux machines.
