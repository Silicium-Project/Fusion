# Workload `calcul/math/matrix-multiply`

Multiplie deux matrices denses JSON de forme `{ "a": [[...]], "b": [[...]] }`.
Les dimensions sont bornées côté worker pour éviter qu’une tâche non fiable ne
consomme toute la mémoire. Le kernel est déterministe et produit un résultat
JSON hashable, ce qui permet une vérification indépendante.
