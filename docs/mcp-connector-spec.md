# Connecteur MCP

Le serveur MCP (`tools/mcp_server.py`) fournit une surface d'observation et de
contrôle limitée pour les outils internes. Il ne remplace pas l'API HTTP
versionnée de `silicium-node`, qui est la source de vérité pour les tâches
actives.

## Responsabilités

- publier des ressources de statut, rapports, résultats, tâches et métriques ;
- appliquer une authentification Bearer et des listes d'autorisation ;
- exposer des actions explicitement permises, sans passage direct de commandes
  shell ;
- masquer les données sensibles dans les journaux et les exports.

Les consommateurs applicatifs utilisent l'API de contrôle Rust :

- `POST /v1/tasks` pour soumettre une tâche ;
- `GET /v1/tasks` pour son suivi ;
- `POST /v1/workloads/{root_job_id}/cancel` pour l'annulation ;
- `GET /v1/peers` pour l'observation du réseau.

Le détail de ce contrat est dans [node-control-api.md](node-control-api.md).
MCP reste adapté aux opérations et à l'observation ; il ne doit pas recréer un
second protocole de planification ni dépendre des anciens artefacts C++.
