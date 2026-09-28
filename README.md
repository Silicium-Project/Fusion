# Silicium

Silicium est un réseau de calcul distribué : des ordinateurs de particuliers
calculent des sous-tâches, d'autres nœuds les vérifient, les résultats sont
rassemblés, et la blockchain Solana rend les transactions transparentes
(jobs, réputation, staking, récompenses).

Ce dépôt, **Fusion**, assemble tous les composants et contient le déploiement.

## Carte du dépôt

| Chemin | Type | Contenu |
| --- | --- | --- |
| [`Network/`](Network/) | sous-module | Runtime réseau (Rust cible, Python legacy), programme Solana, dashboard. Voir `Network/README.md` |
| [`BackEnd/`](BackEnd/) | sous-module | API Go : comptes, sessions JWT, jobs, pilotage du réseau |
| [`FrontEnd/`](FrontEnd/) | sous-module | Site Nuxt 3 : création et suivi des calculs |
| [`apps/silicium-node/`](apps/silicium-node/) | dossier | Application desktop Tauri qui installe et supervise un nœud chez l'utilisateur |
| [`deploy/`](deploy/) | dossier | Serveur (VPS) : Docker Compose, Nginx, systemd, VPN, canaux de release, scripts de CI |
| [`.github/workflows/`](.github/workflows/) | dossier | CI/CD : Build, Test, Deploy, synchronisation des sous-modules |
| [`docs/`](docs/) | dossier | Documentation transverse (architecture, exploitation, développement) |
| [`tests/`](tests/) | dossier | Tests Python des canaux de release et du VPN |
| `install-silicium-windows.*`, `start-silicium-local.*` | scripts | Installation et lancement de l'environnement local (Windows) |

## Règle de langage

- **Rust** pour tout ce qui s'exécute chez un utilisateur ou sur le serveur
  (nœud réseau, calcul, app desktop).
- **Go** pour le BackEnd, **TypeScript** pour le FrontEnd et le SDK Solana.
- **Python** uniquement pour l'outillage des développeurs.

Le runtime réseau est encore en Python en production ; sa migration vers Rust
est décrite dans
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
