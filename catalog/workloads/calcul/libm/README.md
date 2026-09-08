# Profils libm

Ces workloads servent de **micro-tâches mathématiques** utilisées pour satisfaire
les dépendances détectées dans les fragments ASM (ex: appels à `sin`, `exp`,
`pow`). Ils permettent au scheduler de déléguer le calcul d'une fonction pure à
un worker spécialisé, de cache le résultat et de déverrouiller les fragments
consommateurs sans relancer l'exécutable complet.

Chaque sous-dossier (`sin/`, `exp/`, …) contient un `manifest.yaml` décrivant la
commande à exécuter, les artefacts d'entrée/sortie et les garanties de
validation associées. Ajoutez une nouvelle fonction en dupliquant l'un de ces
profils puis en mettant à jour la commande et la description correspondantes.
