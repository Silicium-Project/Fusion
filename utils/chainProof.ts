// Checks of a job's blockchain trace, run in the user's browser.
//
// The BackEnd anchors each finished job on Solana with one Memo transaction
// carrying the Merkle root of the job's tasks (see BackEnd
// internal/chainproof). The dashboard sends every task with its leaf hash and
// Merkle proof. This module lets the site check, without trusting the
// BackEnd, that:
//   1. each task's fields hash to its leaf (same encoding as the Go side);
//   2. each leaf's proof leads to the root;
//   3. the root is the one written on-chain in the transaction's memo.

import type { ChainProofStep, ChainTask } from '~/types/api';
import { resolveSolanaRpcEndpoint } from './solanaRpc';

/** SPL Memo program (v2), which carries the anchored text. */
export const MEMO_PROGRAM_ID = 'MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr';

/** Fields of the anchored memo. */
export interface AnchoredMemo {
  schema: string;
  job: string;
  tasks: number;
  root: string;
  final: string;
}

/** Outcome of checking a whole trace. */
export interface TraceCheck {
  /** `match`: the on-chain root is the trace's root. */
  chain: 'match' | 'mismatch' | 'unreachable';
  /** Task id → its leaf and proof are valid. */
  tasks: Record<string, boolean>;
}

/**
 * A JSON string encoded like Go's encoding/json: `<`, `>`, `&`, U+2028 and
 * U+2029 are escaped, which JSON.stringify does not do.
 */
function goString(value: unknown): string {
  return JSON.stringify(String(value ?? ''))
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

const goInt = (value: unknown): string => String(Math.trunc(Number(value) || 0));
const goBool = (value: unknown): string => (value === true ? 'true' : 'false');

/**
 * Canonical JSON of a task: the fields and order of the Go `Task` struct
 * (`silicium.job-proof.v1`). Any change here must match the Go side.
 */
export function canonicalTaskJson(task: ChainTask): string {
  const verifiers = (task.verifiers || []).map((verifier) => (
    `{"author":${goString(verifier.author)},`
    + `"verdict":${verifier.verdict === true || verifier.verdict === false ? goBool(verifier.verdict) : 'null'},`
    + `"verification_event":${goString(verifier.verification_event)},`
    + `"self_verification":${goBool(verifier.self_verification)}}`
  ));
  return `{"task_id":${goString(task.task_id)},`
    + `"fragment_index":${goInt(task.fragment_index)},`
    + `"status":${goString(task.status)},`
    + `"result_sha256":${goString(task.result_sha256)},`
    + `"publisher":${goString(task.publisher)},`
    + `"proposal_event":${goString(task.proposal_event)},`
    + `"spec_sha256":${goString(task.spec_sha256)},`
    + `"attempt":${goInt(task.attempt)},`
    + `"worker":${goString(task.worker)},`
    + `"claim_event":${goString(task.claim_event)},`
    + `"result_event":${goString(task.result_event)},`
    + `"verifiers":[${verifiers.join(',')}]}`;
}

function hexToBytes(hex: string): Uint8Array | null {
  if (!/^[0-9a-f]{64}$/.test(hex)) return null;
  const bytes = new Uint8Array(32);
  for (let index = 0; index < 32; index += 1) bytes[index] = parseInt(hex.slice(index * 2, index * 2 + 2), 16);
  return bytes;
}

async function sha256(parts: Uint8Array[]): Promise<Uint8Array> {
  const length = parts.reduce((total, part) => total + part.length, 0);
  const buffer = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    buffer.set(part, offset);
    offset += part.length;
  }
  return new Uint8Array(await crypto.subtle.digest('SHA-256', buffer));
}

const toHex = (bytes: Uint8Array): string => Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');

/** Leaf hash of a task: SHA-256(0x00 || canonical JSON). */
export async function leafHash(task: ChainTask): Promise<string> {
  return toHex(await sha256([new Uint8Array([0]), new TextEncoder().encode(canonicalTaskJson(task))]));
}

/** Whether `leaf`, combined along `proof` (inner node = SHA-256(0x01 || l || r)), gives `root`. */
export async function verifyProof(leaf: string, proof: ChainProofStep[], root: string): Promise<boolean> {
  let current = hexToBytes(leaf);
  if (!current) return false;
  for (const step of proof || []) {
    const sibling = hexToBytes(step.sibling);
    if (!sibling) return false;
    current = step.left
      ? await sha256([new Uint8Array([1]), sibling, current])
      : await sha256([new Uint8Array([1]), current, sibling]);
  }
  return toHex(current) === root;
}

/** A task is valid when its fields give its leaf and the leaf reaches the root. */
export async function checkTask(task: ChainTask, root: string): Promise<boolean> {
  return (await leafHash(task)) === task.leaf_hash && verifyProof(task.leaf_hash, task.proof, root);
}

/** Parses `silicium.job-proof.v1 job=… tasks=… root=… final=…`. */
export function parseMemo(memo: string | null | undefined): AnchoredMemo | null {
  const text = String(memo || '').trim();
  const [schema, ...pairs] = text.split(/\s+/);
  if (!schema?.startsWith('silicium.job-proof.')) return null;
  const fields = Object.fromEntries(pairs.map((pair) => {
    const separator = pair.indexOf('=');
    return separator < 0 ? [pair, ''] : [pair.slice(0, separator), pair.slice(separator + 1)];
  }));
  if (!/^[0-9a-f]{64}$/.test(fields.root || '')) return null;
  return { schema, job: fields.job || '', tasks: Number(fields.tasks) || 0, root: fields.root, final: fields.final || '' };
}

/** Memo text of the transaction `signature`, read from a Solana RPC. */
export async function fetchOnChainMemo(signature: string, rpcUrl: string): Promise<string | null> {
  const { Connection } = await import('@solana/web3.js');
  const connection = new Connection(resolveSolanaRpcEndpoint(rpcUrl), 'confirmed');
  const transaction = await connection.getParsedTransaction(signature, { commitment: 'confirmed', maxSupportedTransactionVersion: 0 });
  for (const instruction of transaction?.transaction.message.instructions || []) {
    if (instruction.programId.toBase58() !== MEMO_PROGRAM_ID) continue;
    if ('parsed' in instruction && typeof instruction.parsed === 'string') return instruction.parsed;
  }
  return null;
}

/**
 * Checks every task against the trace's root, then the root, task count and
 * final result hash against the on-chain memo read by `readMemo` (the
 * network call, injectable for tests).
 */
export async function checkTrace(
  trace: { tasks: ChainTask[]; root: string; finalSha256: string },
  readMemo: () => Promise<string | null>,
): Promise<TraceCheck> {
  const results: Record<string, boolean> = {};
  for (const task of trace.tasks) results[task.task_id] = await checkTask(task, trace.root);
  let chain: TraceCheck['chain'] = 'unreachable';
  try {
    const memo = parseMemo(await readMemo());
    if (memo) {
      const same = memo.root === trace.root && memo.tasks === trace.tasks.length && memo.final === trace.finalSha256;
      chain = same ? 'match' : 'mismatch';
    }
  } catch {
    chain = 'unreachable';
  }
  return { chain, tasks: results };
}

/** Explorer link of a transaction; mainnet needs no cluster parameter. */
export function explorerTransactionUrl(signature: string, cluster?: string): string {
  const base = `https://explorer.solana.com/tx/${encodeURIComponent(signature)}`;
  return !cluster || cluster === 'mainnet-beta' ? base : `${base}?cluster=${encodeURIComponent(cluster)}`;
}
