"""Small protobuf runtime used by the local ZeroMQ control plane.

The project intentionally does not commit generated Python code: descriptors
are built from the stable schema at import time, which keeps node upgrades
backwards compatible and avoids a protoc build step on Windows nodes.
"""
from __future__ import annotations

import json
from google.protobuf import descriptor_pb2, descriptor_pool, message

try:
    from google.protobuf.message_factory import GetMessageClass as _get_message_class
except ImportError:
    from google.protobuf.message_factory import MessageFactory

    _MESSAGE_FACTORY = MessageFactory()

    def _get_message_class(descriptor):
        return _MESSAGE_FACTORY.GetPrototype(descriptor)


def _classes():
    file = descriptor_pb2.FileDescriptorProto(
        name="silicium_rpc.proto", package="silicium.rpc", syntax="proto3"
    )
    req = file.message_type.add(name="RpcRequest")
    for num, name, typ in ((1, "schema_version", 13), (2, "request_id", 9), (3, "method", 9), (4, "payload_json", 12), (5, "bearer_token", 9)):
        field = req.field.add(name=name, number=num, label=1, type=typ)
    resp = file.message_type.add(name="RpcResponse")
    for num, name, typ in ((1, "schema_version", 13), (2, "request_id", 9), (3, "ok", 8), (4, "payload_json", 12), (5, "error", 9), (6, "duration_us", 4)):
        resp.field.add(name=name, number=num, label=1, type=typ)
    pool = descriptor_pool.Default()
    try:
        pool.Add(file)
    except Exception:
        pass
    return _get_message_class(pool.FindMessageTypeByName("silicium.rpc.RpcRequest")), _get_message_class(pool.FindMessageTypeByName("silicium.rpc.RpcResponse"))


RpcRequest, RpcResponse = _classes()


def encode_request(method: str, payload: object, request_id: str, token: str = "") -> bytes:
    msg = RpcRequest(schema_version=1, request_id=request_id, method=method, payload_json=json.dumps(payload, separators=(",", ":")).encode(), bearer_token=token)
    return msg.SerializeToString()


def decode_request(raw: bytes) -> tuple[message.Message, object]:
    msg = RpcRequest.FromString(raw)
    payload = json.loads(bytes(msg.payload_json) or b"{}")
    return msg, payload


def encode_response(request_id: str, ok: bool, payload: object = None, error: str = "", duration_us: int = 0) -> bytes:
    msg = RpcResponse(schema_version=1, request_id=request_id, ok=ok, payload_json=json.dumps(payload if payload is not None else {}, separators=(",", ":")).encode(), error=error, duration_us=max(0, int(duration_us)))
    return msg.SerializeToString()


def decode_response(raw: bytes) -> tuple[message.Message, object]:
    msg = RpcResponse.FromString(raw)
    return msg, json.loads(bytes(msg.payload_json) or b"{}")
