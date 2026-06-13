import type { LayerSnapshot } from "../lib/types";

export function StatCards({ snapshot }: { snapshot: LayerSnapshot }) {
  const items = [
    ["Jobs", snapshot.stats.jobs],
    ["Fragments", snapshot.stats.fragments],
    ["Workers", snapshot.stats.workers],
    ["Votes", snapshot.stats.votes],
    ["Resolutions", snapshot.stats.fragmentResolutions],
    ["Splits", snapshot.stats.splitProposals],
    ["Stakers", snapshot.stats.networkStakers],
  ];

  return (
    <div className="stat-grid">
      {items.map(([label, value]) => (
        <div className="stat-card" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
