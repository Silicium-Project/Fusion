# Contrats aux frontières du runtime Rust

Le runtime actif est le workspace Rust de `network`. Les anciens modules Python
`networked`, TUI, MCP, ZeroMQ et leurs interfaces `I*` sont historiques.

Les frontières maintenues sont le protocole P2P signé, les références de contenu,
les workloads, le contrôle HTTP authentifié, la persistance et les instructions
Solana. Elles ont des contrats versionnés et des fixtures ; leurs consommateurs
doivent être qualifiés ensemble en cas d'évolution incompatible.

Utiliser un trait Rust lorsqu'il permet une substitution réelle ou isole une
dépendance externe pour ses tests. Une structure concrète convient aux chemins
internes qui n'ont qu'une implémentation. Ne pas créer une interface sur la seule
base d'une possibilité future. Les noms suivent les conventions du langage.

Voir la [carte du monorepo](../../../docs/architecture/monorepo.md) et les
[instructions du réseau](../../AGENTS.md). Aucun changement de politique CI ne
réduit les conditions de validation du protocole.
