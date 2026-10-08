# Jeu d'évaluation de la recherche

Onze documents inventés (français, anglais, allemand) et 74 questions dont
on connaît la réponse. Il sert à juger chaque changement du découpage, des
mots-clés ou du modèle sur des chiffres plutôt qu'à l'œil.

```bash
cargo run --release -p silicium-embedding --bin silicium-embed -- eval crates/embedding/eval
cargo run --release -p silicium-embedding --bin silicium-embed -- eval crates/embedding/eval --lexical-only
```

Le rapport donne, pour les modes `dense` (sens), `lexical` (mots-clés) et
`hybrid` (les deux, mode du site), la part des questions dont la réponse est
dans les 1, 3, 5 et 10 premiers résultats (R@k) et le rang réciproque moyen
(MRR@10), au total et par langue, puis les questions manquées.

## Format

- `documents/` : tout fichier que lit `silicium-embed prepare` (PDF, Word,
  texte, Markdown), dans des sous-dossiers au choix.
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
- Garder quelques questions sur un nombre, un nom ou une référence exacte,
  et quelques questions dans une autre langue que le document.
- `contains` : une courte phrase exacte du document, qui ne tombe pas à
  cheval sur deux paragraphes.
