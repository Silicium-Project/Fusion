# Revue préalable à l'ouverture publique — 25 octobre 2026

## Décision attendue

Fusion est encore privé. L'ouverture n'est pas appliquée par les scripts de
protection. Le propriétaire doit valider ce rapport, notamment la publication
des historiques, commentaires et visuels, avant le changement de visibilité.

L'ouverture rendra consultables le code et ses anciennes versions, les branches
et tags Fusion, les auteurs et leurs métadonnées Git, les issues/commentaires/PR
Fusion conservés, les releases et les journaux Actions encore disponibles.
Les adresses des services, identifiants publics de programmes et clés publiques
présents dans ces contenus seront également visibles.

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
prompts de génération. Le logo de référence et les ressources fournies au
projet demandent confirmation de provenance par le propriétaire avant leur
publication. L'audit n'attribue pas de droits nouveaux sur ces ressources.

## Mesures de bascule

Les anciennes Actions des quatre dépôts sont suspendues et six runners VPS
inactifs ont été désenregistrés. Les services dev répondent toujours aux
contrôles de santé. Les nouveaux workflows ne s'exécutent que sur un dépôt
public ; la livraison exige en plus une activation explicite.

Après validation : appliquer les protections publiques, restreindre les
environnements et traiter les secrets historiques avant de réactiver les
workflows qualifiés. Les anciens dépôts restent privés ; leur archivage
attend la reprise des PR et des travaux actifs.

La dérive constatée entre la clé du manifeste d'auto-update du VPS et celle
épinglée dans le client est un blocage de livraison distinct. Elle doit être
résolue par restauration de la clé existante ou migration de confiance revue.
Le pipeline refuse une substitution silencieuse de cette clé.
