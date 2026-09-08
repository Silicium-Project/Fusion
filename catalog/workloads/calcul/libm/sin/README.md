# Workload `calcul/libm/sin`

Calcule `sin(x)` avec la précision double de la GLIBC/Libm. Le worker reçoit un
artefact JSON contenant `{"value": <float64>}` et renvoie :

- `result` : JSON `{ "value": <float64> }` (même encodage IEEE754 qu'en entrée).
- `hash` : digest BLAKE3 du tuple `(fonction, valeur, résultat)` permettant au
  scheduler de mettre en cache le calcul et de résoudre les dépendances des
  fragments ASM consommateurs.

La redondance minimale est de 2 workers afin de détecter toute divergence. Les
conteneurs peuvent être très légers (Python + `math.sin` ou implémentation C
embarquant `libm`).
