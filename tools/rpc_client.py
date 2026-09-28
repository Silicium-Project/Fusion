"""Legacy ZeroMQ RPC client for the local control plane (see proto/silicium_rpc.proto)."""
from __future__ import annotations
import uuid
import zmq
try:  # Works both as ``tools.rpc_client`` and as the legacy script module.
    from .rpc_protocol import decode_response, encode_request
except ImportError:  # pragma: no cover - exercised by standalone tooling
    from rpc_protocol import decode_response, encode_request


class RpcClient:
    def __init__(self, endpoint: str, token: str = "", timeout_ms: int = 3000):
        self.endpoint, self.token, self.timeout_ms = endpoint, token, timeout_ms

    def call(self, method: str, payload: object = None) -> object:
        ctx = zmq.Context(); sock = ctx.socket(zmq.DEALER); sock.setsockopt(zmq.RCVTIMEO, self.timeout_ms); sock.setsockopt(zmq.SNDTIMEO, self.timeout_ms); sock.connect(self.endpoint)
        try:
            sock.send(encode_request(method, payload or {}, uuid.uuid4().hex, self.token))
            msg, data = decode_response(sock.recv())
            if not msg.ok: raise RuntimeError(str(msg.error))
            return data
        finally: sock.close(0); ctx.term()
