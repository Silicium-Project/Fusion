import { useMemo, useState } from "react";
import type { Idl } from "@coral-xyz/anchor";
import { DEVNET_PROGRAM_ID, DEVNET_RPC, LOCALNET_RPC } from "./lib/solana";
import { fetchLayerSnapshot } from "./lib/fetchLayer";
import { demoSnapshot } from "./lib/demo";
import type { LayerSnapshot } from "./lib/types";
import { StatCards } from "./components/StatCards";
import { WorkersPanel } from "./components/WorkersPanel";
import { JobsList, JobGraph } from "./components/JobGraph";
import { FragmentsPanel } from "./components/FragmentsPanel";
import { StakingPanel } from "./components/StakingPanel";
import { NetworkGraph } from "./components/NetworkGraph";

export default function App() {
  const [idl, setIdl] = useState<Idl | null>(null);
  const [rpcUrl, setRpcUrl] = useState(DEVNET_RPC);
  const [programId, setProgramId] = useState(DEVNET_PROGRAM_ID);
  const [snapshot, setSnapshot] = useState<LayerSnapshot>(demoSnapshot);
  const [selectedJob, setSelectedJob] = useState<string | undefined>(demoSnapshot.jobs[0]?.pubkey);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedJobFragments = useMemo(() => {
    if (!selectedJob) return snapshot.fragments;
    return snapshot.fragments.filter((f) => f.job === selectedJob);
  }, [snapshot.fragments, selectedJob]);

  async function loadIdlFile(file: File) {
    const text = await file.text();
    const parsed = JSON.parse(text);
    setIdl(parsed);
  }

  async function loadFromSolana() {
    if (!idl) {
      setError("Charge d'abord l'IDL Anchor target/idl/solana_layer.json.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const next = await fetchLayerSnapshot({ idl, rpcUrl, programId });
      setSnapshot(next);
      setSelectedJob(next.jobs[0]?.pubkey);
    } catch (err: any) {
      console.error(err);
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  function loadDemo() {
    setSnapshot(demoSnapshot);
    setSelectedJob(demoSnapshot.jobs[0]?.pubkey);
    setError(null);
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Silicium · Solana Layer</p>
          <h1>Blockchain visualizer</h1>
          <p>
            Dashboard graphique pour observer les jobs, fragments, sous-fragments, workers,
            vérificateurs, réputation V2.5, votes, splits et staking passif.
          </p>
        </div>
        <div className="hero-badge">
          <span>{snapshot.source === "demo" ? "Mode démo" : "Données Solana"}</span>
          <strong>{new Date(snapshot.loadedAt).toLocaleTimeString()}</strong>
        </div>
      </header>

      <section className="panel connector">
        <div className="panel-header">
          <h2>Connexion</h2>
          <span>read-only</span>
        </div>
        <div className="connector-grid">
          <label>
            Cluster
            <select
              value={rpcUrl === DEVNET_RPC ? "devnet" : rpcUrl === LOCALNET_RPC ? "localnet" : "custom"}
              onChange={(e) => {
                if (e.target.value === "devnet") setRpcUrl(DEVNET_RPC);
                if (e.target.value === "localnet") setRpcUrl(LOCALNET_RPC);
              }}
            >
              <option value="devnet">Devnet</option>
              <option value="localnet">Localnet</option>
              <option value="custom">Custom RPC</option>
            </select>
          </label>
          <label>
            RPC URL
            <input value={rpcUrl} onChange={(e) => setRpcUrl(e.target.value)} />
          </label>
          <label>
            Program ID
            <input value={programId} onChange={(e) => setProgramId(e.target.value)} />
          </label>
          <label>
            IDL Anchor
            <input type="file" accept=".json,application/json" onChange={(e) => e.target.files?.[0] && loadIdlFile(e.target.files[0])} />
          </label>
        </div>
        <div className="actions">
          <button onClick={loadFromSolana} disabled={loading}>{loading ? "Chargement..." : "Charger depuis Solana"}</button>
          <button className="secondary" onClick={loadDemo}>Revenir à la démo</button>
          <span className={idl ? "ok" : "warn"}>{idl ? "IDL chargé" : "IDL non chargé"}</span>
        </div>
        {error && <pre className="error-box">{error}</pre>}
      </section>

      <StatCards snapshot={snapshot} />
      <NetworkGraph />

      <div className="main-grid">
        <JobsList jobs={snapshot.jobs} selectedJob={selectedJob} onSelect={setSelectedJob} />
        <JobGraph snapshot={snapshot} selectedJob={selectedJob} />
      </div>

      <WorkersPanel workers={snapshot.workers} />
      <FragmentsPanel fragments={selectedJobFragments} votes={snapshot.votes} splits={snapshot.splitProposals} />
      <StakingPanel pools={snapshot.stakingPools} stakers={snapshot.networkStakers} />

      <section className="panel">
        <div className="panel-header"><h2>Events / timeline</h2><span>{snapshot.events.length}</span></div>
        <div className="timeline">
          {snapshot.events.map((event, index) => (
            <div className="timeline-item" key={`${event.name}-${index}`}>
              <strong>{event.name}</strong>
              <span>{event.text}</span>
            </div>
          ))}
          {!snapshot.events.length && (
            <p>
              Aucun event indexé dans ce mode. Pour du temps réel robuste, ajoute plus tard un
              indexer Node.js qui écoute les events Anchor et les stocke dans SQLite/PostgreSQL.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
