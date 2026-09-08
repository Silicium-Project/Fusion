# Calcul · Math simulation (generic)

- **Objectif** : exécuter des kernels scientifiques (PDE, optimisation, statistiques) paramétrés par un fichier JSON.
- **Entrées** : `config.json` (équations, constantes, grille), `task.bin` (données initiales).
- **Sorties** : `result.json` + `result.hash`.
- **Notes** : ce profil sert de base à des workloads plus spécifiques (Monte Carlo, FEM…). Associez un profil de vérification adapté (`verification/statistical-consistency`, etc.).
