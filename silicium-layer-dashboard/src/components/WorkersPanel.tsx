import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { WorkerView } from "../lib/types";
import { shortKey } from "../lib/solana";

function tier(rep: number): string {
  if (rep >= 8500) return "elite";
  if (rep >= 7000) return "trusted";
  if (rep >= 5000) return "bootstrap";
  return "risk";
}

export function WorkersPanel({ workers }: { workers: WorkerView[] }) {
  const data = workers.map((w) => ({
    name: shortKey(w.pubkey),
    compute: w.computeReputation,
    verify: w.verifyReputation,
    global: w.globalReputation,
  }));

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Workers & verifiers</h2>
        <span>{workers.length} comptes</span>
      </div>
      <div className="chart-card">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis domain={[0, 10000]} />
            <Tooltip />
            <Bar dataKey="compute" name="compute" />
            <Bar dataKey="verify" name="verify" />
            <Bar dataKey="global" name="global" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Worker</th>
              <th>Compute</th>
              <th>Verify</th>
              <th>Global</th>
              <th>Stake</th>
              <th>Claims</th>
              <th>Status</th>
              <th>Rôle</th>
            </tr>
          </thead>
          <tbody>
            {workers.map((w) => (
              <tr key={w.pubkey}>
                <td title={w.pubkey}>{shortKey(w.pubkey)}</td>
                <td><span className={`pill ${tier(w.computeReputation)}`}>{w.computeReputation}</span></td>
                <td><span className={`pill ${tier(w.verifyReputation)}`}>{w.verifyReputation}</span></td>
                <td>{w.globalReputation}</td>
                <td>{w.stakeAmount}</td>
                <td>{w.activeClaims}</td>
                <td>{w.status}</td>
                <td>{w.roles.join(", ") || "auto"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
