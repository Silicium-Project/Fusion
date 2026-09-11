import assert from "node:assert/strict";
import test from "node:test";

import { compactProof, safeRpcLabel } from "./devnet_trace_fragments.mjs";

test("compact proof carries verified result and receipt hashes", () => {
  const proof = compactProof({
    job_id: "site-render-1",
    final_hash: "sha256:result",
    fragment_count: 8,
    billing: { receipt_set_hash: "sha256:receipts" },
  });
  assert.deepEqual(proof, {
    schema: "silicium.devnet-proof.v1",
    job: "site-render-1",
    result: "sha256:result",
    receipts: "sha256:receipts",
    fragments: 8,
  });
});

test("private RPC paths are not persisted in public trace data", () => {
  assert.equal(
    safeRpcLabel("https://solana-devnet.example.test/v2/private-token"),
    "https://solana-devnet.example.test"
  );
});

test("oversized job identifiers are replaced with their digest", () => {
  const proof = compactProof({ job_id: "x".repeat(700) });
  assert.match(proof.job, /^sha256:[a-f0-9]{64}$/);
  assert.ok(Buffer.byteLength(JSON.stringify(proof), "utf8") <= 566);
});
