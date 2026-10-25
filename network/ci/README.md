# CI du réseau Rust

Depuis la racine Fusion : `./dev test --suite network`, puis
`./dev test --suite network-integration`. Le registre commun est
`tools/config/lanes.json` ; GitHub appelle les mêmes commandes.

`e2e.sh` compile une seule fois les binaires release puis lance les scénarios
Rust (raytracer à un et deux workers, SHA-256). Les mêmes binaires sont
collectés pour la livraison Linux. Le support WASM a sa suite ciblée
`network-wasm` et sa campagne complémentaire.

Les scripts de réparation des runners persistants ont été retirés. Une
corruption de cache sur un runner GitHub éphémère reste un échec explicite ;
les caches ne contiennent ni wallets ni données utilisateur. Les anciens
scripts et leur historique restent accessibles dans les commits antérieurs.

Il n'existe plus de CI sur le VPS applicatif. Voir
[les instructions communes](../../docs/ai/README.md).
