# Jeu d'évaluation de la recherche

24 documents inventés (français, anglais, allemand) et 232 questions dont
on connaît la réponse. Il sert à juger chaque changement du découpage, des
mots-clés ou du modèle sur des chiffres plutôt qu'à l'œil.

```bash
cargo run --release -p silicium-embedding --bin silicium-embed -- eval crates/embedding/eval
cargo run --release -p silicium-embedding --bin silicium-embed -- eval crates/embedding/eval --lexical-only
```

Le rapport donne, pour chaque mode, la part des questions dont la réponse
est dans les 1, 3, 5 et 10 premiers résultats (R@k) et le rang réciproque
moyen (MRR@10), au total et par langue, puis les questions manquées :

- `dense` : par le sens seul ;
- `lexical` : par mots-clés seuls ;
- `auto` : mode du site, sens + mots-clés quand la question contient un
  nombre, un code ou un sigle ;
- `hybrid (keywords xP)` : sens + mots-clés sur toutes les questions, pour
  chaque poids P de `--lexical-weights`.

Options pour comparer : `--max-words`, `--overlap-words`, `--min-words`,
`--no-headings` (découpage sans titres ni sections) et `--input` (ce que lit
le modèle : `full` = titre du document + section + texte, `section`,
`title`, `text`).

## Ce que contient le jeu

- Des documents structurés (Markdown, « Article N », « § N », « Clause N »)
  et des documents en prose sans titre ni intertitre, comme le texte tiré
  d'un PDF.
- Des documents qui se ressemblent exprès (deux baux meublés, deux machines
  à café, location de vélos et de trottinettes) : la recherche doit trouver
  le bon.
- Des questions reformulées comme un utilisateur, des questions sur un
  nombre, un code ou une référence (« article 14 », « E21 »,
  « INC-20417 »), et des questions dans une autre langue que le document.

## Résultats (vrai modèle `multilingual-e5-small`, 2026-10-08)

| Version | R@1 | R@5 | R@10 | MRR |
| --- | --- | --- | --- | --- |
| Avant : 200 mots, coupés n'importe où, texte seul (`--max-words 200 --overlap-words 40 --min-words 30 --no-headings --input text`) | 63,8 % | 78,4 % | 81,0 % | 0,699 |
| + titres et sections (`--input section`) | 72,4 % | 87,1 % | 90,5 % | 0,787 |
| + coupe en fin de paragraphe ou de phrase | 72,8 % | 90,5 % | 94,8 % | 0,804 |
| **+ titre du document (version actuelle)** | **73,3 %** | **90,1 %** | **94,8 %** | **0,808** |

Mode `auto` dans chaque ligne. Sur la version actuelle : sens seul 0,791,
mots-clés seuls 0,733, hybride sur toutes les questions de 0,785 (poids 0,2)
à 0,805 (poids 0,75). Restent ratées surtout les questions posées dans une
autre langue que le document.

## Format

- `documents/` : tout fichier que lit `silicium-embed prepare` (PDF, Word,
  texte, Markdown), dans des sous-dossiers au choix ; noms de fichiers
  uniques.
- `questions.jsonl`, une question par ligne :

```json
{"id":"fr-bail-01","lang":"fr","question":"Combien de temps de préavis ?","expected":[{"document":"contrat-de-location.md","contains":"Le préavis est d'un mois"}]}
```

Un résultat répond quand il vient d'un document attendu (nom du fichier,
sans dossier) et contient les mots attendus, comparés sans casse, accents
ni espaces en trop : le jeu reste valable quand le découpage change.

## Ajouter des questions

- Formuler la question comme un utilisateur, avec d'autres mots que le
  document (paraphrase) : c'est ce que la recherche par le sens doit
  rattraper.
- Garder des questions sur un nombre, un nom ou une référence exacte, et
  des questions dans une autre langue que le document.
- `contains` : une courte phrase exacte (4 à 12 mots) d'un seul paragraphe.
- Une question n'a qu'une bonne réponse dans tout le jeu : ajouter un
  indice (« sur ma Crema Pro », « quai Saint-Vincent ») quand deux documents
  se ressemblent.
