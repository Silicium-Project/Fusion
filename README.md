# Silicium Fusion

Silicium développe un réseau de calcul distribué et vérifié. Fusion rassemble
les applications, le réseau Rust, le programme Solana et leur qualification.

## Développer

```sh
./dev doctor --profile tooling
./dev capabilities --json
./dev ci plan --base origin/main --head HEAD --json
./dev test --suite tooling
```

Sous Windows, remplacer `./dev` par `.\dev.ps1`. Les prérequis et commandes de
chaque composant sont dans le [guide de développement](docs/development/commands.md).

## Composants

| Emplacement | Responsabilité |
| --- | --- |
| [apps/web](apps/web) | Site Nuxt et parcours des comptes |
| [apps/api](apps/api) | API Go, comptes et accès au réseau |
| [apps/node](apps/node) | Application Tauri et supervision d'une machine |
| [network](network) | Runtime P2P et workloads Rust |
| [chain/solana](chain/solana) | Programme Anchor et qualification localnet |
| [packages/solana-sdk](packages/solana-sdk) | SDK TypeScript |
| [contracts](contracts) | Contrats et schémas partagés |
| [infra](infra) | Livraison d'artefacts, services et exploitation |

Les historiques des composants sont conservés sans squash. La
[carte de migration](docs/architecture/monorepo.md) documente leurs références.

## Contribuer et livrer

Lire [CONTRIBUTING](CONTRIBUTING.md), les [instructions agents](AGENTS.md) et les
[procédures de livraison](docs/operations/delivery.md). Pendant la stabilisation,
les contributions exécutées sont celles de l'équipe. Le Project de référence
reste privé ; les arbitrages internes ne sont pas publiés avec le code.

Les applications restent en développement. Le registre des commandes décrit
les capacités présentes ; la roadmap décrit les travaux à réaliser. Une release
n'est qualifiée qu'avec ses preuves, ses signatures et son manifeste.

[Documentation](docs/README.md) · [Sécurité](Security.md) · [Licence MIT](LICENSE)

[Roadmap](docs/roadmap/README.md) · [Workflow des issues](docs/development/issue-workflow.md)
