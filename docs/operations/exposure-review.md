# Revue préalable à l'ouverture publique — 25 octobre 2026

## Décision du propriétaire

Le 25 octobre 2026, après un premier report, le propriétaire a validé
l'ouverture de **Fusion uniquement**, avec ses historiques et échanges, ainsi
que le droit de publication des logos et visuels fournis. Fusion est public
depuis 18:30 UTC. Le Project 12, `planning-private` et les anciens dépôts
Network/BackEnd/FrontEnd conservent leur visibilité privée.

Les protections de `main` et des environnements précèdent la réactivation de
la qualification CI. Les workflows de livraison et de suivi restent suspendus
jusqu'à leur qualification et leur activation distinctes. Les plafonds de
dépenses restent à zéro ; aucun runner VPS n'est réinscrit.

L'ouverture rend consultables le code et ses anciennes versions, les branches
et tags Fusion, les auteurs et leurs métadonnées Git, les issues/commentaires/PR
Fusion conservés, les releases et les journaux Actions encore disponibles.
Les adresses des services, identifiants publics de programmes et clés publiques
présents dans ces contenus sont également visibles.

## Couverture et constats

| Surface | Contrôle réalisé | Résultat |
|---|---|---|
| Historiques des quatre sources | Gitleaks, toutes les références sauvegardées | Un littéral hexadécimal déterministe de test JWT, classé comme fixture ; aucune autre détection |
| Histoire monorepo importée | 1 796 commits analysés au point de référence de l'audit | Aucun secret détecté après l'exception limitée à cette fixture exacte |
| Wallets Solana | Vérification Ed25519 des tableaux de 64 octets dans les objets accessibles | Aucun keypair valide trouvé ; un test avec clé jetable vérifie le détecteur |
| LFS | Inventaire des pointeurs des objets accessibles | Aucun pointeur LFS |
| Contenus GitHub | Exports des issues, commentaires, PR, reviews, milestones et paramètres | Détections limitées à quatre `temp_clone_token` éphémères renvoyés par l'API dans les exports privés ; champs retirés de l'export et de l'outil |
| Actions Fusion | 2 854 exécutions inventoriées ; 2 532 archives de logs accessibles analysées | 54 occurrences de clé WireGuard publique et un jeton de processus de test local temporaire ; aucune clé privée identifiée |
| Logs non disponibles | 322 archives expirées ou absentes | Leur contenu n'est pas récupérable ; elles ne sont pas présentées comme analysées |
| Releases Fusion | 47 releases, 218 fichiers, environ 7,2 Gio téléchargés et contrôlés | 638 détections génériques dans des annotations/types et identifiants de dépendances Python embarquées dans les anciennes distributions ; pas de secret de déploiement identifié |
| Artefacts Actions encore présents | 8 enregistrements de build Docker, environ 0,38 Mio | Archives décompressées et analysées ; aucune détection |

Après la préparation initiale, les cinq qualifications privées accessibles
40175560939, 40176010077, 40176267805, 40179208684 et 40197099773 ont aussi été
auditées : 278 fichiers de logs, environ 5,4 Mo, aucune détection Gitleaks.
La tentative 40199389136 n'a produit aucun log de runner : ses annotations
indiquent un refus d'allocation lié à la facturation ou à la limite de dépenses.
Ces contrôles n'autorisent pas une ouverture ; tout nouveau contenu doit être
repris dans la prochaine revue d'exposition.

Avant la bascule, une nouvelle lecture de toutes les références distantes et
un contrôle au commit `65d6c27b` ont couvert **1 867 commits**, sans détection
Gitleaks ni keypair Solana valide. Le réexport courant couvre 308 entrées
d'issues (PR incluses), 106 commentaires, 140 PR et leurs revues récentes ;
aucune détection Gitleaks. Les 47 releases et leurs fichiers sont inchangés
depuis l'audit. Les références et rapports expurgés de cette vérification sont
conservés dans l'espace privé de restauration.

Les détections des distributions concernent les annotations `Ed25519PrivateKey`
et `X25519PrivateKey`, les descripteurs Protobuf générés et `win32api.RegEnumKey`.
Les archives RPM contiennent les mêmes sources dans leur CPIO. Les programmes
et installateurs n'ont pas été exécutés pour cet audit. La recherche automatisée
ne garantit pas l'absence de toute donnée personnelle ou de tout secret sous
un format non couvert ; les originaux et rapports expurgés restent privés.

## Éléments isolés

- Les 31 issues HOLD et leur hub d'arbitrage sont dans `planning-private`.
  Les six idées rédigées dans le Project restent privées. Aucun arbitrage
  définitif n'est pris et aucune issue n'est fermée par la migration.
- Le Project 12 reste privé ; son export complet n'entre pas dans Fusion.
- Les rapports internes de remédiation et l'outil local expérimental de pool
  sont conservés dans une PR privée distincte, sans dépendances générées.
- Les sauvegardes Git, patchs, fichiers non suivis, journaux bruts et exports
  restent dans la sauvegarde privée. Aucune clé privée n'est ajoutée au dépôt.

## Licences, provenance et revue du propriétaire

Les trois composants importés possèdent une licence MIT ; la racine Fusion
reprend cette licence. Les métadonnées ISC existantes du workspace Anchor et
les licences propres aux dépendances sont conservées. Une licence de racine
ne remplace pas les obligations des dépendances redistribuées.

Les maquettes et ressources graphiques sont présentes avec leurs manifestes et
prompts de génération. Le propriétaire a confirmé le droit de publication du
logo de référence et des ressources fournies lors de la validation de
l'ouverture. Les licences des dépendances et les attributions propres aux
ressources restent applicables.

## Mesures de bascule

Les anciennes Actions des quatre dépôts restent suspendues et six runners VPS
inactifs ont été désenregistrés. La CI de Fusion est réactivée séparément après
vérification des protections. L'ouverture n'autorise aucun déploiement sans
qualification, signatures et activation explicite.

Les protections publiques et les restrictions d'environnements sont appliquées
avant la CI. La migration des secrets historiques vers les environnements
protégés reste nécessaire avant la livraison. Les anciens dépôts restent privés ; leur archivage
attend la reprise des PR et des travaux actifs.

La dérive constatée entre la clé du manifeste d'auto-update du VPS et celle
épinglée dans le client est un blocage de livraison distinct. Elle doit être
résolue par restauration de la clé existante ou migration de confiance revue.
Le pipeline refuse une substitution silencieuse de cette clé.
