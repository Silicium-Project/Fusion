"""Silicium network node (legacy Python runtime), split by feature.

Entry point and compatibility facade: ``tools/network_node.py`` (re-exports
the public names below; ``python3 -m tools.network_node`` and
``python3 tools/network_node.py`` keep working).

Layout:

- ``constants``      roles, terminal statuses, release channels, defaults
- ``util``           time, ids, canonical JSON, hashing, atomic file writes
- ``config``         ``NodeConfig``, capacity snapshot, peer constraints
- ``identity``       ``NodeIdentity`` (Ed25519 keys, signatures)
- ``queue_state``    ``QueueState`` (queue cursors, idempotency set)
- ``reputation``     ``ReputationStore`` (local score, resource memory)
- ``p2p_client``     ``P2PClient`` (content fetch/put over file/peers/HTTP/IPFS)
- ``role_runtime``   ``RoleRuntime`` (executes tasks/requests per role)
- ``solana_bridge``  ``SolanaBridge`` (Node.js bridge subprocess)
- ``envelopes``      enqueue tasks/requests, ingest inline content blobs
- ``cli``            ``parse_roles``, ``build_arg_parser``, ``main``
- ``peer/``          ``PeerNetwork``: one mixin per P2P feature + ``http/`` server
- ``daemon/``        ``NetworkNode``: one mixin per daemon feature

Modules import each other with absolute ``tools.node...`` imports; the two
large classes are assembled from mixins in ``peer/network.py`` and
``daemon/node.py`` (mixins share state through ``self``).
"""
