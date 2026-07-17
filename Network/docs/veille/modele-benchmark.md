# Modèle de benchmark reproductible

Dupliquer cette fiche pour chaque comparaison. Conserver les résultats bruts dans
un sous-dossier daté, sans les retoucher manuellement.

## Identification

- **Date et heure :**
- **Auteur :**
- **Question mesurée :**
- **Hypothèse :**
- **Commit / branche :**
- **Scénario ou workload :**

## Environnement

- **OS et version :**
- **CPU / nombre de cœurs :**
- **RAM :**
- **Versions Solana / Anchor / Node / Python :**
- **Nombre de nœuds :**
- **Réseau :** localnet, Devnet ou autre ; latence connue :
- **Variables de configuration pertinentes :**

## Protocole

- **Commande exacte :**
- **Données d'entrée :**
- **Échauffement :**
- **Nombre de répétitions :** au minimum 5, idéalement 20 ou plus.
- **Métriques :** durée murale, CPU, mémoire, débit, latence p50/p95, taux d'échec.
- **Facteurs maintenus constants :**

## Résultats bruts

| Variante | Essai | Durée (s) | CPU (s) | RSS max (KiB) | Débit | Erreurs | Trace |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Avant | 1 | | | | | | |
| Après | 1 | | | | | | |

## Synthèse

- **Médiane avant :**
- **Médiane après :**
- **Variation :** `(après - avant) / avant × 100` ; préciser si une baisse est
  meilleure pour la métrique.
- **Dispersion / valeurs aberrantes :**
- **Conclusion :** confirmée, infirmée ou non concluante.
- **Limites :** biais, bruit réseau, taille d'échantillon, environnement partagé.
- **Décision et lien vers issue/PR/commit :**

## Règles d'interprétation

- Ne pas comparer des machines, versions ou données d'entrée différentes sans le
  signaler explicitement.
- Ne pas retenir uniquement le meilleur essai.
- Ne pas confondre un seuil dans `performance-budgets.json` avec une mesure réelle.
- Publier aussi les résultats négatifs ou non concluants.
- Retirer les clés privées, tokens RPC et informations personnelles des traces.

