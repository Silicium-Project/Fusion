import type { FragmentResolutionView, FragmentView, SplitProposalView, VoteView } from "../lib/types";
import { shortKey } from "../lib/solana";

function shortHash(value?: string): string {
  if (!value) return "-";
  if (/^0+$/.test(value)) return "empty";
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}

export function FragmentsPanel({
  fragments,
  votes,
  resolutions,
  splits,
}: {
  fragments: FragmentView[];
  votes: VoteView[];
  resolutions: FragmentResolutionView[];
  splits: SplitProposalView[];
}) {
  const votesByFragment = new Map<string, VoteView[]>();
  for (const v of votes) {
    const list = votesByFragment.get(v.fragment) || [];
    list.push(v);
    votesByFragment.set(v.fragment, list);
  }

  const resolutionByFragment = new Map<string, FragmentResolutionView>();
  for (const resolution of resolutions) {
    resolutionByFragment.set(resolution.fragment, resolution);
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Fragments resolus</h2>
        <span>{fragments.length}</span>
      </div>

      <div className="resolution-grid">
        {fragments.map((f) => {
          const fragmentVotes = votesByFragment.get(f.pubkey) || [];
          const resolution = resolutionByFragment.get(f.pubkey);
          const computeWorker = f.computeWorker || f.assignedWorker;
          const resolved = f.status === "verified" || Boolean(resolution?.resolved);

          return (
            <article className="resolution-card" key={f.pubkey}>
              <div className="resolution-card-head">
                <div>
                  <strong>Fragment {f.fragmentIndex}</strong>
                  <span title={f.pubkey}>{shortKey(f.pubkey, 6, 6)}</span>
                </div>
                <span className={`status status-${f.status}`}>{f.status}</span>
              </div>

              <div className="resolution-steps">
                <div className="resolution-step done">
                  <b>1. Appartenance</b>
                  <span title={f.job}>job {shortKey(f.job, 6, 6)}</span>
                  <small>{f.parentFragment ? `parent ${shortKey(f.parentFragment, 6, 6)}` : "fragment racine"}</small>
                </div>
                <div className={computeWorker ? "resolution-step done" : "resolution-step"}>
                  <b>2. Compute</b>
                  <span title={computeWorker}>{computeWorker ? shortKey(computeWorker, 6, 6) : "non claim"}</span>
                  <small>depth {f.depth} - complexity {f.complexityScore ?? 0}</small>
                </div>
                <div className={f.resultHash && !/^0+$/.test(f.resultHash) ? "resolution-step done" : "resolution-step"}>
                  <b>3. Resultat</b>
                  <span title={f.resultHash}>hash {shortHash(f.resultHash)}</span>
                  <small title={f.proofRef}>proof {shortHash(f.proofRef)}</small>
                </div>
                <div className={resolved ? "resolution-step done" : "resolution-step"}>
                  <b>4. Verification</b>
                  <span>{f.yesVotes ?? fragmentVotes.filter((v) => v.choice).length} yes / {f.noVotes ?? fragmentVotes.filter((v) => !v.choice).length} no</span>
                  <small>{resolution ? `resolution round ${resolution.round}` : `${fragmentVotes.length} vote(s) charges`}</small>
                </div>
              </div>

              <div className="vote-list">
                {fragmentVotes.map((vote) => (
                  <span key={vote.pubkey} title={`${vote.pubkey}\nVerifier: ${vote.verifier}`}>
                    {vote.choice ? "yes" : "no"} by {shortKey(vote.verifier, 5, 5)}
                  </span>
                ))}
                {!fragmentVotes.length && <span>Aucun vote charge</span>}
              </div>
            </article>
          );
        })}
      </div>

      <h3>Table brute des fragments</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Fragment</th><th>Job</th><th>Parent</th><th>Status</th><th>Leaf</th><th>Depth</th><th>Worker</th><th>Result hash</th><th>Proof ref</th><th>Votes</th>
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
                <td title={f.computeWorker || f.assignedWorker}>{shortKey(f.computeWorker || f.assignedWorker)}</td>
                <td title={f.resultHash}>{shortHash(f.resultHash)}</td>
                <td title={f.proofRef}>{shortHash(f.proofRef)}</td>
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
            {!splits.length && <tr><td colSpan={6}>Aucun split proposal trouve.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
