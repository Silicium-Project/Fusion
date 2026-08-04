#!/usr/bin/env python3
"""
Diagnostic Tool: UDP Hole Punching & STUN/NAT Traversal Inspector (Brique 1)
-----------------------------------------------------------------------------
Standalone CLI utility to inspect local network interfaces, query STUN/observe
server-reflexive addresses, send UDP punch probes, and classify NAT behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

# Import Network Node identity & json utilities
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.network_node import NodeIdentity, stable_json


def get_local_interfaces() -> list[dict[str, Any]]:
    interfaces: list[dict[str, Any]] = []
    try:
        hostname = socket.gethostname()
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            ip = sockaddr[0]
            family_str = "ipv6" if family == socket.AF_INET6 else "ipv4"
            if not any(item["ip"] == ip for item in interfaces):
                is_loopback = ip in ("127.0.0.1", "::1")
                is_private = ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172.") or ip.startswith("fe80:")
                interfaces.append(
                    {
                        "ip": ip,
                        "family": family_str,
                        "private": is_private,
                        "loopback": is_loopback,
                        "source": "hostname",
                    }
                )
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        default_ip = s.getsockname()[0]
        s.close()
        if not any(item["ip"] == default_ip for item in interfaces):
            interfaces.append(
                {
                    "ip": default_ip,
                    "family": "ipv4",
                    "private": default_ip.startswith("10.") or default_ip.startswith("192.168.") or default_ip.startswith("172."),
                    "loopback": False,
                    "source": "default-route",
                }
            )
    except Exception:
        pass

    return interfaces


def query_http_observe(target_url: str, mesh_key: str = "demo-mesh") -> dict[str, Any] | None:
    endpoint = target_url.rstrip("/") + "/discovery/observe"
    headers = {"User-Agent": "Silicium-UDP-Diagnose/1.0"}
    if mesh_key:
        headers["Authorization"] = f"Bearer {mesh_key}"
    try:
        req = urllib.request.Request(endpoint, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as err:
        print(f"  - Warning: HTTP observe query to {endpoint} failed: {err}")
    return None


def test_udp_probe(
    target_host: str,
    target_port: int,
    bind_port: int = 0,
    mesh_key: str = "demo-mesh",
    identity: NodeIdentity | None = None,
    timeout_s: float = 3.0,
) -> dict[str, Any]:
    if identity is None:
        import tempfile
        from tools import network_node
        tmp = network_node.Path(tempfile.mkdtemp(prefix="silicium-diag-"))
        args = network_node.build_arg_parser().parse_args(["--export-dir", str(tmp), "--node-id", "diag-client"])
        export_dir = network_node.Path(args.export_dir).expanduser().resolve()
        state_dir = export_dir / "node-state" / "diag-client"
        cfg = network_node.NodeConfig(
            export_dir=export_dir,
            roles=network_node.parse_roles(args.roles),
            node_id="diag-client",
            idle_ms=250,
            once=False,
            max_items=0,
            p2p_gateway="http://127.0.0.1:5001",
            state_dir=state_dir,
            solana_enable=False,
            solana_rpc="",
            solana_program_id="",
            solana_wallet="",
            solana_bridge=export_dir,
            solana_timeout_s=45,
            max_retries=2,
            worker_binary="",
            worker_mode="emu",
            bootstrap_worker=False,
            gossip_enable=True,
            gossip_bind="0.0.0.0",
            gossip_port=0,
            peer_http_bind="0.0.0.0",
            peer_http_port=0,
            peer_advertise_host="",
            peer_advertise_port=0,
            gossip_advertise_host="",
            gossip_advertise_port=0,
            seed_peers=[],
            mesh_key="demo-mesh",
            peer_sync_interval_s=1,
            peer_event_limit=10,
            peer_stale_after_s=30,
            relay_enable=False,
            relay_hops=1,
            identity_key_path=state_dir / "ed25519.pem",
            reputation_score=100.0,
            replication_factor=1,
            replication_quorum=1,
            discovery_seeds=[],
            discovery_sync_interval_s=5,
            remote_dispatch_enable=True,
            remote_dispatch_limit=3,
            pull_tasks_enable=False,
            pull_tasks_interval_s=2,
            nat_punch_enable=True,
            solana_reputation_enable=False,
            solana_reputation_refresh_s=30,
            scheduler_onchain_weight=1.0,
            scheduler_offchain_weight=1.0,
            scheduler_capacity_weight=0.01,
        )
        identity = NodeIdentity(cfg)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout_s)

    bound_port = bind_port
    try:
        sock.bind(("0.0.0.0", bind_port))
        bound_port = sock.getsockname()[1]
    except OSError:
        sock.bind(("0.0.0.0", 0))
        bound_port = sock.getsockname()[1]

    probe_payload = {
        "schema_version": 1,
        "message_type": "punch_probe",
        "session_id": "diag-session-001",
        "peer_id": "diag-client",
        "node_id": "diag-client",
        "identity_id": identity.identity_id,
        "public_key": identity.public_key_b64,
        "timestamp_unix": int(time.time()),
        "target_host": target_host,
        "target_port": target_port,
    }

    # Sign unsigned fields
    unsigned = dict(probe_payload)
    if mesh_key:
        unsigned["mesh_mac"] = hmac.new(mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    probe_payload["signature"] = identity.sign_bytes(stable_json(unsigned).encode("utf-8"))
    if mesh_key:
        probe_payload["mesh_mac"] = hmac.new(mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()

    raw_bytes = json.dumps(probe_payload, separators=(",", ":")).encode("utf-8")

    sent_time = time.monotonic()
    rtt_ms = None
    received_data = None
    sender_addr = None

    try:
        sock.sendto(raw_bytes, (target_host, target_port))
        data, addr = sock.recvfrom(65536)
        rtt_ms = (time.monotonic() - sent_time) * 1000.0
        received_data = data.decode("utf-8", errors="replace")
        sender_addr = addr
    except socket.timeout:
        pass
    except Exception as err:
        print(f"  - Socket error sending probe to {target_host}:{target_port}: {err}")
    finally:
        sock.close()

    return {
        "target_host": target_host,
        "target_port": target_port,
        "bound_port": bound_port,
        "rtt_ms": rtt_ms,
        "received": received_data is not None,
        "sender_addr": sender_addr,
        "response_preview": received_data[:100] if received_data else None,
    }


def print_banner() -> None:
    print("=" * 70)
    print(" [SILICIUM P2P NETWORK DIAGNOSTIC TOOL - BRIQUE 1]")
    print(" NAT Traversal & UDP Hole Punching Inspector")
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Silicium UDP Hole Punching & NAT Diagnostic Tool")
    parser.add_argument("--target", default="http://213.32.68.67:46100", help="Target orchestrator HTTP URL or IP:port")
    parser.add_argument("--udp-host", default="213.32.68.67", help="Target UDP host for probe test")
    parser.add_argument("--udp-port", type=int, default=46100, help="Target UDP port for probe test")
    parser.add_argument("--bind-port", type=int, default=46101, help="Local UDP bind port to test")
    args = parser.parse_args()

    print_banner()

    print("\n[1/4] Inspecting Local Network Interfaces...")
    interfaces = get_local_interfaces()
    for iface in interfaces:
        kind = "LOOPBACK" if iface["loopback"] else ("PRIVATE LAN" if iface["private"] else "PUBLIC/ROUTABLE")
        print(f"  - Interface [{iface['family'].upper()}] : {iface['ip']:<40} ({kind}, via {iface['source']})")

    print("\n[2/4] Querying Server-Reflexive (STUN/Observe) Address from Target...")
    observe_data = query_http_observe(args.target)
    srflx_ip = None
    if observe_data:
        srflx_ip = observe_data.get("observed_ip")
        node_id = observe_data.get("node_id")
        print(f"  - Target Node ID   : {node_id}")
        print(f"  - Observed Public IP: {srflx_ip}")
    else:
        print("  - Could not query /discovery/observe from target HTTP server.")

    print(f"\n[3/4] Testing UDP Socket Binding & Probe to {args.udp_host}:{args.udp_port}...")
    probe_result = test_udp_probe(args.udp_host, args.udp_port, bind_port=args.bind_port)
    print(f"  - Local UDP Bind Port : {probe_result['bound_port']}")
    if probe_result["received"]:
        print(f"  - Probe Status        : [OK] ACK RECEIVED in {probe_result['rtt_ms']:.2f} ms")
        print(f"  - Sender Address      : {probe_result['sender_addr']}")
        print(f"  - Payload Preview     : {probe_result['response_preview']}")
    else:
        print(f"  - Probe Status        : [TIMEOUT] (No direct UDP packet back from {args.udp_host}:{args.udp_port})")

    print("\n[4/4] Connectivity & NAT Behavior Analysis:")
    if probe_result["received"]:
        print("  [OK] DIRECT UDP CONNECTIVITY CONFIRMED!")
        print("  - Your local NAT router passes outbound & inbound UDP datagrams freely.")
    elif srflx_ip and srflx_ip != "127.0.0.1":
        print("  [WARN] RESTRICTED NAT / STUN ACTIVE:")
        print(f"  - Your router mapped your internal IP to Public IP {srflx_ip}.")
        print("  - Direct UDP probe timed out because target hasn't punched back or firewall blocked uninvited UDP.")
        print("  - RECOMMENDED ACTION: Ensure symmetric probe exchange (both peers send probes simultaneously).")
    else:
        print("  [FAIL] STRICT FIREWALL / NAT SYMMETRIC DETECTED:")
        print("  - UDP traffic appears blocked or severely restricted by router firewall.")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
