"""Peer HTTP server: bounded threaded server, request handler and route modules.

- ``server``            bounded threading HTTP server and ``HttpServerMixin``
- ``handler``           request handler, ordered GET/POST route tables
- ``common``            JSON body parsing and response helpers
- ``routes_status``     /health, /peers, /events/*
- ``routes_discovery``  /discovery/*, /p2p/peers/register, /p2p/candidates
- ``routes_updates``    /updates/*
- ``routes_p2p``        /p2p/sessions*, /p2p/transport, /p2p/attestations, content
- ``routes_mesh``       /mesh, /gossip/publish
- ``routes_tasks``      /tasks/claim, /tasks|requests|results/dispatch
- ``routes_relay``      /relay/*
"""
