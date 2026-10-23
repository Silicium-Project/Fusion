# Silicium

Silicium est un réseau de calcul distribué : des ordinateurs de particuliers
calculent des sous-tâches, d'autres nœuds les vérifient, les résultats sont
rassemblés, et la blockchain Solana rend les transactions transparentes
(jobs, réputation, staking, récompenses).

Ce dépôt, **Fusion**, assemble tous les composants et contient le déploiement.

## Carte du dépôt

| Chemin | Type | Contenu |
| --- | --- | --- |
| [`Network/`](Network/) | sous-module | Runtime réseau en Rust (nœud, calcul, workloads), programme Solana. Voir `Network/README.md` |
| [`BackEnd/`](BackEnd/) | sous-module | API Go : comptes, sessions JWT, jobs, pilotage du réseau |
| [`FrontEnd/`](FrontEnd/) | sous-module | Site Nuxt 3 : création et suivi des calculs |
| [`apps/silicium-node/`](apps/silicium-node/) | dossier | Application desktop Tauri qui installe et supervise un nœud chez l'utilisateur |
| [`deploy/`](deploy/) | dossier | Serveur (VPS) : Docker Compose, Nginx, systemd, VPN, canaux de release, scripts de CI, tests Python (`deploy/tests/`) |
| [`.github/workflows/`](.github/workflows/) | dossier | CI/CD : Build, Test, Deploy, synchronisation des sous-modules |
| [`docs/`](docs/) | dossier | Documentation transverse (architecture, exploitation, développement) |
| `install-silicium-windows.*`, `start-silicium-local.*` | scripts | Installation et lancement de l'environnement local (Windows) |

## Règle de langage

- **Rust** pour tout ce qui s'exécute chez un utilisateur ou sur le serveur
  (nœud réseau, calcul, app desktop).
- **Go** pour le BackEnd, **TypeScript** pour le FrontEnd et le SDK Solana.
- **Python** uniquement pour l'outillage des développeurs.

Le runtime réseau est entièrement en Rust : l'orchestrateur du serveur et les
nœuds des utilisateurs exécutent le même binaire `p2p_node`. L'ancien runtime
Python a été supprimé ; l'historique de la bascule est dans
[`Network/docs/architecture/rust-migration.md`](Network/docs/architecture/rust-migration.md).

## Démarrage rapide (Windows)

```powershell
git clone --recurse-submodules https://github.com/Silicium-Project/Fusion.git
.\install-silicium-windows.cmd -InstallSystemDeps
.\start-silicium-local.cmd
```

Détails, options et variables : [`docs/development/local-setup.md`](docs/development/local-setup.md).

## Documentation

Index : [`docs/README.md`](docs/README.md).
