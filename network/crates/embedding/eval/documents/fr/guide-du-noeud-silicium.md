# Guide du nœud Silicium

Ce guide explique comment une machine participe au réseau de calcul Silicium.

## Installation

Le nœud s'installe avec l'application Silicium pour Windows ou Linux. Au premier lancement, l'application crée une identité unique pour la machine, conservée dans le dossier de données. Supprimer ce dossier fait apparaître la machine comme une nouvelle machine sur le réseau.

## Ressources utilisées

Par défaut, le nœud utilise au plus la moitié des cœurs du processeur et s'interrompt quand la batterie descend sous 20 %. Ces limites se règlent dans l'onglet Ressources de l'application. Le nœud ne travaille que lorsque la machine est branchée, sauf réglage contraire.

## Comment le travail est réparti

Un projet est découpé en parties indépendantes appelées fragments. Chaque fragment est calculé par une machine du réseau, puis vérifié par une autre machine qui en recalcule une partie tirée au sort. Un fragment refusé est recalculé ailleurs, et la machine fautive perd de la réputation.

## Rémunération

Chaque fragment validé rapporte des unités de calcul, enregistrées sur la blockchain Solana. Sur le réseau de démonstration, ces unités n'ont pas de valeur réelle. Les unités d'un fragment refusé ne sont pas versées.

## Réseau et pare-feu

Le nœud se connecte à l'orchestrateur et aux autres nœuds par le port TCP 46201. Il fonctionne derrière une box internet sans ouvrir de port, grâce aux relais du réseau, mais ouvrir ce port améliore les échanges entre machines.

## Confidentialité

Les machines du réseau voient les données des fragments qu'elles calculent. Il ne faut donc pas envoyer de documents confidentiels : la recherche dans les documents en avertit l'utilisateur avant l'envoi.

## Mises à jour

L'application vérifie les mises à jour au démarrage puis toutes les six heures. Une version trop ancienne ne reçoit plus de travail tant qu'elle n'est pas mise à jour.
