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
  items, canaries?}` ; `canaries` = exemples publics du modèle (voir § 4.2) ; `items` = les `inputs` du schéma de la tâche sur le Hub ; fichiers
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

### 4.1 Peu de rechargements de modèle chez les vérificateurs

- L'éditeur préfère, parmi les offres de vérification, un nœud qui a calculé
  un autre fragment du même travail : il a déjà le modèle chargé
  (`publisher/mod.rs`, `job_workers`).
- Un vérificateur qui n'a pas les fichiers du modèle attend
  `SILICIUM_COLD_VERIFY_GRACE_SECS` (60 s par défaut) plus un délai propre
  (0 à la même durée, tiré de son id et de la tâche) avant de le télécharger,
  et seulement s'il manque encore des vérificateurs (`verifier.rs`,
  `Workload::is_warm`). Les nœuds sans le modèle ne le téléchargent donc pas
  tous pour quelques éléments.
- Le runtime garde les 2 derniers modèles en mémoire
  (`SILICIUM_AI_MAX_LOADED`).

### 4.2 Canaris (« exercices corrigés ») et réputation

- Le BackEnd convertit à l'admission les exemples `widgetData` du modèle en
  éléments de la tâche (fichiers téléchargés seulement depuis le Hub, 2 Mo
  au plus, 4 exemples au plus) et les ajoute à chaque demande (`canaries`).
- L'éditeur les mélange aux éléments de l'utilisateur à des places tirées au
  hasard (1 pour 32 éléments, au moins 1, 16 au plus) ; seul lui connaît le
  plan (`<data>/ai/hf/canaries/plans/<sha256 du lot>.json`), jamais partagé.
- **Apprentissage** : une fois un fragment finalisé, la réponse à un canari
  devient sa référence si un vérificateur indépendant a refait cet élément
  précis (l'échantillon vient de son acceptation, l'éditeur le recalcule) et
  approuvé. Référence par modèle, paramètres et entrée.
- **Contrôle** : dès qu'un résultat est publié, l'éditeur compare les
  canaris qui ont une référence (métrique de la tâche) ; une réponse fausse
  est rejetée par l'éditeur lui-même (il s'accepte comme vérificateur et
  publie un verdict négatif) : la tentative échoue, un autre worker reprend
  le fragment, et la réputation du worker baisse (tentatives échouées dans
  le registre des tâches, qui classe les offres).
- **Assemblage** : les réponses aux canaris sont retirées, les éléments de
  l'utilisateur renumérotés à partir de 0.
- Limite : les exemples sont publics ; un tricheur qui les connaît peut y
  répondre juste. Ils s'ajoutent aux échantillons des vérificateurs, ils ne
  les remplacent pas.

## 5. Runtime IA

`apps/silicium-ai-runtime` (Fusion) : serveur local sur `127.0.0.1:11436`
(`SILICIUM_AI_RUNTIME_URL` pour le nœud, `SILICIUM_AI_RUNTIME_TOKEN`
optionnel). Hors ligne, sans réseau sortant, sans code venant des modèles,
seulement les dossiers du nœud. Voir son `README.md`.

Sans `SILICIUM_AI_RUNTIME_URL`, ou si le runtime ne répond pas ou ne fait pas
la tâche, le nœud ne prend ni ne vérifie ces tâches.

## 6. Fichiers des modèles : Hub, pairs, quarantaine

- Chaque fichier épinglé vient du Hub ou des pairs qui l'ont, dans l'ordre
  de `SILICIUM_AI_MODEL_SOURCES` (`hub,peers` par défaut ; `peers,hub`
  ménage le Hub ; `hub` ou `peers` seuls).
- **Partage entre pairs** (`src/model_share.rs`) : un nœud annonce chaque
  fichier de son magasin de modèles dans la DHT
  (`silicium/models/v1/<sha256>` ou `…/git-<sha1>`, au démarrage, après une
  préparation, puis toutes les 30 min) et le sert par morceaux de 4 Mio
  (`/silicium/model/1`, 4 morceaux en vol). Celui qui le reçoit l'écrit à
  côté, vérifie taille et hash épinglés, puis seulement le range ; sinon il
  essaie le pair suivant (8 au plus : détenteurs de la DHT, puis pairs
  connectés). Un pair ne sert que des noms du magasin, jamais un chemin.
- **Quarantaine** : un fichier envoyé par le Hub qui n'est pas celui épinglé
  (autre taille ou autre hash) n'est jamais gardé ; le nœud cite le modèle
  dans `capacity.ai_model_faults` de son battement de cœur. Le BackEnd met
  le modèle en quarantaine dès que 2 nœuds différents le signalent
  (`internal/catalog/faults.go`, toutes les minutes), en plus de sa propre
  relecture de l'arbre du Hub.

## 7. Modèles « chauds »

Un modèle dont les fichiers sont sur le nœud est annoncé dans son profil
(`capacity.ai_models` du battement de cœur, visible dans `GET /v1/peers`). Le
BackEnd s'en servira pour le prix (moins cher quand assez de travailleurs ont
déjà le modèle). Au démarrage, le nœud retrouve les modèles préparés
(`.silicium-ready` dans le dossier du modèle).

## 8. Tests

- `cargo test -p p2p_node workload::hf` : fiche (vecteur commun avec le
  BackEnd, règles), métriques, et un travail complet avec un faux runtime et
  un faux Hub (préparation, calcul, vérification qui refuse des réponses
  modifiées, assemblage) ; un modèle dont les fichiers ne correspondent pas
  n'est jamais prêt.
- `cargo test -p silicium-embedding pinned` : téléchargement et contrôle des
  fichiers épinglés (SHA-256 et hash git), fichier faux du Hub reconnu, copie
  d'un pair vérifiée avant d'être gardée.
- `cargo test -p p2p_node model_share` : un fichier de plusieurs morceaux
  transmis entre deux vrais swarms, une copie au mauvais hash refusée.
- `cargo test -p p2p_node canar` : canaris mélangés, appris, contrôlés,
  retirés ; `publisher` : rejet par l'éditeur lui-même, préférence pour un
  worker du même travail ; `verifier` : délai du vérificateur sans modèle.
- `apps/silicium-ai-runtime` : `python -m pytest -q` (petits modèles locaux).

Pas encore testé : un vrai modèle du Hub de bout en bout sur deux machines.
