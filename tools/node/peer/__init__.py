"""Peer-to-peer layer of a Silicium node.

``PeerNetwork`` (``network.py``) is assembled from one mixin per feature:

- ``peer_table``        peer book: record, merge, load, prune, snapshot
- ``routing``           shortest-path route table over attested links
- ``candidates``        NAT traversal candidates (host / server-reflexive)
- ``attestations``      signed transport-path attestations
- ``signaling``         rendezvous signaling sessions (server side)
- ``signaling_client``  signaling sessions (client side, ICE content sessions)
- ``announce``          local profile and peer/candidate announcements
- ``updates``           software update announcements and content
- ``gossip``            signed event publication and fan-out
- ``content``           content-addressed fetch/replication between peers
- ``direct``            direct ICE/UDP sessions and relayed UDP punching
- ``handshake``         signed session handshakes with replay protection
- ``selection``         peer filtering and scoring for dispatch
- ``messages``          UDP listener and inbound mesh message dispatch
- ``sync``              anti-entropy loop and discovery registration
- ``addressing``        advertised addresses and target parsing
- ``security``          message signatures, mesh HMAC, signed HTTP auth
- ``http``              the peer HTTP server and its routes
"""

from tools.node.peer.network import PeerNetwork

__all__ = ["PeerNetwork"]
