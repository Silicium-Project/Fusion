import type { FragmentView, SplitProposalView, VoteView } from "../lib/types";
import { shortKey } from "../lib/solana";

export function FragmentsPanel({ fragments, votes, splits }: { fragments: FragmentView[]; votes: VoteView[]; splits: SplitProposalView[] }) {
  const votesByFragment = new Map<string, VoteView[]>();
  for (const v of votes) {
    const list = votesByFragment.get(v.fragment) || [];
    list.push(v);
    votesByFragment.set(v.fragment, list);
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Fragments & sous-fragments</h2>
        <span>{fragments.length}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fragment</th><th>Job</th><th>Parent</th><th>Status</th><th>Leaf</th><th>Depth</th><th>Rep. compute</th><th>Stake</th><th>Votes</th>
            </tr>
          </thead>
          <tbody>
            {fragments.map((f) => (
              <tr key={f.pubkey}>
                <td title={f.pubkey}>#{f.fragmentIndex} {shortKey(f.pubkey)}</td>
                <td title={f.job}>{shortKey(f.job)}</td>
                <td title={f.parentFragment}>{shortKey(f.parentFragment)}</td>
                <td><span className={`status status-${f.status}`}>{f.status}</span></td>
                <td>{f.isLeaf ? "yes" : "no"}</td>
                <td>{f.depth}</td>
                <td>{f.requiredComputeReputation}</td>
                <td>{f.requiredStake}</td>
                <td>{votesByFragment.get(f.pubkey)?.length || 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Split proposals</h3>
      <div className="table-wrap compact">
        <table>
          <thead><tr><th>Proposal</th><th>Parent</th><th>Splitter</th><th>Children</th><th>Created</th><th>Status</th></tr></thead>
          <tbody>
            {splits.map((s) => (
              <tr key={s.pubkey}>
                <td title={s.pubkey}>{shortKey(s.pubkey)}</td>
                <td title={s.parentFragment}>{shortKey(s.parentFragment)}</td>
                <td title={s.splitterWorker}>{shortKey(s.splitterWorker)}</td>
                <td>{s.childCount}</td>
                <td>{s.createdChildren}</td>
                <td>{s.status || (s.approved ? "approved" : "pending")}</td>
              </tr>
            ))}
            {!splits.length && <tr><td colSpan={6}>Aucun split proposal trouvé.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
