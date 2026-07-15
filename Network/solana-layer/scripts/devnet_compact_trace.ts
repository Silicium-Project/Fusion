import {
  Commitment,
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  TransactionInstruction,
} from "@solana/web3.js";
import crypto from "crypto";
import fs from "fs";
import os from "os";
import path from "path";

const DEVNET_RPC = process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
const MEMO_PROGRAM_ID = new PublicKey("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr");
const SILICIUM_PROGRAM_ID = process.env.SOLANA_LAYER_PROGRAM_ID ?? "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA";
const POLL_MS = Math.max(250, Number(process.env.SILICIUM_DEVNET_CONFIRM_POLL_MS ?? "1500"));
const CONFIRM_TIMEOUT_MS = Math.max(10_000, Number(process.env.SILICIUM_DEVNET_CONFIRM_TIMEOUT_MS ?? "180000"));

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stableStringify(value: any): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    .join(",")}}`;
}

function sha256(value: string | Buffer): string {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function merkleRoot(leafHashes: string[]): string {
  if (leafHashes.length === 0) return sha256(Buffer.alloc(0));
  let level = leafHashes.map((value) => Buffer.from(value, "hex"));
  while (level.length > 1) {
    const next: Buffer[] = [];
    for (let index = 0; index < level.length; index += 2) {
      const left = level[index];
      const right = level[index + 1] ?? left;
      next.push(crypto.createHash("sha256").update(Buffer.concat([left, right])).digest());
    }
    level = next;
  }
  return level[0].toString("hex");
}

function rpcDisplayName(value: string): string {
  try {
    return new URL(value).origin;
  } catch (_error) {
    return "configured RPC endpoint";
  }
}

function resolveHome(value: string): string {
  return value.startsWith("~") ? path.join(os.homedir(), value.slice(1)) : value;
}

function readKeypair(filePath: string): Keypair {
  const resolved = resolveHome(filePath);
  if (!fs.existsSync(resolved)) throw new Error(`solana_wallet_not_found:${resolved}`);
  return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(resolved, "utf8"))));
}

function writeJson(filePath: string, payload: any) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, JSON.stringify(payload, null, 2), "utf8");
  fs.renameSync(temporary, filePath);
}

function safeError(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return message.replace(/\/v2\/[A-Za-z0-9_-]+/g, "/v2/[redacted]").slice(0, 2048);
}

function confirmationReached(status: string | null | undefined, confirmations: number | null | undefined): boolean {
  const effective = status ?? (confirmations === null ? "finalized" : "processed");
  return effective === "confirmed" || effective === "finalized";
}

async function confirmByHttp(
  connection: Connection,
  signature: string,
  lastValidBlockHeight: number,
  commitment: Commitment = "confirmed",
) {
  const deadline = Date.now() + CONFIRM_TIMEOUT_MS;
  let polls = 0;
  while (Date.now() < deadline) {
    try {
      const statuses = await connection.getSignatureStatuses([signature], { searchTransactionHistory: true });
      const status = statuses.value[0];
      if (status?.err) throw new Error(`transaction_failed:${JSON.stringify(status.err)}`);
      if (status && confirmationReached(status.confirmationStatus, status.confirmations)) return;
      polls += 1;
      if (polls % 4 === 0 && (await connection.getBlockHeight(commitment)) > lastValidBlockHeight) {
        throw new Error(`transaction_expired:${signature}`);
      }
    } catch (error) {
      const message = safeError(error);
      if (message.startsWith("transaction_failed:") || message.startsWith("transaction_expired:")) throw error;
    }
    await sleep(POLL_MS);
  }
  throw new Error(`transaction_confirmation_timeout:${signature}`);
}

function buildManifest(summary: any, summaryBytes: Buffer) {
  const fragments = Array.isArray(summary.fragments) ? summary.fragments : [];
  const leaves = fragments
    .map((fragment: any, position: number) => {
      const leaf = {
        fragment_index: Number(fragment.fragment_index ?? position),
        y_start: Number(fragment.y_start ?? 0),
        y_end: Number(fragment.y_end ?? 0),
        result_hash: String(fragment.compute_result_hash ?? fragment.result_hash ?? fragment.expected_hash ?? "").replace(/^sha256:/, ""),
        compute_node_id: String(fragment.compute_node_id ?? ""),
        verify_node_id: String(fragment.verify_node_id ?? ""),
        verify_choice: Boolean(fragment.verify_choice),
        status: String(fragment.status ?? ""),
      };
      return { ...leaf, leaf_hash: sha256(stableStringify(leaf)) };
    })
    .sort((left: any, right: any) => left.fragment_index - right.fragment_index);
  const root = merkleRoot(leaves.map((leaf: any) => leaf.leaf_hash));
  const manifest = {
    schema_version: 1,
    kind: "silicium_compact_job_trace",
    job_id: String(summary.job_id ?? ""),
    source_summary_hash: sha256(summaryBytes),
    final_hash: String(summary.reassembled_hash ?? summary.final_hash ?? "").replace(/^sha256:/, ""),
    fragment_count: leaves.length,
    merkle_root: root,
    fragments: leaves,
  };
  return { manifest, manifestHash: sha256(stableStringify(manifest)), merkleRoot: root };
}

async function main() {
  const summaryPath = process.argv[2];
  if (!summaryPath) throw new Error("usage: ts-node scripts/devnet_compact_trace.ts <raytracer-summary.json>");
  const summaryBytes = fs.readFileSync(summaryPath);
  const summary = JSON.parse(summaryBytes.toString("utf8"));
  if (!summary.success) throw new Error("refusing_to_trace_unsuccessful_job");

  const outPath = process.env.SILICIUM_TRACE_RESULT_PATH || path.join(path.dirname(summaryPath), "devnet-compact-trace.json");
  const manifestPath = path.join(path.dirname(summaryPath), "compact-trace-manifest.json");
  const { manifest, manifestHash, merkleRoot: root } = buildManifest(summary, summaryBytes);
  writeJson(manifestPath, manifest);

  const walletPath = process.env.ANCHOR_WALLET ?? path.resolve(__dirname, "..", "..", ".silicium", "solana", "id.json");
  const payer = readKeypair(walletPath);
  const connection = new Connection(DEVNET_RPC, "confirmed");
  const pending = {
    schema_version: 1,
    enabled: true,
    mode: "async_compact",
    status: "pending",
    ok: false,
    source_summary_path: path.resolve(summaryPath),
    manifest_path: manifestPath,
    manifest_hash: manifestHash,
    merkle_root: root,
    final_hash: manifest.final_hash,
    fragment_count: manifest.fragment_count,
    rpc: rpcDisplayName(DEVNET_RPC),
    memo_program_id: MEMO_PROGRAM_ID.toBase58(),
    silicium_program_id: SILICIUM_PROGRAM_ID,
    wallet: payer.publicKey.toBase58(),
    submitted_utc: new Date().toISOString(),
  };
  writeJson(outPath, pending);

  const commitment = {
    p: "silicium",
    v: 1,
    job: manifest.job_id,
    manifest: manifestHash,
    merkle: root,
    result: manifest.final_hash,
    fragments: manifest.fragment_count,
  };
  const memo = Buffer.from(stableStringify(commitment), "utf8");
  if (memo.length > 700) throw new Error(`compact_trace_payload_too_large:${memo.length}`);

  const latest = await connection.getLatestBlockhash("confirmed");
  const transaction = new Transaction({
    feePayer: payer.publicKey,
    blockhash: latest.blockhash,
    lastValidBlockHeight: latest.lastValidBlockHeight,
  }).add(
    new TransactionInstruction({
      programId: MEMO_PROGRAM_ID,
      keys: [{ pubkey: payer.publicKey, isSigner: true, isWritable: false }],
      data: memo,
    }),
  );
  transaction.sign(payer);
  const signature = await connection.sendRawTransaction(transaction.serialize(), {
    maxRetries: 5,
    skipPreflight: false,
  });
  writeJson(outPath, { ...pending, status: "confirming", signature });
  await confirmByHttp(connection, signature, latest.lastValidBlockHeight);

  const trace = {
    ...pending,
    status: "confirmed",
    ok: true,
    signature,
    explorer_url: `https://explorer.solana.com/tx/${signature}?cluster=devnet`,
    confirmed_utc: new Date().toISOString(),
  };
  writeJson(outPath, trace);
  console.log(JSON.stringify(trace, null, 2));
}

main().catch((error) => {
  const summaryPath = process.argv[2] || "";
  const outPath = process.env.SILICIUM_TRACE_RESULT_PATH || path.join(path.dirname(summaryPath || "."), "devnet-compact-trace.json");
  let previous: any = {};
  try {
    previous = JSON.parse(fs.readFileSync(outPath, "utf8"));
  } catch (_readError) {
    previous = {
      schema_version: 1,
      enabled: true,
      mode: "async_compact",
      source_summary_path: summaryPath ? path.resolve(summaryPath) : "",
      rpc: rpcDisplayName(DEVNET_RPC),
    };
  }
  writeJson(outPath, {
    ...previous,
    status: "failed",
    ok: false,
    error: safeError(error),
    failed_utc: new Date().toISOString(),
  });
  console.error(safeError(error));
  process.exit(1);
});
