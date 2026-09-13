# Workload `calcul/simulation/monte-carlo-pi`

Exécute un Monte Carlo borné et reproductible pour estimer π. L’entrée JSON
contient `seed` et `iterations`; le worker utilise un générateur LCG explicite
afin que deux machines puissent rejouer exactement le même calcul. La limite
maximale d’itérations est appliquée côté runtime.
