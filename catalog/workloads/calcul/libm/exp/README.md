# Workload `calcul/libm/exp`

Calcule l'exponentielle `exp(x)` (double précision). Entrée et sortie suivent le
même format JSON que les autres workloads libm :

- `value` : nombre flottant encodé en texte JSON.
- `result` : JSON contenant le résultat numérique.
- `hash` : digest BLAKE3 pour prouver la valeur retournée et activer le cache du
  scheduler.

Ce profil est utilisé par le backend lorsqu'un fragment ASM dépend d'un appel à
`exp@plt` (ou toute équivalence). Le runner peut être un simple script Python
`math.exp` ou une implémentation C statique.
