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

function makeNode(id: string, label: string, subtitle: string, x: number, y: number, status = "unknown", title?: string): Node {
  return {
    id,
    position: { x, y },
    data: { label: <div title={title}><strong>{label}</strong><span>{subtitle}</span></div> },
    className: `graph-node ${statusClass[status] || "node-gray"}`,
  };
}

function fragmentLabel(f: FragmentView): string {
  return f.parentFragment ? `Sub-fragment ${f.fragmentIndex}` : `Fragment ${f.fragmentIndex}`;
}

export function JobGraph({ snapshot, selectedJob }: { snapshot: LayerSnapshot; selectedJob?: string }) {
  const job = snapshot.jobs.find((j) => j.pubkey === selectedJob) || snapshot.jobs[0];
  if (!job) {
    return <section className="panel empty">Aucun job a afficher.</section>;
  }

  const fragments = snapshot.fragments
    .filter((f) => f.job === job.pubkey)
    .sort((a, b) => a.depth - b.depth || a.fragmentIndex - b.fragmentIndex);
  const fragmentsByKey = new Map(fragments.map((f) => [f.pubkey, f]));
  const workersByKey = new Map(snapshot.workers.map((w) => [w.pubkey, w]));
  const votesByFragment = new Map<string, number>();
  for (const vote of snapshot.votes) {
    votesByFragment.set(vote.fragment, (votesByFragment.get(vote.fragment) || 0) + 1);
  }

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  nodes.push(makeNode(
    `job-${job.pubkey}`,
    `Job ${job.jobId || shortKey(job.pubkey)}`,
    `${job.status} - ${job.verifiedFragments}/${job.expectedFragments} verifies`,
    0,
    0,
    job.status,
    `Job account: ${job.pubkey}`,
  ));

  const childrenByParent = new Map<string, FragmentView[]>();
  for (const fragment of fragments) {
    if (!fragment.parentFragment) continue;
    const list = childrenByParent.get(fragment.parentFragment) || [];
    list.push(fragment);
    childrenByParent.set(fragment.parentFragment, list);
  }
  for (const list of childrenByParent.values()) {
    list.sort((a, b) => a.fragmentIndex - b.fragmentIndex);
  }

  const roots = fragments.filter((f) => f.depth === 0 || !f.parentFragment || !fragmentsByKey.has(f.parentFragment));
  const rootsToRender = roots.length ? roots : fragments;
  const rendered = new Set<string>();
  let row = 0;

  function renderFragmentTree(fragment: FragmentView, depth: number) {
    if (rendered.has(fragment.pubkey)) return;
    rendered.add(fragment.pubkey);

    const id = `fragment-${fragment.pubkey}`;
    const votes = votesByFragment.get(fragment.pubkey) || 0;
    const parentExists = fragment.parentFragment ? fragmentsByKey.has(fragment.parentFragment) : false;
    const isRoot = depth === 0 || !fragment.parentFragment || !parentExists;
    const sourceId = isRoot ? `job-${job.pubkey}` : `fragment-${fragment.parentFragment}`;
    const subtitle = `${fragment.status} - depth ${fragment.depth} - votes ${votes}`;
    const title = [
      `Fragment account: ${fragment.pubkey}`,
      `Job account: ${fragment.job}`,
      fragment.parentFragment ? `Parent fragment: ${fragment.parentFragment}` : "Parent fragment: none",
      `Index: ${fragment.fragmentIndex}`,
    ].join("\n");

    nodes.push(makeNode(id, fragmentLabel(fragment), subtitle, 330 + depth * 300, row * 135 - 80, fragment.status, title));
    edges.push({
      id: `${sourceId}-${id}`,
      source: sourceId,
      target: id,
      label: isRoot ? "belongs to job" : "child of",
      animated: !isRoot,
    });
    row += 1;

    for (const child of childrenByParent.get(fragment.pubkey) || []) {
      renderFragmentTree(child, depth + 1);
    }
  }

  rootsToRender.forEach((fragment) => renderFragmentTree(fragment, 0));

  fragments
    .filter((fragment) => !rendered.has(fragment.pubkey))
    .forEach((fragment) => renderFragmentTree(fragment, Math.max(0, fragment.depth)));

  const workerUsed = new Map<string, WorkerView>();
  fragments.forEach((f) => {
    const workerKey = f.computeWorker || f.assignedWorker;
    const worker = workerKey ? workersByKey.get(workerKey) : undefined;
    if (worker) workerUsed.set(worker.pubkey, worker);
  });

  Array.from(workerUsed.values()).forEach((w, i) => {
    const id = `worker-${w.pubkey}`;
    nodes.push(makeNode(
      id,
      `Worker ${shortKey(w.pubkey)}`,
      `C:${w.computeReputation} V:${w.verifyReputation}`,
      1120,
      i * 135 - 60,
      "claimed",
      `Worker account: ${w.pubkey}`,
    ));
  });

  fragments.forEach((f) => {
    const workerKey = f.computeWorker || f.assignedWorker;
    if (workerKey && workerUsed.has(workerKey)) {
      edges.push({ id: `worker-${f.pubkey}`, source: `fragment-${f.pubkey}`, target: `worker-${workerKey}`, label: "computed by" });
    }
  });

  const orphanCount = roots.filter((f) => f.parentFragment && !fragmentsByKey.has(f.parentFragment)).length;

  return (
    <section className="panel graph-panel">
      <div className="panel-header">
        <h2>Graphe du job</h2>
        <span>{fragments.length} fragments lies a {shortKey(job.pubkey, 8, 8)}</span>
      </div>
      {orphanCount > 0 && (
        <p className="graph-note">
          {orphanCount} fragment(s) ont un parent absent du snapshot charge. Ils sont rattaches au job pour rester visibles.
        </p>
      )}
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
      <div className="panel-header"><h2>Jobs</h2><span>plus recent d'abord - {jobs.length}</span></div>
      {jobs.map((j, index) => (
        <button key={j.pubkey} className={j.pubkey === selectedJob ? "job-row active" : "job-row"} onClick={() => onSelect(j.pubkey)}>
          <strong>{index === 0 ? "Dernier job - " : ""}Job {j.jobId || shortKey(j.pubkey)}</strong>
          <span>{j.status} - {j.verifiedFragments}/{j.expectedFragments}</span>
          {j.createdAtUnix ? <small>{new Date(j.createdAtUnix * 1000).toLocaleString()}</small> : null}
        </button>
      ))}
    </section>
  );
}
