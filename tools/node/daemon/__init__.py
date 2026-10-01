"""Node daemon: the role-aware ``NetworkNode`` and its feature mixins.

``NetworkNode`` (``node.py``) is assembled from:

- ``onchain_profile``  on-chain reputation of this node and of its peers
- ``heartbeat``        heartbeat/metrics files, activity and telemetry snapshots
- ``queue``            local queue sweep and envelope status updates
- ``task_control``     signed cancel/expire controls
- ``receipts``         signed compute receipts and verifier attestations
- ``performance``      performance block of task results
- ``progress``         progress monitor of the running task
- ``reconcile``        orphaned running/dispatched task reconciliation
- ``task_snapshots``   queue telemetry and its cache
- ``handling``         end-to-end execution of one envelope
- ``execution``        task/request bodies, retries, reputation updates
- ``dispatch``         remote dispatch and result return/ingestion
- ``claims``           scheduler side of pull-based claims
- ``pull_loop``        worker side of pull-based claims
- ``onchain``          on-chain submission of outcomes
"""

from tools.node.daemon.node import NetworkNode

__all__ = ["NetworkNode"]
