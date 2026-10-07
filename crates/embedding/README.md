# embedding (`silicium-embedding`)

La « Recherche dans mes documents » de Silicium, hors plomberie réseau.
L'utilisateur dépose des documents ; le réseau calcule un vecteur par
passage avec un modèle épinglé ; l'utilisateur cherche ensuite dans ses
passages par le sens, et pas seulement par les mots exacts.

Le nœud (`p2p_node`, workload `ai/embedding/multilingual-e5-small`) et le
binaire `silicium-embed` utilisent exactement ce code, ce qui garantit que
le site, l'éditeur, les workers et les vérificateurs produisent les mêmes
vecteurs.

Conception détaillée (formats, vérification, sécurité, exploitation) :
[`docs/architecture/embedding-workload.md`](../../docs/architecture/embedding-workload.md).

## Modules

| Module | Rôle |
| --- | --- |
| `documents` | PDF, Word (`.docx`), texte, Markdown, ZIP → pages de texte ; fichiers ignorés listés avec leur raison (PDF scanné, format non pris en charge, fichier abîmé, trop gros) |
| `passages` | Pages → passages de 200 mots au plus, chevauchement de 40 mots, sans sortir d'une page |
| `corpus` | Entrée d'un job (`silicium-corpus/1`, JSON Lines) et découpage en fragments de passages entiers |
| `model` | Modèles épinglés (commit du dépôt, SHA-256 et taille de chaque fichier, architecture compilée) et leur cache local (`model/store.rs`) |
| `encoder` | Le modèle (Candle, CPU) : préfixes `passage: ` / `query: `, moyenne des jetons, vecteurs de norme 1 |
| `vectors` | Bloc de vecteurs publié par un worker (`SLCMVEC1`) et ses contrôles |
| `sampling` | Passages recalculés par un vérificateur, tirés d'une graine |
| `index` | Index assemblé (`silicium-index/1`) et recherche exacte |
| `testing` | Modèle minuscule construit en mémoire (fonctionnalité `test-model`, jamais dans une release) |

## Modèle

| | |
| --- | --- |
| Identifiant | `multilingual-e5-small` |
| Source | `intfloat/multilingual-e5-small`, commit `614241f622f53c4eeff9890bdc4f31cfecc418b3` (licence MIT) |
| Fichiers | `model.safetensors` (470 Mo), `tokenizer.json` (17 Mo), vérifiés par SHA-256 au téléchargement et au chargement |
| Vecteurs | 384 dimensions, ~100 langues dont le français et l'anglais |
| Mémoire | ~0,5 Go une fois chargé |

Changer de modèle (ou de révision) crée un nouvel identifiant de modèle, donc
un nouveau workload : des vecteurs de modèles différents ne sont jamais
mélangés.

## `silicium-embed`

```bash
silicium-embed prepare documents.zip -o corpus.jsonl   # documents → corpus
silicium-embed model fetch                             # télécharge et vérifie le modèle
silicium-embed index corpus.jsonl -o index/            # corpus → index, sur cette machine
silicium-embed search index/ "comment résilier ?"      # meilleurs passages (JSON Lines)
```

Les modèles sont rangés sous `--data-dir/models` (par défaut
`$SILICIUM_DATA_DIR/models`, sinon `./models`) ou `SILICIUM_MODEL_DIR` ; la
source se change avec `SILICIUM_MODEL_BASE_URL` (miroir de même arborescence).

## Tests

```bash
cargo test -p silicium-embedding                       # modèle minuscule, sans réseau
cargo test -p silicium-embedding --release --test real_model -- --ignored   # vrai modèle (490 Mo téléchargés une fois)
python3 crates/embedding/scripts/parity_check.py index/  # vecteurs identiques à sentence-transformers
```

Le contrôle de parité compare un index produit par `silicium-embed index` aux
vecteurs de la bibliothèque de référence (`sentence-transformers`) ; il
demande Python, PyTorch et un accès à Hugging Face, donc il se lance sur un
poste de développement, pas en CI.

## Limites connues

- Pas d'OCR : un PDF scanné est signalé (`no_text`) mais pas lu.
- Formats lus : PDF, `.docx`, texte, Markdown, ZIP d'un niveau ; pas de
  `.doc`, `.odt`, `.pptx` ni HTML.
- Recherche exacte (produit scalaire sur tous les passages) : une fraction de seconde pour un
  million de passages sur un cœur ; un index approché (HNSW) deviendra utile
  au-delà, sans changer les fichiers.
- Calcul sur CPU uniquement ; le nombre de threads suit les cœurs de la
  machine.
