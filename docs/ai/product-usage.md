# Utiliser et diagnostiquer les parcours existants

Cette procédure décrit le code présent. La migration n'a pas encore été
fusionnée ni livrée ; vérifier la version exposée avant d'attribuer au VPS
un comportement observé seulement dans la branche. Les fonctionnalités de
roadmap n'ont pas valeur de capacité disponible.

## Identifier le contexte et ses effets

| Opération | Droits et effets |
|---|---|
| Lire santé, version ou plan CI | Lecture ; pas de modification distante |
| Développer l'API avec SQLite | Création d'une base locale et migrations automatiques |
| Installer un paquet | Administrateur local ; fichiers et services du poste modifiés |
| Créer un code d'association | Session du compte ; autorisation temporaire à garder privée |
| Associer une machine | Signature de son identité et liaison persistante au compte |
| Soumettre un calcul | Données distribuées ; coût possible si les paiements sont activés |
| Signer une transaction | Effet blockchain selon le réseau et l'instruction ; décision de l'utilisateur |

Ne jamais demander une seed, afficher une clé privée ou copier un wallet dans
une fixture. Ne pas accepter une transaction, clôturer un calcul ou délier une
machine au titre d'un diagnostic en lecture seule.

## Développement depuis le clone

Depuis Workbench, commencer par `./dev workspace status`, puis exécuter
`./dev workspace init --component api --apply` selon la
[procédure multi-dépôts](../architecture/multi-repo.md). Il faut avoir accès au
dépôt privé BackEnd. Après cette initialisation, lire `apps/api/AGENTS.md`, puis
lancer `./dev doctor --profile api`. Le fichier du composant n'est pas présent
dans un clone public non initialisé. L'API sait utiliser SQLite sans serveur
PostgreSQL ; réserver ce mode au développement local. Exemple Bash :

```sh
mkdir -p .artifacts/local-api
DATABASE_DRIVER=sqlite SQLITE_PATH="$PWD/.artifacts/local-api/site.db" \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  HOST=127.0.0.1 PORT=8080 SILICIUM_RELEASE_CHANNEL=dev \
  CORS_ALLOWED_ORIGINS=http://127.0.0.1:3000 \
  SILICIUM_SOLANA_PAYMENTS_ENABLED=0 SILICIUM_DEVNET_TRACE=0 \
  go -C apps/api run ./cmd
```

La clé JWT générée est éphémère : les sessions de ce serveur local sont
invalidées après redémarrage. Pour conserver une configuration locale, la
placer dans un stockage privé hors Git. Ne jamais réutiliser les paramètres
ou la base du VPS. L'API démarre sans runtime réseau ; les fonctions de calcul
peuvent alors être indisponibles, même si `/health` répond.

Dans un autre terminal Bash :

```sh
npm ci --prefix apps/web
NUXT_PUBLIC_API_BASE=http://127.0.0.1:8080 \
  npm --prefix apps/web run dev -- --host 127.0.0.1
curl --fail --silent --show-error http://127.0.0.1:8080/health
curl --fail --silent --show-error http://127.0.0.1:8080/version
```

Sous Windows, utiliser `dev.ps1` pour les commandes communes et les variables
`$env:` pour les applications. Les suites natives Windows se lancent avec
`.\dev.ps1 test --suite node-windows`. Les scripts Bash demandent Git Bash.
Ne pas supposer qu'un build Linux qualifie les comportements Windows.

## Site privé et WireGuard

Le canal dev sert le site sur `https://10.77.0.1:8443/`. Le certificat de la CA
de développement et la configuration WireGuard doivent provenir d'un canal
de confiance de l'équipe. Vérifier l'empreinte de la CA avant installation ;
ne pas installer une CA obtenue avec une vérification TLS désactivée.

Sur un poste déjà équipé du helper local :

```sh
command -v silicium-vpn
silicium-vpn status
silicium-vpn on
silicium-vpn off
```

Ce helper préexistant n'est pas distribué par Workbench. Ne pas
annoncer son installation par `dev`. Sans helper, une configuration système
déjà installée dans `/etc/wireguard/wg-dev.conf` peut être activée avec
`sudo wg-quick up wg-dev`, puis désactivée avec `sudo wg-quick down wg-dev`.
Vérifier d'abord les interfaces existantes pour éviter deux tunnels sur les
mêmes routes ; ne jamais remplacer une configuration différente sans analyse.

Diagnostic, sans afficher le contenu de la configuration :

```sh
sudo wg show interfaces
ip -4 route get 10.77.0.1
sudo wg show wg-dev latest-handshakes
curl --fail --silent --show-error --connect-timeout 5 \
  https://10.77.0.1:8443/api/version
```

Un handshake récent démontre un échange WireGuard ; il ne démontre ni la santé
du reverse proxy, ni celle de l'API. Un délai HTTP avec handshake actif appelle
le [diagnostic du service](../operations/diagnostics.md), pas la régénération
des clés. Un échec TLS appelle la vérification de la CA et de la date du poste.

## Installer ou mettre à jour une machine

La page `/download` et les tests d'installation utilisent le même
[contrat de snippets](../../contracts/install/repositories.json). Pour afficher
exactement les commandes DNF dev actuelles depuis le clone :

```sh
node --input-type=module -e 'import {repositoryCommands} from "./contracts/install/repositories.mjs"; const c=repositoryCommands("dnf","dev"); console.log([c.setup,c.install,c.diagnose].join("\n\n"))'
```

Remplacer `dnf` par `apt` pour Debian/Ubuntu. Examiner ces commandes avant leur
exécution administrateur. Le canal dev exige le VPN et sa CA ; `prod` désigne
le dépôt public de paquets existant. La mise à jour est `c.update`, les commandes
de CA sont `c.ca` après obtention et vérification du certificat.

En cas de paquet absent : vérifier que le dépôt du canal est activé, que les
métadonnées sont accessibles et que la version attendue a réellement été
publiée. Ne pas remplacer l'installation par un `.deb`/`.rpm` local pour
masquer une livraison absente. Une vérification statique du snippet ne qualifie
pas une installation ; voir [les preuves de livraison](../operations/delivery.md).

## Compte, machines et capacité réseau

1. Ouvrir `/auth`, puis `/profile` pour les informations du compte et son wallet.
2. Vérifier le wallet par le challenge et la signature du parcours existant.
3. Depuis l'espace worker, créer le code temporaire de la machine desktop.
4. Saisir ce code dans l'application installée ; la machine signe avec son
   identité persistante. Le code n'est pas un jeton de session du compte.
5. Vérifier la machine liée dans l'espace worker, puis sa présence réseau.

Les routes actuelles sont `GET /user`, `GET /user/devices`,
`POST /user/devices/pairing-code` et `POST /devices/pair`. Les trois premières
exigent la session du compte ; la dernière exige le code et les preuves de la
machine. Les codes expirent après dix minutes et ne doivent pas être conservés
dans les logs, issues ou exemples publics. Une absence de wallet vérifié
empêche la génération du code dans l'implémentation actuelle.

Le bouton d'association du pool appelle `POST /user/devices/pairing-codes` :
il cible les miniworkers configurés côté serveur, avec une autorisation distincte
par identité. Il ne s'agit pas d'un import générique de machines arbitraires.
Les volumes de miniworkers conservent identités, wallets et taskbooks ; ne pas
les supprimer pendant une mise à jour. Voir
[leurs limites sur un hôte unique](../../infra/compose/DEV_MINIWORKERS.md).

Une machine liée au compte (`/user/devices`) et un pair observé
(`GET /jobs/network/peers`) sont deux informations distinctes. Une liaison ne
prouve pas un heartbeat récent ; un pair observé ne prouve pas sa propriété
par le compte connecté. Ne pas additionner leurs compteurs comme une même liste.

## Calculs, paiements et preuve de résultat

Le parcours `/jobs` utilise le catalogue, les devis et l'API authentifiée. Lire
le détail, les fragments et le résultat avant toute finalisation. Une tâche
en `verifying` n'est pas un résultat accepté ; une attribution de vérificateur
n'est pas un vote reçu. En cas de blocage, relever l'identifiant réseau, l'état
des fragments, la version et les preuves présentes. Ne pas clôturer ou annuler
automatiquement pour rendre l'interface verte.

La configuration distingue l'activation des paiements, le cluster, le RPC,
le programme et le mint. Un prix indicatif n'est ni un montant réglé ni un
taux garanti. Un wallet SIL ne dispense pas du SOL nécessaire aux frais du
signataire actuel. L'architecture de paiement transparente envisagée dans la
roadmap ne doit pas être présentée comme déjà déployée par cette refonte.

Pour modifier programme, SDK ou logique de transaction, `./dev test --suite
solana` utilise localnet isolé, des clés jetables et un SBF identique entre
construction et tests. Un passage Devnet ou une signature utilisateur demande
une action distincte explicite. Une erreur RPC 429 ou de blockhash doit rester
visible ; ne pas basculer de cluster, de programme ou de wallet silencieusement.

## Validation à joindre à une modification de parcours

- API : `./dev test --suite api`, notamment authentification, challenge wallet,
  association single-use, autorisations du compte et erreurs HTTP.
- Web : `./dev test --suite web`, types, tests unitaires et vrais scénarios
  navigateur ; un mock réseau seul ne prouve pas le calcul distribué.
- Desktop : `node-ui`, puis `node-native`/`node-windows` selon la plateforme ;
  l'installation se qualifie séparément dans la livraison.
- Réseau : `network` et `network-integration` ; vérifier calcul et vérification
  dans les scénarios P2P, sans confondre disponibilité d'un site et celle du réseau.
- Contrat partagé : demander `dev ci plan` pour inclure les consommateurs,
  actualiser contrat, fixtures, documentation humaine et instructions IA ensemble.
