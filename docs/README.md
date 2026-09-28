# Documentation — Fusion

Documentation transverse au projet. Chaque composant a aussi sa propre
documentation : `Network/docs/`, `deploy/README.md`,
`apps/silicium-node/README.md`, et les README de `BackEnd/` et `FrontEnd/`.

| Dossier | Contenu |
| --- | --- |
| [`architecture/`](architecture/) | Comment les composants s'assemblent |
| [`operations/`](operations/) | CI/CD, canaux de release, synchronisation des sous-modules |
| [`development/`](development/) | Environnement local, conventions |
| [`archive/`](archive/) | Documents datés, conservés pour l'historique |

## Index

- [architecture/overview.md](architecture/overview.md) — composants, flux, où vit chaque chose
- [operations/ci-cd-topology.md](operations/ci-cd-topology.md) — workflows GitHub et runners
- [operations/releases-and-submodules.md](operations/releases-and-submodules.md) — canaux `dev` / `prod`, composition des sous-modules
- [development/local-setup.md](development/local-setup.md) — installer et lancer tout le projet en local
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — contribuer
- [archive/repo-attack-plan-and-triage-2026-09-08.md](archive/repo-attack-plan-and-triage-2026-09-08.md) — plan figé du 08/09/2026 (remplacé par la migration Rust)
