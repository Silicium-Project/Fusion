/**
 * Anchor a completed raytracer result in the live Devnet program.
 *
 * This is deliberately a write-path smoke test: it reuses the full minimal
 * job flow (mint, registration/stake, claim, submit, quorum votes, worker
 * rewards, and finalization) while binding the on-chain fragment hash to the
 * actual reassembled artifact produced by run_network_job.py.
 */

import fs from "fs";
import path from "path";
import { main as runMinimalJobFlow } from "./devnet_minimal_job_flow";

function readSummary(summaryPath: string): any {
  const payload = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
  if (!payload || typeof payload !== "object" || payload.success !== true) {
    throw new Error("raytracer_summary_not_successful");
  }
  return payload;
}

function normalizeHash(value: unknown): string {
  const normalized = String(value ?? "").replace(/^sha256:/, "").trim();
  if (!/^[0-9a-fA-F]{64}$/.test(normalized)) {
    throw new Error("raytracer_summary_hash_missing_or_invalid");
  }
  return normalized.toLowerCase();
}

async function main() {
  const summaryPath = process.argv[2];
  if (!summaryPath) {
    throw new Error("usage: devnet_trace_fragments.ts <raytracer-summary.json>");
  }
  const summary = readSummary(path.resolve(summaryPath));
  const artifactHash = normalizeHash(summary.reassembled_hash);
  const taskId = String(summary.job_id || `raytracer-${Date.now()}`);
  const firstFragment = Array.isArray(summary.fragments) ? summary.fragments[0] ?? {} : {};
  const tileRegion = {
    x: Number(firstFragment.x_start ?? 0),
    y: Number(firstFragment.y_start ?? 0),
    width: Math.max(1, Number(firstFragment.x_end ?? summary.image?.width ?? 1) - Number(firstFragment.x_start ?? 0)),
    height: Math.max(1, Number(firstFragment.y_end ?? summary.image?.height ?? 1) - Number(firstFragment.y_start ?? 0)),
  };
  const taskPayload = {
    kind: "compute",
    workload: "calcul/rendering/raytracer-fragment",
    job_id: taskId,
    fragment_count: Number(summary.fragment_count ?? 1),
    tile_index: Number(firstFragment.fragment_index ?? 0),
    tile_region: tileRegion,
    reassembled_hash: `sha256:${artifactHash}`,
    result_path: String(summary.result_path ?? summary.reassembled_ppm ?? ""),
    source_summary: path.resolve(summaryPath),
  };

  process.env.SILICIUM_CHAIN_TASK_ID = taskId;
  process.env.SILICIUM_CHAIN_TASK_JSON = JSON.stringify(taskPayload);
  process.env.SILICIUM_CHAIN_RESULT_HASH = artifactHash;
  process.env.SILICIUM_CHAIN_PROOF_HASH = artifactHash;
  process.env.SILICIUM_CHAIN_OUTPUT_URI = `silicium://raytracer/${taskId}/${artifactHash}`;
  process.env.SILICIUM_CHAIN_RESULT_PATH =
    process.env.SILICIUM_TRACE_RESULT_PATH ?? path.resolve(path.dirname(summaryPath), "devnet-trace.json");

  await runMinimalJobFlow();

  const tracePath = process.env.SILICIUM_CHAIN_RESULT_PATH;
  if (!tracePath || !fs.existsSync(tracePath)) {
    throw new Error("devnet_trace_result_missing");
  }
  const trace = JSON.parse(fs.readFileSync(tracePath, "utf8"));
  trace.reconciliation = {
    source_summary: path.resolve(summaryPath),
    source_artifact_hash: `sha256:${artifactHash}`,
    on_chain_fragment_hash: trace.result_hash,
    hash_match: trace.result_hash === `sha256:${artifactHash}`,
  };
  if (!trace.reconciliation.hash_match) {
    throw new Error("devnet_trace_artifact_hash_not_reconciled");
  }
  fs.writeFileSync(tracePath, JSON.stringify(trace, null, 2), "utf8");
  console.log("reconciled artifact:", trace.reconciliation.source_artifact_hash);
}

main().catch((error) => {
  console.error("\n❌ Devnet raytracer trace failed");
  console.error(error);
  process.exit(1);
});
