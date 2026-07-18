import { useEffect, useMemo, useState } from "react";

type Peer = {
  node_id: string;
  roles?: string[];
  features?: string[];
  http_base_url?: string;
  relay_capable?: boolean;
  reputation_score?: number;
  last_seen_unix?: number;
  self?: boolean;
};

type PeerSnapshot = {
  node_id?: string;
  updated_utc?: string;
  count?: number;
  peers?: Peer[];
};

const snapshotUrl = "/network-state/node.orchestrator-1.peers.json";

function shortId(value: string): string {
  return value.length > 18 ? `${value.slice(0, 9)}...${value.slice(-6)}` : value;
}

export function NetworkGraph() {
  const [snapshot, setSnapshot] = useState<PeerSnapshot>({ peers: [] });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const response = await fetch(`${snapshotUrl}?t=${Date.now()}`, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const next = (await response.json()) as PeerSnapshot;
        if (active) {
          setSnapshot(next);
          setError(null);
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : String(cause));
      }
    };
    void load();
    const timer = window.setInterval(load, 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const peers = snapshot.peers || [];
  const nodes = useMemo(() => {
    const center = { x: 50, y: 50 };
    return peers.map((peer, index) => {
      if (peer.self || peers.length === 1) return { peer, x: center.x, y: center.y };
      const angle = (index / Math.max(1, peers.length - 1)) * Math.PI * 2;
      return { peer, x: center.x + Math.cos(angle) * 32, y: center.y + Math.sin(angle) * 32 };
    });
  }, [peers]);
  const observer = nodes.find((node) => node.peer.self) || nodes[0];

  return (
    <section className="panel network-panel">
      <div className="panel-header">
        <div>
          <h2>Réseau P2P complet</h2>
          <p className="network-meta">
            {snapshot.count ?? peers.length} nœud(s) observé(s)
            {snapshot.updated_utc ? ` · dernière mise à jour ${snapshot.updated_utc}` : ""}
          </p>
        </div>
        <span className={error ? "warn" : "ok"}>{error ? `Erreur: ${error}` : "Live · 5 s"}</span>
      </div>
      <div className="network-canvas">
        <svg viewBox="0 0 100 100" role="img" aria-label="Topologie du réseau P2P">
          {observer && nodes.filter((node) => node !== observer).map((node) => (
            <line key={`edge-${node.peer.node_id}`} x1={observer.x} y1={observer.y} x2={node.x} y2={node.y} className="network-edge" />
          ))}
          {nodes.map(({ peer, x, y }) => (
            <g key={peer.node_id} transform={`translate(${x} ${y})`}>
              <circle r="7" className={peer.self ? "network-node self" : "network-node"} />
              <text y="12" textAnchor="middle" className="network-label">{shortId(peer.node_id)}</text>
              <text y="17" textAnchor="middle" className="network-role">{(peer.roles || []).join(" · ") || "peer"}</text>
            </g>
          ))}
        </svg>
      </div>
      <div className="network-peer-grid">
        {peers.map((peer) => (
          <article key={peer.node_id} className="network-peer-card">
            <strong>{peer.node_id}</strong>
            <span>{(peer.roles || []).join(", ") || "peer"}</span>
            <small>{(peer.features || []).join(" · ") || "features inconnues"}</small>
            <small>Réputation: {Math.round(peer.reputation_score ?? 0)} · {peer.relay_capable ? "relay" : "direct"}</small>
          </article>
        ))}
        {!peers.length && <p className="empty">Aucun snapshot de peer disponible.</p>}
      </div>
    </section>
  );
}
