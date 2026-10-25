# Anchor — programme et tests localnet isolés

Ce composant fait partie du monorepo Fusion. Exécuter les commandes depuis la racine.

```sh
./dev doctor --profile solana
./dev ci plan --base origin/main --head HEAD --json
./dev test --suite solana
```

Voir les [instructions locales](AGENTS.md), la [carte](../../docs/architecture/monorepo.md)
et les [procédures communes](../../docs/ai/README.md). Les anciens README sont
conservés dans `docs/archive/pre-monorepo-components/` ; leurs commandes antérieures
à la migration ne sont pas des procédures actuelles.
