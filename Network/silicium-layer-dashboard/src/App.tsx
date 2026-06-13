import { useMemo, useState } from "react";
import type { Idl } from "@coral-xyz/anchor";
import { DEVNET_PROGRAM_ID, DEVNET_RPC } from "./lib/solana";
import { fetchLayerSnapshot } from "./lib/fetchLayer";
import type { LayerSnapshot } from "./lib/types";
import { StatCards } from "./components/StatCards";
import { WorkersPanel } from "./components/WorkersPanel";
import { JobsList, JobGraph } from "./components/JobGraph";
import { FragmentsPanel } from "./components/FragmentsPanel";
import { StakingPanel } from "./components/StakingPanel";

function jobSortValue(job: LayerSnapshot["jobs"][number]): number {
  if (job.createdAtUnix) return job.createdAtUnix;
  const parsed = Number(job.jobId);
  return Number.isFinite(parsed) ? parsed : 0;
}

function sortJobsNewestFirst(snapshot: LayerSnapshot): LayerSnapshot {
  return {
    ...snapshot,
    jobs: [...snapshot.jobs].sort((a, b) => jobSortValue(b) - jobSortValue(a)),
  };
}

const emptySnapshot: LayerSnapshot = {
  source: "solana",
  loadedAt: new Date().toISOString(),
  stats: {
    jobs: 0,
    fragments: 0,
    workers: 0,
    votes: 0,
    fragmentResolutions: 0,
    splitProposals: 0,
    stakingPool: 0,
    networkStakers: 0,
  },
  jobs: [],
  fragments: [],
  workers: [],
  votes: [],
  fragmentResolutions: [],
  splitProposals: [],
  networkStakers: [],
  stakingPools: [],
  events: [],
};

export default function App() {
  const [idl, setIdl] = useState<Idl | null>(null);
  const [rpcUrl, setRpcUrl] = useState(DEVNET_RPC);
  const [snapshot, setSnapshot] = useState<LayerSnapshot>(emptySnapshot);
  const [selectedJob, setSelectedJob] = useState<string | undefined>(undefined);
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
      const next = sortJobsNewestFirst(await fetchLayerSnapshot({ idl, rpcUrl, programId: DEVNET_PROGRAM_ID }));
      setSnapshot(next);
      setSelectedJob(next.jobs[0]?.pubkey);
    } catch (err: any) {
      console.error(err);
      setError(err?.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Silicium - Solana Layer</p>
          <h1>Devnet observer</h1>
          <p>
            Dashboard graphique read-only pour observer les jobs, fragments,
            sous-fragments, workers, verificateurs, reputation V2.5, votes,
            splits et staking passif du Devnet Silicium.
          </p>
        </div>
        <div className="hero-badge">
          <span>Donnees Solana Devnet</span>
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
            <input value="Devnet" readOnly />
          </label>
          <label>
            RPC URL
            <input value={rpcUrl} onChange={(e) => setRpcUrl(e.target.value)} />
          </label>
          <label>
            Program ID
            <input value={DEVNET_PROGRAM_ID} readOnly />
          </label>
          <label>
            IDL Anchor
            <input
              type="file"
              accept=".json,application/json"
              onChange={(e) => e.target.files?.[0] && loadIdlFile(e.target.files[0])}
            />
          </label>
        </div>
        <div className="actions">
          <button onClick={loadFromSolana} disabled={loading}>
            {loading ? "Chargement..." : "Charger le Devnet"}
          </button>
          <span className={idl ? "ok" : "warn"}>
            {idl ? "IDL charge" : "IDL non charge"}
          </span>
        </div>
        {error && <pre className="error-box">{error}</pre>}
      </section>

      <StatCards snapshot={snapshot} />

      <div className="main-grid">
        <JobsList jobs={snapshot.jobs} selectedJob={selectedJob} onSelect={setSelectedJob} />
        <JobGraph snapshot={snapshot} selectedJob={selectedJob} />
      </div>

      <WorkersPanel workers={snapshot.workers} />
      <FragmentsPanel fragments={selectedJobFragments} votes={snapshot.votes} resolutions={snapshot.fragmentResolutions} splits={snapshot.splitProposals} />
      <StakingPanel pools={snapshot.stakingPools} stakers={snapshot.networkStakers} />

      <section className="panel">
        <div className="panel-header">
          <h2>Events / timeline</h2>
          <span>{snapshot.events.length}</span>
        </div>
        <div className="timeline">
          {snapshot.events.map((event, index) => (
            <div className="timeline-item" key={`${event.name}-${index}`}>
              <strong>{event.name}</strong>
              <span>{event.text}</span>
            </div>
          ))}
          {!snapshot.events.length && (
            <p>
              Aucun event indexe depuis le dashboard read-only. Pour du temps reel robuste,
              ajouter plus tard un indexer Node.js qui ecoute les events Anchor et les stocke
              dans SQLite/PostgreSQL.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
