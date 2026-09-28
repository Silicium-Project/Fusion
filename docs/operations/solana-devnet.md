# Connexion Solana Devnet et rémunération

Le programme de référence est `A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2`.
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

Le backend ne lance pas ces écritures par défaut. Après configuration de
`SILICIUM_SOLANA_WALLET`, `SILICIUM_SOLANA_RPC` et du programme canonique,
activer explicitement `SILICIUM_DEVNET_TRACE=1`. Le script de trace lie alors
le hash du rendu réassemblé au fragment on-chain et exige
`reconciliation.hash_match=true` avant de déclarer le job réussi.
