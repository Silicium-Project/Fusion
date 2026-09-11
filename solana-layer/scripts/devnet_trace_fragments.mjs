import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

import {
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  TransactionInstruction,
  sendAndConfirmTransaction,
} from "@solana/web3.js";

const MEMO_PROGRAM_ID = new PublicKey(
  "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
);
const MAX_MEMO_BYTES = 566;

function requiredEnv(name) {
  const value = (process.env[name] ?? "").trim();
  if (!value) {
    throw new Error(`missing_environment:${name}`);
  }
  return value;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

export function safeRpcLabel(rpc) {
  const parsed = new URL(rpc);
  return `${parsed.protocol}//${parsed.host}`;
}

export function compactProof(summary) {
  const billing =
    summary.billing && typeof summary.billing === "object"
      ? summary.billing
      : {};
  const finalHash = String(
    summary.final_hash ?? summary.reassembled_hash ?? ""
  );
  const receiptHash = String(billing.receipt_set_hash ?? "");
  const proof = {
    schema: "silicium.devnet-proof.v1",
    job: String(summary.job_id ?? "unknown"),
    result: finalHash,
    receipts: receiptHash,
    fragments: Number(summary.fragment_count ?? 0),
  };
  const encoded = Buffer.from(JSON.stringify(proof), "utf8");
  if (encoded.length > MAX_MEMO_BYTES) {
    proof.job = `sha256:${sha256(proof.job)}`;
  }
  return proof;
}

function writeJsonAtomic(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temporaryPath = `${filePath}.tmp-${process.pid}`;
  fs.writeFileSync(temporaryPath, `${JSON.stringify(payload, null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  fs.renameSync(temporaryPath, filePath);
}

async function main() {
  const summaryPath = process.argv[2];
  if (!summaryPath) {
    throw new Error("summary_path_required");
  }

  const walletPath = requiredEnv("ANCHOR_WALLET");
  const rpc = requiredEnv("SOLANA_RPC_URL");
  const projectProgram = new PublicKey(requiredEnv("SOLANA_LAYER_PROGRAM_ID"));
  const outputPath =
    process.env.SILICIUM_TRACE_RESULT_PATH?.trim() ||
    path.join(path.dirname(summaryPath), "devnet-trace.json");
  const summary = readJson(summaryPath);
  const secret = Uint8Array.from(readJson(walletPath));
  const payer = Keypair.fromSecretKey(secret);
  const connection = new Connection(rpc, "confirmed");
  const proof = compactProof(summary);
  const memo = Buffer.from(JSON.stringify(proof), "utf8");

  if (memo.length > MAX_MEMO_BYTES) {
    throw new Error(`proof_memo_too_large:${memo.length}`);
  }

  const instruction = new TransactionInstruction({
    programId: MEMO_PROGRAM_ID,
    keys: [{ pubkey: projectProgram, isSigner: false, isWritable: false }],
    data: memo,
  });
  const transaction = new Transaction().add(instruction);
  const signature = await sendAndConfirmTransaction(
    connection,
    transaction,
    [payer],
    {
      commitment: "confirmed",
      preflightCommitment: "confirmed",
      maxRetries: 5,
    }
  );
  const signatureStatus = await connection.getSignatureStatus(signature, {
    searchTransactionHistory: true,
  });
  const proofHash = `sha256:${sha256(memo)}`;
  const trace = {
    schema_version: 1,
    kind: "compact_job_proof",
    cluster: "devnet",
    job: proof.job,
    program_id: projectProgram.toBase58(),
    memo_program_id: MEMO_PROGRAM_ID.toBase58(),
    wallet: payer.publicKey.toBase58(),
    rpc: safeRpcLabel(rpc),
    proof_hash: proofHash,
    result_hash: proof.result,
    receipt_hash: proof.receipts,
    fragment_count: proof.fragments,
    slot: signatureStatus.value?.slot ?? null,
    signatures: [signature],
    explorer_urls: [
      `https://explorer.solana.com/tx/${signature}?cluster=devnet`,
    ],
    submitted_utc: new Date().toISOString(),
  };

  writeJsonAtomic(outputPath, trace);
  process.stdout.write(
    `${JSON.stringify({ ok: true, trace_path: outputPath, signature })}\n`
  );
}

const invokedPath = process.argv[1]
  ? pathToFileURL(path.resolve(process.argv[1])).href
  : "";
if (import.meta.url === invokedPath) {
  main().catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${JSON.stringify({ ok: false, error: message })}\n`);
    process.exitCode = 1;
  });
}
