import { describe, expect, it } from 'vitest';
import type { ChainTask } from '../types/api';
import {
  canonicalTaskJson,
  checkTask,
  checkTrace,
  explorerTransactionUrl,
  leafHash,
  parseMemo,
  verifyProof,
} from '../utils/chainProof';
import { awaitingChainAnchor } from '../utils/jobs';
// Written by the Go BackEnd (internal/chainproof.BuildTrace): the browser
// must recompute exactly the same leaves and root.
import fixture from './fixtures/chain-trace.json';

const tasks = fixture.fragments as unknown as ChainTask[];
const root = fixture.merkle_root;

describe('blockchain trace checks', () => {
  it('recomputes the Go leaf of every task, escapes included', async () => {
    expect(canonicalTaskJson(tasks[0])).toContain('"worker":"w0 \\u003c\\u0026\\u003e"');
    for (const task of tasks) expect(await leafHash(task)).toBe(task.leaf_hash);
  });

  it('follows every Merkle proof to the anchored root', async () => {
    for (const task of tasks) {
      expect(await verifyProof(task.leaf_hash, task.proof, root)).toBe(true);
      expect(await checkTask(task, root)).toBe(true);
    }
  });

  it('rejects a task whose trace was changed after anchoring', async () => {
    const forged = { ...tasks[1], worker: 'someone-else' };
    expect(await checkTask(forged, root)).toBe(false);
    expect(await verifyProof(tasks[0].leaf_hash, tasks[1].proof, root)).toBe(false);
    expect(await verifyProof('not-hex', [], root)).toBe(false);
  });

  it('reads the anchored memo', () => {
    expect(parseMemo(fixture.memo)).toEqual({
      schema: 'silicium.job-proof.v1',
      job: fixture.job,
      tasks: 3,
      root,
      final: 'ffee',
    });
    expect(parseMemo('hello')).toBeNull();
    expect(parseMemo('silicium.job-proof.v1 root=short')).toBeNull();
  });

  it('compares the trace with the transaction on chain', async () => {
    const trace = { tasks, root, finalSha256: fixture.final_sha256 };
    expect(await checkTrace(trace, async () => fixture.memo)).toEqual({
      chain: 'match',
      tasks: Object.fromEntries(tasks.map((task) => [task.task_id, true])),
    });
    expect(
      (await checkTrace(trace, async () => fixture.memo.replace('final=ffee', 'final=0000'))).chain,
    ).toBe('mismatch');
    expect((await checkTrace(trace, async () => null)).chain).toBe('unreachable');
    expect(
      (
        await checkTrace(trace, async () => {
          throw new Error('rpc down');
        })
      ).chain,
    ).toBe('unreachable');
  });

  it('links the explorer of the right cluster', () => {
    expect(explorerTransactionUrl('sig', 'devnet')).toBe(
      'https://explorer.solana.com/tx/sig?cluster=devnet',
    );
    expect(explorerTransactionUrl('sig', 'mainnet-beta')).toBe(
      'https://explorer.solana.com/tx/sig',
    );
  });

  it('waits a few minutes at most for the anchor of a completed job', () => {
    const completedAt = '2026-10-14T10:00:00Z';
    const at = (minutes: number) => Date.parse(completedAt) + minutes * 60_000;
    const job = { status: 'completed', completedAt };
    expect(awaitingChainAnchor({ job, devnet: { status: 'pending' } }, at(1))).toBe(true);
    expect(awaitingChainAnchor({ job, devnet: { status: 'pending' } }, at(6))).toBe(false);
    expect(awaitingChainAnchor({ job, devnet: { status: 'anchored' } }, at(1))).toBe(false);
    expect(
      awaitingChainAnchor(
        { job: { ...job, status: 'running' }, devnet: { status: 'pending' } },
        at(1),
      ),
    ).toBe(false);
  });
});
