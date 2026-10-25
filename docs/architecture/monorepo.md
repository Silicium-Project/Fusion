# ADR — Monorepo Fusion et séparation des responsabilités

Décision du 25 octobre 2026 : réunir le code des quatre dépôts dans Fusion,
préserver leurs historiques et utiliser des livraisons par artefacts immuables.
La centralisation du code ne modifie pas la topologie ou l'autorité du réseau.

## Historique

Les SHA de développement et de production ont été relevés avant import. Les
historiques sont rattachés sans squash ; les écarts `main`/`dev` ont été fusionnés
dans une copie isolée. Les sources et destinations sont dans
[import-map.json](import-map.json). Les sauvegardes complètes et modifications
locales restent dans l'espace privé de migration, hors du dépôt public.

Les déplacements sont des commits distincts des corrections de chemins et des
changements de comportement. Les anciens dépôts conservent les anciennes PR,
branches, tags et références de provenance.

## Frontières

Le runtime Rust conserve son workspace dans `network`. Anchor utilise son
propre workspace et sa toolchain dans `chain/solana`. Le SDK est un paquet
TypeScript distinct. Les applications web, API et desktop ont chacune leur
manifeste et leur lockfile ; l'import ne change pas leur gestionnaire.

Les contrats partagés sont versionnés, associés à leurs consommateurs et à
leurs fixtures. Une évolution incompatible doit préciser sa migration.
Les traits Rust et interfaces Go/TypeScript sont introduits aux points
pertinents d'extension ou d'IO, sans préfixe imposé à toutes les abstractions.

## Branches et environnements

`main` est l'intégration ; les branches de travail sont courtes. `dev` et
`prod` sont des environnements et canaux explicites. Les anciennes branches
restent présentes pour la traçabilité. Les changements locaux antérieurs
sont réintégrés dans des PR identifiables.
