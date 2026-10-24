# Traitement par IA (workload `ai/llm/…`)

Une consigne appliquée par une IA à chaque élément d'une liste : résumer des
comptes rendus, traduire des fiches, classer des avis, extraire un nom ou un
montant. Les éléments sont indépendants : le réseau les répartit entre les
PC comme les tuiles du raytracer, et chaque partie est vérifiée par une autre
machine.

| | |
| --- | --- |
| Workload | `ai/llm/qwen2.5-1.5b-instruct` |
| Code | Network : `crates/llm` (formats, prompt, vérification, client Ollama, CLI `silicium-llm`), `crates/p2p-node/src/workload/llm/` (réseau) ; BackEnd : `internal/batchai`, `internal/handler/batchAIJobs.go` ; FrontEnd : `components/jobs/BatchAIForm.vue`, `components/jobs/BatchAIAnswers.vue`, `utils/batchAI.ts` ; app : `src-tauri/src/ai.rs` |
| État | Dev. Testé de bout en bout en local avec un faux Ollama ; le vrai modèle se teste avec `silicium-llm run` (voir « Tests ») |

## 1. Ce que voit l'utilisateur

1. **Dépôt.** « Nouveau calcul » → « Traitement par IA ». Il dépose un CSV,
   un fichier JSON Lines ou du texte. Le fichier est lu **dans le
   navigateur** : il choisit la colonne (devinée : la plus longue en
   moyenne), voit les trois premiers éléments et le nombre d'éléments.
2. **Consigne.** Il choisit Résumer, Traduire, Classer (avec ses catégories),
   Extraire (avec ses champs) ou Libre, et ajuste la consigne préremplie. En
   « Libre » sans consigne, chaque élément est envoyé tel quel (lot de
   prompts). Une case confirme que les machines du réseau lisent la liste
   (vérifiée aussi par le BackEnd).
3. **Suivi.** La page du projet affiche la demande, « 412 / 1 000 réponses
   vérifiées » et le tableau des réponses déjà vérifiées, qui grossit au fil
   du calcul.
4. **Résultat.** Tableau paginé, téléchargement CSV (UTF-8 avec BOM, une
   colonne par champ extrait, s'ouvre dans Excel) ou JSON Lines.

Côté contributeur, l'app desktop a un interrupteur « Tâches IA » (désactivé
par défaut) : l'activer télécharge Ollama (≈ 1,4 Go) ; le modèle (1,1 Go)
est téléchargé par le nœud à la première tâche.

## 2. Vue d'ensemble

```
Site ──POST /jobs (file=request.json, acknowledge_sharing)──▶ BackEnd ──▶ nœud éditeur (VPS)
                                                                 │ 1. prépare : demande → lot canonique
                                                                 │ 2. découpe : fragments d'éléments entiers
                                                                 ▼
             workers (PC) : Ollama joignable et modèle importé ? → réponses du fragment (une génération par élément)
             vérificateurs : 2 à 6 éléments tirés au sort, recalculés, comparés par similarité
                                                                 │
             éditeur : fragments/fragment-NNN.jsonl dès qu'une partie est vérifiée ; answers.* à la fin
Site ──GET /jobs/{id}/answers──▶ BackEnd (lit les fichiers du job)
```

## 3. Formats

### Demande `silicium-llm-request/1` (site → BackEnd → nœud)

```json
{"format": "silicium-llm-request/1", "task": "classify",
 "instruction": "Classe cet avis client selon son ton.",
 "output": {"kind": "label", "labels": ["positif", "négatif", "neutre"]},
 "max_tokens": 32, "source": {"name": "avis.csv", "column": "avis"},
 "items": ["Livraison rapide, très content.", "…"]}
```

`output.kind` : `text`, `label` (`labels`, 2 à 50) ou `fields` (`fields`, 1 à
20). Limites : 20 000 éléments, 6 000 caractères par élément, consigne de
2 000 caractères, `max_tokens` de 16 à 1 024 (256 par défaut), fichier de
16 Mo. Le site, le BackEnd (`internal/batchai`, messages traduits) et le
nœud (`silicium_llm::request`, qui fait foi) appliquent les mêmes limites.

Le nœud **nettoie** chaque texte : Unicode NFC, fins de ligne `\n`, plus de
caractères de contrôle, et plus de jetons spéciaux du format de chat
(`<|im_start|>`, `<|im_end|>`, `<|endoftext|>`) : sans cela, un élément
pourrait réécrire le prompt.

### Lot `silicium-llm-batch/1` (entrée partagée, JSON Lines)

```
{"format":"silicium-llm-batch/1","model":"qwen2.5-1.5b-instruct","item_count":2,"task":"classify","instruction":"…","output":{…},"max_tokens":32,"source":{…}}
{"id":0,"text":"…"}
{"id":1,"text":"…"}
```

Canonique (même demande ⇒ mêmes octets). Un fragment = une plage d'octets de
lignes entières (`byte_range`), avec `items = {first, count}` dans le
manifeste. 8 éléments par fragment par défaut, 128 fragments au plus.

### Réponses d'un fragment `silicium-llm-answers/1`

```
{"id":12,"output":"positif"}
{"id":13,"output":null}
```

`output` : texte, catégorie, objet `{champ: texte}` ou `null` (réponse
contrainte impossible à lire). L'éditeur refuse des réponses dont les ids,
le nombre ou la forme ne sont pas ceux du fragment.

### Résultat (`answers/`)

| Fichier | Contenu |
| --- | --- |
| `answers.jsonl` | `{"id","input","output"}` par élément, dans l'ordre |
| `answers.csv` | même tableau ; cellules commençant par `=`, `+`, `@` ou `-x` préfixées de `'` (pas de formule exécutée par le tableur) |
| `result.json` | `silicium-llm-result/1` : modèle (dépôt, révision, fichier, SHA-256, licence), version du prompt, consigne, `item_count`, `answered` ; écrit en dernier |

## 4. Le modèle et Ollama

| | |
| --- | --- |
| Modèle | `Qwen/Qwen2.5-1.5B-Instruct-GGUF`, fichier `qwen2.5-1.5b-instruct-q4_k_m.gguf` (1,1 Go, Apache 2.0), ~30 langues dont FR/EN/DE |
| Épinglage | commit `91cad51170dc346986eccefdc2dd33a9da36ead9`, SHA-256 et taille compilés dans le binaire |
| Téléchargement | par le nœud, dans le même magasin que les modèles d'embedding (`<SILICIUM_DATA_DIR>/models/<sha256>`, `SILICIUM_MODEL_BASE_URL`, verrou, reprise) ; puis envoyé à Ollama comme blob (Ollama revérifie le hash) et créé sous le nom `silicium-qwen2.5-1.5b-instruct-<16 premiers caractères du hash>` ; la copie du nœud est ensuite supprimée |
| Prompt | écrit par `silicium_llm::prompt` au format ChatML et envoyé en mode `raw` : le modèle de prompt de la version d'Ollama installée n'intervient jamais |
| Décodage | glouton (`temperature 0`, `top_k 1`), graine fixe, `num_ctx 8192`, `repeat_penalty 1.05`, tout épinglé dans `LlmModel::options` |
| Sorties contraintes | catégories et champs passent par les sorties structurées d'Ollama (schéma JSON) : la réponse est toujours une des catégories, ou un objet avec les champs demandés |
| Ollama | celui de l'app desktop (`SILICIUM_OLLAMA_URL=http://127.0.0.1:11435`), version épinglée 0.40.4 avec le SHA-256 de chaque archive ; un nœud sans Ollama ne prend aucune tâche IA |

**Un worker ne prend une tâche, et un vérificateur ne propose une
vérification, que si Ollama répond et contient le modèle.** Sinon le nœud
prépare le modèle en arrière-plan et laisse la tâche, que l'éditeur
réannonce toutes les 10 s. Un modèle prêt est revérifié toutes les minutes.

**Bail.** Une tâche IA a un bail de 5 min renouvelable 12 fois (65 min par
tentative, `Workload::terms`), contre 2 min pour les autres : sur un CPU, un
fragment prend quelques minutes, et un vérificateur doit recalculer ses
éléments dans un bail.

**Changer de modèle** = nouveau workload (`ai/llm/<autre modèle>`). Changer
le prompt ou les options = incrémenter `PROMPT_VERSION`, et ne pas mélanger
d'anciens et de nouveaux nœuds sur un même job.

## 5. Vérification

Deux machines honnêtes ne donnent pas toujours le même texte : CPU, GPU et
instructions SIMD arrondissent différemment, et dès qu'un jeton diffère, la
suite d'une réponse longue prend un autre chemin. On ne compare donc pas des
hachages. Le vérificateur :

1. récupère les réponses publiées et contrôle ids, nombre et forme (refus
   immédiat sinon) ;
2. tire au sort, à partir de la graine d'acceptation de l'éditeur (inconnue
   du worker quand il a calculé), `k` éléments : texte et champs
   `clamp(⌈n/6⌉, 2, 4)`, catégories `clamp(⌈n/4⌉, 3, 6)` ;
3. les recalcule et compare chaque réponse :

| Sortie | Similarité | Acceptation |
| --- | --- | --- |
| texte | 1 si mêmes mots, sinon F1 ROUGE-L des mots (plus longue sous-suite commune ; idéogrammes un par un) | moyenne ≥ 0,6 et chaque élément ≥ 0,2 |
| catégorie | égales ou non | au moins 2 sur 3 en accord (moyenne ≥ 0,66) |
| champs | moyenne de la similarité texte de chaque champ | comme le texte |

Ce que ça attrape : réponses inventées, vides, copie de l'élément, autre
élément, mauvaise forme, catégories tirées au hasard. Un worker qui triche
sur une fraction `f` de ses éléments est pris avec une probabilité
`1 − (1 − f)^k` (comme pour l'embedding).

**Limite honnête.** C'est une vérification plus faible que celle de
l'embedding (cosinus ≥ 0,999) ou du raytracer (octets identiques) : un
worker qui utiliserait un modèle voisin (même famille, autre quantification)
pourrait passer sur des textes courts. **Les seuils sont des premières
valeurs** : ils sont à mesurer sur de vraies machines avec
`silicium-llm compare` (section 8) avant la production. Pistes pour durcir :
vérifier la vraisemblance des jetons du worker sous le modèle épinglé (log-
probabilités en « teacher forcing », dès qu'Ollama les exposera pour un
texte imposé), ou comparer par l'embedding épinglé de Silicium.

## 6. Sécurité et confidentialité

| Risque | Mesure |
| --- | --- |
| Élément qui détourne le prompt | jetons spéciaux retirés ; l'élément est délimité (`<text>…</text>`) ; la sortie contrainte (catégories, champs) ne peut pas sortir du schéma ; le modèle ne fait qu'écrire du texte (aucun outil) |
| Substitution de modèle | hash épinglé, vérifié au téléchargement, par Ollama à l'import, et nom du modèle contenant le hash |
| Archive Ollama modifiée | SHA-256 de chaque archive compilé dans l'app ; une archive qui ne correspond pas est supprimée |
| Ollama exposé | l'app l'écoute sur `127.0.0.1:11435` seulement, avec son propre dossier de modèles ; l'Ollama personnel de l'utilisateur (11434) n'est pas touché |
| Formule dans le CSV | cellules préfixées (section 3) |
| **Confidentialité** | **les workers lisent les éléments** : consentement explicite (case à cocher, vérifiée par le BackEnd) ; même mode privé à venir que pour l'embedding |

## 7. Exploitation

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `SILICIUM_OLLAMA_URL` | — | Ollama du worker (posé par l'app) |
| `SILICIUM_LLM_ITEMS_PER_FRAGMENT` | `8` | Éléments par fragment |
| `SILICIUM_LLM_MAX_FRAGMENTS` | `128` | Fragments par job (≤ 256) |
| `SILICIUM_MODEL_DIR`, `SILICIUM_MODEL_BASE_URL` | comme l'embedding | Magasin et source du GGUF |

Rien à installer sur le VPS (l'éditeur ne calcule pas). Débit : un PC de
bureau répond à quelques éléments par minute sur CPU (dizaines de jetons
par seconde), bien plus avec un GPU (utilisé automatiquement par Ollama).
Journal : `Preparing model …`, `Model … ready in Ollama`, `Ollama
unreachable`, `Answered N items of …`, `Answers of … differ from
recomputation: [scores]`.

## 8. Tests

| Niveau | Commande | Couvre |
| --- | --- | --- |
| Crate | `cargo test -p silicium-llm` | demande et nettoyage, lot, prompt, schémas, lecture des réponses, similarité et seuils, assemblage et CSV, client Ollama contre un faux serveur |
| Nœud | `cargo test -p p2p_node llm` | préparation, découpage, bail, calcul, vérification de réponses honnêtes et truquées, assemblage, aperçu des fragments vérifiés |
| Bout en bout | `WORKERS=2 WORKLOAD=ai/llm/test-tiny crates/p2p-node/scripts/e2e-local.sh request.json` (binaires `--features p2p_node/test-ollama,silicium-llm/test-ollama`) | orchestrateur + 2 workers, chacun avec un faux Ollama : chaque fragment calculé par l'un et vérifié par l'autre, réponses assemblées dans l'ordre |
| Vrai modèle | `silicium-llm prepare request.json batch.jsonl` puis `silicium-llm run batch.jsonl a.jsonl --ollama http://127.0.0.1:11434 --gguf qwen2.5-1.5b-instruct-q4_k_m.gguf` | import et réponses du vrai modèle sur une machine |
| Calibrage | même lot sur deux machines (ou CPU et GPU), puis `silicium-llm compare batch.jsonl a.jsonl b.jsonl` | similarité élément par élément et part des vérifications qui passeraient avec les seuils actuels |
| BackEnd | `go test ./...` | dépôt, consentement, refus traduits, réponses partielles et finales, téléchargements |
| FrontEnd | `npm test`, `npm run test:functional` | lecture CSV/JSONL/texte, demande, parcours de dépôt et de suivi |
| App | `cargo test` dans `apps/silicium-node/src-tauri` | archives Ollama épinglées, câblage superviseur / nœud |

## 9. Feuille de route

1. Calibrer les seuils sur le réseau de dev (section 8), puis vérification
   par vraisemblance des jetons.
2. Traiter directement des documents (corpus de l'embedding comme liste).
3. Réponses rédigées sur ses documents (RAG) à partir de l'index d'embedding.
4. Modèle plus grand en second workload (`qwen2.5-7b-instruct`, Apache 2.0)
   pour les PC avec GPU, avec une capacité annoncée par le nœud.
5. Lancement automatique : l'app pourrait proposer les tâches IA quand elle
   détecte un GPU.
