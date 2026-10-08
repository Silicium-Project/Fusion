# Recherche dans mes documents (workload `ai/embedding/…`)

Conception du premier workload d'IA de Silicium : l'utilisateur dépose ses
documents, le réseau calcule un vecteur par passage avec un modèle épinglé,
puis l'utilisateur cherche dans ses passages par le sens de sa question.

| | |
| --- | --- |
| Workload | `ai/embedding/multilingual-e5-small` |
| Code | Network : `crates/embedding` (formats, modèle, recherche), `crates/p2p-node/src/workload/embedding/` (réseau) ; BackEnd : `internal/documents`, `internal/handler/documentJobs.go` ; FrontEnd : `components/jobs/DocumentSearch.vue`, `utils/documents.ts` |
| État | Dev. Testé de bout en bout en local avec un modèle minuscule ; le vrai modèle se teste sur un poste avec accès Internet (voir « Tests ») |

## 1. Ce que voit l'utilisateur

1. **Dépôt.** « Nouveau calcul » → « Recherche dans mes documents ». Il glisse
   des PDF, des fichiers Word (`.docx`), du texte ou du Markdown, ou un ZIP
   (64 Mo au total). Une case à cocher confirme que les machines du réseau
   lisent le texte (le BackEnd la vérifie aussi). Aucun réglage technique.
2. **Lecture.** La page du projet affiche « Lecture de tes documents…
   412 / 1 000 passages lus ».
3. **Recherche.** Une barre « Pose ta question ». Chaque résultat donne le
   passage, les mots proches de la question surlignés, le document et la
   page ; « Ouvrir » affiche le document à cette page. Les fichiers non lus
   sont signalés avec la raison (« image scannée », « format non pris en
   charge »…).
4. **Ajouter des documents.** Les nouveaux documents rejoignent la même
   collection : une recherche porte sur tous les envois de la collection.
5. **Avancé.** Un ZIP de l'index (`index.json`, `vectors.f32`,
   `passages.jsonl`, `LISEZMOI.txt`) pour le réutiliser ailleurs.

## 2. Vue d'ensemble

```
Site ──POST /jobs (files[], acknowledge_sharing)──▶ BackEnd ──ZIP──▶ nœud éditeur (VPS)
                                                                     │ 1. prépare (processus enfant) : documents → corpus
                                                                     │ 2. découpe : fragments de passages entiers
                                                                     ▼
                                              workers (PC) : modèle prêt ? → vecteurs du fragment
                                              vérificateurs : 3 à 8 passages tirés au sort, recalculés
                                                                     │
                                              éditeur : index = corpus + vecteurs (assemblage)
Site ──GET /jobs/{id}/search?q=──▶ BackEnd ──POST /v1/embedding/search──▶ éditeur : vecteur de la question, top k
```

Le trait `Workload` du nœud a gagné deux étapes facultatives, utiles à
d'autres workloads d'IA :

| Étape | Qui | Méthode | Ici |
| --- | --- | --- | --- |
| préparer l'entrée | éditeur | `prepare_input` | documents → corpus, dans un processus enfant |
| se préparer | worker, vérificateur | `ensure_ready` | télécharger et charger le modèle avant de prendre une tâche |

## 3. Formats

### Corpus `silicium-corpus/2` (entrée partagée, JSON Lines)

```
{"format":"silicium-corpus/2","passage_count":3,"documents":[{"name":"contrat.pdf","pages":12,"passages":2},…],"skipped":[{"name":"scan.pdf","reason":"no_text"}]}
{"id":0,"doc":0,"page":1,"section":"Contrat › Article 6 - Résiliation","text":"…"}
{"id":1,"doc":0,"page":2,"text":"…"}
```

- Passages de 150 mots au plus, chevauchement de 30 mots, sans sortir d'une
  page (un passage a toujours sa page). Une fin de moins de 25 mots rejoint
  le passage précédent.
- **Titres** : titres Markdown, styles de titre Word (`Heading 1`, `Titre 2`,
  `Überschrift 3`), lignes courtes du type « Article 6 », « Chapitre II »,
  « § 3 », « 2.1 Durée », ou en MAJUSCULES. Un titre ouvre un nouveau
  passage, et chaque passage garde le chemin des titres qui le contiennent
  (`section`, trois niveaux, séparés par « › », absent sans titre).
- Le modèle vectorise `section` + saut de ligne + texte (sans répéter un
  titre qui ouvre déjà le passage) : un passage qui ne dit pas de quoi il
  parle est retrouvé par le titre de sa section. Workers et vérificateurs
  construisent ce texte avec la même fonction (`PassageRecord::embedding_input`).
- `silicium-corpus/1` (sans `section`) est encore lu ; un nœud plus ancien
  refuse `/2`, donc l'éditeur et les workers doivent être mis à jour
  ensemble.
- Le découpage est déterministe : un même document donne toujours les mêmes
  passages (les vérificateurs en dépendent).
- Un fragment = une plage d'octets de lignes entières (`byte_range` de
  l'enveloppe de tâche, déjà utilisé par sha256) ; son manifeste garde aussi
  `items = {first, count}`.
- Raisons d'un fichier ignoré : `no_text`, `unsupported_format`,
  `unreadable`, `too_large`.

### Bloc de vecteurs `SLCMVEC1` (résultat d'un fragment)

En-tête de 32 octets (magie, dimension, nombre, id du premier passage,
réservé), puis `n × d` f32 little-endian. L'éditeur et les vérificateurs
refusent un bloc dont la dimension, le premier passage ou le nombre ne sont
pas ceux du fragment, ou dont un vecteur n'est pas de norme 1 (± 1e-3) ou
contient un NaN.

### Index `silicium-index/1` (résultat du job)

`index.json` (modèle, révision, dimension, documents, fichiers ignorés),
`vectors.f32` (vecteurs bruts, `numpy.fromfile(…, "<f4").reshape(-1, d)`),
`passages.jsonl` (`{"id","document","page","text"}`). Le manifeste est écrit
en dernier : il marque le job terminé pour le BackEnd.

## 4. Le modèle

| | |
| --- | --- |
| Modèle | `intfloat/multilingual-e5-small` (licence MIT), ~100 langues dont le français |
| Épinglage | commit `614241f622f53c4eeff9890bdc4f31cfecc418b3` ; SHA-256 et taille de `model.safetensors` (470 Mo) et `tokenizer.json` (17 Mo) compilés dans le binaire ; architecture compilée (le `config.json` du dépôt n'est pas téléchargé) |
| Calcul | Candle (Rust pur, CPU) ; préfixes `passage: ` / `query: ` ; moyenne des jetons hors remplissage ; norme 1 |
| Stockage | `<SILICIUM_DATA_DIR>/models/<sha256>`, téléchargé une fois, vérifié au téléchargement et à chaque chargement (un fichier abîmé est retéléchargé, un téléchargement plus gros que prévu est interrompu) ; verrou contre deux téléchargements simultanés, repris s'il n'a pas bougé depuis 10 min |
| Mémoire | ~0,5 Go chargé ; déchargé après 15 min sans usage |

**Pourquoi Candle et pas ONNX Runtime** : pas de bibliothèque native à livrer
avec l'app (Windows, Linux, macOS), même chaîne de compilation que le reste du
nœud. Le moteur est derrière `Encoder` : on pourra en changer sans toucher au
protocole.

**Changer de modèle** = nouvel identifiant de modèle, donc nouveau workload :
des vecteurs de deux modèles ne sont jamais mélangés dans un index, et un
worker ne peut pas répondre avec un autre modèle que celui de la tâche.

**Un worker ne prend une tâche, et un vérificateur ne propose une
vérification, que si le modèle est prêt** : sinon il lance le
téléchargement en arrière-plan et laisse la tâche, que l'éditeur réannonce
toutes les 10 s ; le bail d'une tâche n'expire donc jamais pendant un
téléchargement de 490 Mo.

## 5. Vérification

Deux CPU honnêtes ne produisent pas les mêmes nombres à virgule (SIMD, ordre
des additions, remplissage d'un lot) : on ne peut pas comparer des hachages.
Le vérificateur :

1. récupère le bloc publié (chez le worker, ou chez l'éditeur qui le
   télécharge dès sa publication : deux PC derrière leur box ne se joignent
   souvent pas) ;
2. contrôle sa forme et ses normes (refus immédiat sinon) ;
3. tire `k = clamp(⌈n/50⌉, 3, 8)` passages à partir de la graine d'acceptation
   de l'éditeur, inconnue du worker quand il a calculé ;
4. les recalcule et exige une similarité cosinus ≥ 0,999 pour chacun.

| Situation | Similarité observée |
| --- | --- |
| Même modèle, autre CPU ou autre lot | > 0,99999 |
| Modèle quantifié, autre modèle, vecteurs inventés | nettement < 0,999 |

Un worker qui truque une fraction `f` de ses vecteurs est pris avec une
probabilité `1 − (1 − f)^k` : à coup sûr s'il truque tout, environ 2 fois sur 3
pour un quart de ses vecteurs avec `k = 4`. La vérification coûte environ 2 %
du calcul. La règle du worker seul (auto-vérification quand il est le seul
worker) s'applique comme aux autres workloads.

## 6. Sécurité

| Risque | Mesure |
| --- | --- |
| Document piégé (PDF qui fait boucler, exploser la mémoire ou paniquer le parseur) | Lecture dans un processus enfant du nœud (`p2p_node embedding-prepare`) : tué après 300 s, 2 Go de mémoire au plus (Unix), premier choix du tueur de mémoire de Linux, deux lectures en même temps au plus ; une panique d'un format est rattrapée et le fichier ignoré |
| Archive bombe | ZIP lu sur un seul niveau, 1 000 fichiers, 64 Mio par fichier, 256 Mio décompressés au total, tailles déclarées contrôlées à la lecture ; le corpus produit (le texte) ne dépasse pas 64 Mio, sinon l'utilisateur est invité à envoyer en plusieurs fois |
| Substitution de modèle | Hash de chaque fichier épinglé dans le code, vérifié au téléchargement et au chargement ; source changeable (`SILICIUM_MODEL_BASE_URL`), pas les hashes |
| Résultat truqué | Vérification ci-dessus ; l'éditeur refuse un bloc de forme ou de norme incorrecte |
| Document servi au navigateur | `GET /jobs/{id}/documents` vérifie que la tâche appartient à l'utilisateur, ne lit que des entrées existantes du ZIP déposé et ne sert que des types inertes (PDF, texte, `.docx` en téléchargement) ; l'en-tête `Content-Security-Policy: sandbox` protège l'ouverture directe de l'URL (le site, lui, ouvre une copie locale du fichier) |
| Recherche dans les documents d'un autre | La recherche porte sur les tâches de la collection **et** du compte ; une collection ne s'étend qu'avec une tâche du même compte |
| **Confidentialité** | **Les workers lisent le texte.** Consentement explicite à l'envoi (case à cocher, vérifiée par le BackEnd). Voir « Feuille de route » pour le mode privé |

## 7. Recherche

`POST /v1/embedding/search` sur le nœud éditeur (jeton de contrôle requis),
appelé par le BackEnd avec les tâches terminées de la collection :

```json
{"jobs": ["site-render-7-…", "site-render-7-…"], "query": "comment résilier ?", "top_k": 10}
```

- **Recherche hybride** : la question est vectorisée avec le même modèle
  épinglé (préfixe `query: `) et cherchée aussi par mots-clés (BM25 sur le
  document, la section et le texte de chaque passage ; statistiques communes
  à toutes les tâches cherchées). Les deux classements sont fusionnés par
  rang réciproque (RRF, k = 60). Les mots-clés rattrapent ce qu'un petit
  modèle manque : nombres, noms, références (« article 6 », « 780 € »).
  L'index de mots-clés est construit au chargement de l'index, en mémoire :
  les fichiers publiés ne changent pas.
- Deux passages voisins qui se chevauchent ne sont montrés qu'une fois.
- Chaque résultat porte sa `section`, affichée par le site sous le nom du
  document.
- Recherche exacte par produit scalaire : une fraction de seconde pour un million de passages
  sur un cœur. Les index chargés restent en mémoire (512 Mo par défaut, les
  moins récemment utilisés sortent en premier).
- `503` + `Retry-After: 10` tant que le modèle se prépare (première recherche
  sur l'éditeur) : le site réessaie seul.
- Une tâche introuvable ou inachevée sur ce nœud n'empêche pas la recherche
  dans les autres : elle est listée dans `unavailable_jobs`. La requête
  échoue (`404`) seulement si aucune ne peut être cherchée.
- Les index sont lus hors de la boucle asynchrone et hors du verrou du cache.

Le BackEnd ajoute ses propres contrôles (propriété de la tâche, question de
1 à 1 000 caractères, 50 résultats au plus) et remplace les identifiants
réseau par ceux du site.

## 8. Exploitation

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SILICIUM_MODEL_DIR` | `$SILICIUM_DATA_DIR/models` | Fichiers des modèles |
| `SILICIUM_MODEL_BASE_URL` | `https://huggingface.co` | Source des modèles (miroir de même arborescence possible) |
| `SILICIUM_EMBEDDING_PASSAGES_PER_FRAGMENT` | `128` | Passages par fragment |
| `SILICIUM_EMBEDDING_IDLE_UNLOAD_S` | `900` | Déchargement d'un modèle inutilisé |
| `SILICIUM_EMBEDDING_INDEX_CACHE_MB` | `512` | Index gardés en mémoire pour la recherche |
| `SILICIUM_EMBEDDING_PREPARE_TIMEOUT_S` | `300` | Lecture maximale des documents |
| `SILICIUM_EMBEDDING_PREPARE_MEMORY_MB` | `2048` | Mémoire du processus qui lit les documents (Unix) |
| `SILICIUM_EMBEDDING_PREPARE_PARALLEL` | `2` | Lectures de documents en même temps |

À prévoir sur le VPS : ~500 Mo de disque pour le modèle et ~0,5 Go de mémoire
pendant les recherches ; un accès sortant à `huggingface.co` (ou un miroir).
Journal à surveiller : `Preparing model …`, `Model … ready` /
`Model … unavailable`, `Documents not prepared`, `Search failed`.

Volume : un PC de bureau vectorise quelques centaines de passages par
seconde ; un livre de 300 pages (~1 000 passages) prend quelques secondes.

## 9. Tests

| Niveau | Commande | Couvre |
| --- | --- | --- |
| Crate | `cargo test -p silicium-embedding` | formats, documents réels (PDF, Word, ZIP), découpage, cache de modèle (téléchargement truqué, verrou), encodeur (modèle minuscule), index, recherche |
| Nœud | `cargo test -p p2p_node` | préparation, découpage, calcul, vérification d'un résultat honnête et de résultats truqués, assemblage, API de recherche |
| Bout en bout | `WORKERS=2 WORKLOAD=ai/embedding/test-tiny crates/p2p-node/scripts/e2e-local.sh docs.zip` (binaire construit avec `--features p2p_node/test-model`) | orchestrateur + 2 workers en local : chacun calcule un fragment et vérifie celui de l'autre, l'index est assemblé, la recherche répond |
| Vrai modèle | `cargo test -p silicium-embedding --release --test real_model -- --ignored` | téléchargement, hashes, classement par le sens (français et anglais), écart entre lots |
| Qualité | `silicium-embed eval crates/embedding/eval` | rappel@k et MRR des modes dense, mots-clés et hybride sur 74 questions FR/EN/DE (`--lexical-only` sans modèle) |
| Parité | `crates/embedding/scripts/parity_check.py` | vecteurs identiques à `sentence-transformers` (≥ 0,999) |
| BackEnd | `go test ./...` | dépôt, consentement, collections, recherche, ouverture, export |
| FrontEnd | `npm test`, `npm run test:functional` | sélection des documents, surlignage, parcours de dépôt et de recherche |

## 10. Limites et feuille de route

1. **Mode privé (« seulement mes appareils »)** : liaison d'un nœud à un
   compte (appairage depuis l'app), tâches réservées à une liste de pairs dans
   l'enveloppe signée, contenus servis aux seuls pairs autorisés. Le site
   l'affichera par défaut quand l'utilisateur a au moins un appareil lié.
2. **Qualité de recherche** : reclassement des meilleurs passages par un
   cross-encoder, modèle plus grand (`bge-m3`) comme second workload, jugés
   sur `silicium-embed eval`.
3. **OCR** des PDF scannés (aujourd'hui signalés, pas lus).
4. **Formats** `.odt`, `.pptx`, HTML.
5. **Index approché** (HNSW) au-delà d'environ un million de passages.
6. **Réponses rédigées** : le workload Ollama s'appuiera sur cet index pour
   répondre à la question en citant les passages (RAG).
