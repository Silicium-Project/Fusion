import { Background, Controls, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import type { FragmentView, JobView, LayerSnapshot, WorkerView } from "../lib/types";
import { shortKey } from "../lib/solana";

const statusClass: Record<string, string> = {
  available: "node-gray",
  claimed: "node-blue",
  submitted: "node-yellow",
  verified: "node-green",
  rejected: "node-red",
  splitParent: "node-purple",
  finalized: "node-green",
  open: "node-blue",
};

function makeNode(id: string, label: string, subtitle: string, x: number, y: number, status = "unknown"): Node {
  return {
    id,
    position: { x, y },
    data: { label: <div><strong>{label}</strong><span>{subtitle}</span></div> },
    className: `graph-node ${statusClass[status] || "node-gray"}`,
  };
}

function fragmentLabel(f: FragmentView): string {
  return f.parentFragment ? `Sub-fragment ${f.fragmentIndex}` : `Fragment ${f.fragmentIndex}`;
}

export function JobGraph({ snapshot, selectedJob }: { snapshot: LayerSnapshot; selectedJob?: string }) {
  const job = snapshot.jobs.find((j) => j.pubkey === selectedJob) || snapshot.jobs[0];
  if (!job) {
    return <section className="panel empty">Aucun job à afficher.</section>;
  }

  const fragments = snapshot.fragments
    .filter((f) => f.job === job.pubkey)
    .sort((a, b) => a.fragmentIndex - b.fragmentIndex);
  const workersByKey = new Map(snapshot.workers.map((w) => [w.pubkey, w]));
  const votesByFragment = new Map<string, number>();
  for (const vote of snapshot.votes) {
    votesByFragment.set(vote.fragment, (votesByFragment.get(vote.fragment) || 0) + 1);
  }

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  nodes.push(makeNode(`job-${job.pubkey}`, `Job ${job.jobId || shortKey(job.pubkey)}`, `${job.status} · ${job.verifiedFragments}/${job.expectedFragments}`, 0, 0, job.status));

  const roots = fragments.filter((f) => !f.parentFragment);
  const children = fragments.filter((f) => f.parentFragment);

  roots.forEach((f, i) => {
    const id = `fragment-${f.pubkey}`;
    nodes.push(makeNode(id, fragmentLabel(f), `${f.status} · rep ${f.requiredComputeReputation}`, 320, i * 160 - 40, f.status));
    edges.push({ id: `job-${id}`, source: `job-${job.pubkey}`, target: id, label: "contains" });
  });

  children.forEach((f, i) => {
    const parentId = `fragment-${f.parentFragment}`;
    const id = `fragment-${f.pubkey}`;
    nodes.push(makeNode(id, fragmentLabel(f), `${f.status} · votes ${votesByFragment.get(f.pubkey) || 0}`, 660, i * 135 - 80, f.status));
    edges.push({ id: `parent-${id}`, source: parentId, target: id, label: "split" });
  });

  const displayedFragments = fragments;
  const workerUsed = new Map<string, WorkerView>();
  displayedFragments.forEach((f) => {
    const workerKey = f.computeWorker || f.assignedWorker;
    const worker = workerKey ? workersByKey.get(workerKey) : undefined;
    if (worker) workerUsed.set(worker.pubkey, worker);
  });

  Array.from(workerUsed.values()).forEach((w, i) => {
    const id = `worker-${w.pubkey}`;
    nodes.push(makeNode(id, `Worker ${shortKey(w.pubkey)}`, `C:${w.computeReputation} V:${w.verifyReputation}`, 1010, i * 135 - 60, "claimed"));
  });

  displayedFragments.forEach((f) => {
    const workerKey = f.computeWorker || f.assignedWorker;
    if (workerKey && workerUsed.has(workerKey)) {
      edges.push({ id: `worker-${f.pubkey}`, source: `fragment-${f.pubkey}`, target: `worker-${workerKey}`, label: "computed by" });
    }
  });

  return (
    <section className="panel graph-panel">
      <div className="panel-header">
        <h2>Graphe du job</h2>
        <span>{shortKey(job.pubkey, 8, 8)}</span>
      </div>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </section>
  );
}

export function JobsList({ jobs, selectedJob, onSelect }: { jobs: JobView[]; selectedJob?: string; onSelect: (job: string) => void }) {
  return (
    <section className="panel jobs-list">
      <div className="panel-header"><h2>Jobs</h2><span>{jobs.length}</span></div>
      {jobs.map((j) => (
        <button key={j.pubkey} className={j.pubkey === selectedJob ? "job-row active" : "job-row"} onClick={() => onSelect(j.pubkey)}>
          <strong>Job {j.jobId || shortKey(j.pubkey)}</strong>
          <span>{j.status} · {j.verifiedFragments}/{j.expectedFragments}</span>
        </button>
      ))}
    </section>
  );
}
