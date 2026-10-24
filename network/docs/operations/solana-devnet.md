# Connexion Solana Devnet et rémunération

Le programme de référence est `64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG`.
L'ancien programme `A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2` reste présent
sur Devnet, mais ses comptes ne sont pas migrés vers cette nouvelle adresse.
Les nouveaux clients doivent cibler le nouveau programme après confirmation de
son déploiement on-chain.

Les keypairs de déploiement sont conservées hors du dépôt, dans
`~/.config/solana/silicium-devnet-program-id.json` et
`~/.config/solana/silicium-devnet-upgrade-candidate.json` (permissions `0600`,
répertoire `~/.config/solana` en `0700`). Ne jamais les copier dans les sources,
les artefacts CI ou le VPS. Les adresses publiques sont respectivement
`64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG` et
`TzkEJNsTVA2Z9E39dLHuyHpMkUz9WLiD6VRPhkjz8Fs`.

Le contrôle sans écriture est reproductible depuis la racine de Network :

```bash
python3 tools/dev/release/solana_devnet_preflight.py --json
```

Il vérifie via RPC que le compte du programme existe et est exécutable. Le
bridge et le script Anchor recherchent ensuite l’IDL localement puis sur
Devnet, ce qui évite de dépendre d’un `target/idl` présent dans l’image.

Pour exécuter le flux d’écriture complet, il faut un wallet Devnet financé et
les dépendances JavaScript installées :

```bash
cd solana-layer
npm install --no-package-lock
npx ts-node scripts/devnet_minimal_job_flow.ts
```

Le flux crée une mint de test, enregistre et stake un worker de calcul et deux
verifiers, soumet un fragment, vote, réclame les récompenses des verifiers,
puis finalise le job. La sortie contient les signatures de chaque transaction,
les comptes impliqués et le compte `JobResult` finalisé.

## Trace blockchain des jobs

Ce flux complet reste un test du programme. Les jobs du site sont tracés plus
simplement par le BackEnd (`internal/chainproof`) lorsque
`SILICIUM_DEVNET_TRACE=1` :

1. le nœud Rust écrit dans le résumé du job, pour chaque tâche, sa trace signée
   du task book (`fragments[].trace` : worker, vérificateurs, hash des
   événements ; voir `docs/contracts/backend-files.md`) ;
2. à la fin du job, le BackEnd calcule une feuille par tâche terminée
   (SHA-256 de `0x00` + JSON canonique), la racine de Merkle (nœuds internes
   SHA-256 de `0x01` + gauche + droite) et l'empreinte du résultat final ;
3. il envoie **une** transaction Memo signée par `SILICIUM_SOLANA_WALLET`
   sur `SILICIUM_SOLANA_RPC`, avec le texte
   `silicium.job-proof.v1 job=<id> tasks=<n> root=<racine> final=<sha256>` ;
4. il écrit `devnet-trace.json` à côté du résumé (feuilles et preuves de
   Merkle de chaque tâche), que la page du job affiche. Le bouton « Vérifier
   depuis la blockchain » relit la transaction sur Solana et recalcule chaque
   preuve dans le navigateur.

Un échec d'ancrage (portefeuille absent ou vide, RPC injoignable) ne fait
jamais échouer le job : la trace passe en `failed` avec la raison. Le
portefeuille doit avoir quelques milliers de lamports par job (frais d'une
transaction, pas de compte créé).
