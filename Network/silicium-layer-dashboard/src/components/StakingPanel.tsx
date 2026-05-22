import type { NetworkStakerView, StakingPoolView } from "../lib/types";
import { shortKey } from "../lib/solana";

export function StakingPanel({ pools, stakers }: { pools: StakingPoolView[]; stakers: NetworkStakerView[] }) {
  return (
    <section className="panel">
      <div className="panel-header"><h2>Staking passif</h2><span>{stakers.length} stakers</span></div>
      <div className="pool-grid">
        {pools.map((p) => (
          <div className="stat-card" key={p.pubkey}>
            <span>Pool {shortKey(p.pubkey)}</span>
            <strong>{p.totalStaked}</strong>
            <small>reward pool: {p.rewardPool || 0}</small>
          </div>
        ))}
        {!pools.length && <p>Aucun staking pool trouvé.</p>}
      </div>
      <div className="table-wrap compact">
        <table>
          <thead><tr><th>Staker</th><th>Owner</th><th>Amount</th><th>Pending</th></tr></thead>
          <tbody>
            {stakers.map((s) => (
              <tr key={s.pubkey}>
                <td title={s.pubkey}>{shortKey(s.pubkey)}</td>
                <td title={s.owner}>{shortKey(s.owner)}</td>
                <td>{s.amount}</td>
                <td>{s.pendingRewards || 0}</td>
              </tr>
            ))}
            {!stakers.length && <tr><td colSpan={4}>Aucun network staker trouvé.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
