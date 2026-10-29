# Silicium Workbench

Workbench est l'atelier d'intégration de Silicium : documentation, roadmap,
contrats partagés, outillage commun et description exacte des versions compatibles.
Les applications évoluent dans des dépôts indépendants, actuellement privés.

## Commencer

```sh
git clone https://github.com/Silicium-Project/Workbench.git
cd Workbench
./dev doctor --profile tooling
./dev capabilities --json
./dev workspace status --json
./dev ci plan --scope public --base origin/main --json
```

Pour développer un composant, un accès à son dépôt est nécessaire :

```sh
./dev workspace init --component web       # aperçu, aucune récupération
./dev workspace init --component web --apply
cd apps/web
npm ci
npm run dev
```

Sous Windows, utiliser `.\dev.ps1`. Consulter les
[commandes communes](docs/development/commands.md) et les
[instructions agents](AGENTS.md).

## Dépôts et responsabilités

| Chemin local | Dépôt | Responsabilité |
| --- | --- | --- |
| `apps/web` | [FrontEnd](https://github.com/Silicium-Project/FrontEnd) | Nuxt, comptes et projets |
| `apps/api` | [BackEnd](https://github.com/Silicium-Project/BackEnd) | API Go et accès au réseau |
| `apps/node` | [DesktopApp](https://github.com/Silicium-Project/DesktopApp) | Application Tauri et supervision locale |
| `network` | [Network](https://github.com/Silicium-Project/Network) | Runtime P2P Rust et workloads |
| `chain` | [Solana](https://github.com/Silicium-Project/Solana) | Programme Anchor dans `solana/`, SDK dans `sdk/` |
| — | [Integration](https://github.com/Silicium-Project/Integration) | Qualification complète avec sources et journaux privés |

[components.lock.json](components.lock.json) et les gitlinks désignent les mêmes
commits immuables. Le clone public ne récupère aucune source privée par défaut.
Un changement de composant passe par sa PR ; son intégration passe par une PR
Workbench modifiant le pin et son lock ensemble.

## Historique et qualification

Workbench conserve l'identité GitHub et l'historique public de Fusion, ainsi que
ses issues, PR et releases. **Les anciennes sources déjà publiées restent dans
cet historique.** Les versions futures utilisent les dépôts séparés. Voir
[la décision et la méthode de migration](docs/architecture/multi-repo.md).

`ci/required` sur Workbench qualifie ses fichiers publics. La compatibilité
applicative exige une qualification privée complète des cinq pins. Une CI
publique verte ne suffit pas à publier une application. La qualification privée
reste désactivée tant que le solde inclus courant ne couvre pas le pire cas du
plan et qu'aucun run concurrent ne consomme ce solde. Aucun plafond de dépense
Actions à zéro n'est appliqué par le workflow ; aucun dépassement facturé ni
runner VPS de secours n'est autorisé.
Les publications automatiques restent suspendues pendant cette transition.
La preuve du `ci/required` courant peut être vérifiée sans jeton avec
`./dev ci public-evidence --sha SHA --json`.

[Documentation](docs/README.md) · [Contribution](CONTRIBUTING.md) ·
[Sécurité](Security.md) · [Licence MIT de Workbench](LICENSE) ·
[Roadmap](docs/roadmap/README.md)
