# ADR-0001 — Runtimes IA sur la machine de l'utilisateur

- Statut : accepté (23/10/2026)
- Décideurs : Thom (avec l'audit du 23/10/2026)

## Contexte
La règle de langage du projet impose Rust pour tout ce qui s'exécute chez l'utilisateur.
Aujourd'hui, l'app desktop fait tourner trois moteurs d'IA chez le volontaire :
- candle (Rust) pour l'embedding (recherche dans des documents) ;
- Ollama (binaire téléchargé, épinglé par hash) pour le traitement IA ;
- `apps/silicium-ai-runtime` (Python 3.12 via `uv`, `torch`, `transformers`) pour le catalogue
  Hugging Face. Ce dernier pèse plusieurs Go, n'est pas testé en CI et n'est pas isolé au niveau de l'OS.

## Décision
1. Le catalogue Hugging Face devient une **option expérimentale, désactivée par défaut** dans l'app
   et masquée sur le canal prod, tant qu'il dépend de Python.
2. `apps/silicium-ai-runtime` est la **seule exception** autorisée à la règle « Rust chez l'utilisateur ».
   Aucun autre code Python, Node.js ou interpréteur n'est ajouté côté utilisateur ou serveur.
3. Le runtime Python reste épinglé par hash (`--require-hashes`) et doit être testé en CI
   (pytest, variante CPU) avant d'être réactivé par défaut.
4. Le portage vers candle ou ort est planifié après la démo (jalon M4). L'exception prend fin à ce moment.

## Conséquences
- Périmètre de démo : raytracer, sha256, recherche dans des documents (candle), traitement IA (Ollama).
- La documentation ne doit plus affirmer « aucun Python chez l'utilisateur » sans mentionner cette exception.
- Tout ajout de paquet lourd au runtime Python passe par une mise à jour de cet ADR.
