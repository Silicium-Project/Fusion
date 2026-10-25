import { PublicKey } from '@solana/web3.js';
import * as anchor from '@coral-xyz/anchor';

export function u32le(value: number): Buffer {
  const buffer = Buffer.alloc(4);
  buffer.writeUInt32LE(value, 0);
  return buffer;
}

export function u16le(value: number): Buffer {
  const buffer = Buffer.alloc(2);
  buffer.writeUInt16LE(value, 0);
  return buffer;
}

export function toBn(value: anchor.BN | number | bigint | string): anchor.BN {
  if (anchor.BN.isBN(value)) return value;
  return new anchor.BN(value.toString());
}

export function jobPda(
  programId: PublicKey,
  client: PublicKey,
  jobId: anchor.BN | number | bigint | string,
): PublicKey {
  const id = toBn(jobId);
  return PublicKey.findProgramAddressSync(
    [Buffer.from('job'), client.toBuffer(), id.toArrayLike(Buffer, 'le', 8)],
    programId,
  )[0];
}

export function jobStoragePda(programId: PublicKey, job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('job_storage'), job.toBuffer()],
    programId,
  )[0];
}

export function fragmentPda(
  programId: PublicKey,
  job: PublicKey,
  fragmentIndex: number,
): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('fragment'), job.toBuffer(), u32le(fragmentIndex)],
    programId,
  )[0];
}

export function workerPda(programId: PublicKey, worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync([Buffer.from('worker'), worker.toBuffer()], programId)[0];
}

export function workerPayoutPda(programId: PublicKey, workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('worker_payout'), workerAccount.toBuffer()],
    programId,
  )[0];
}

export function escrowAuthPda(programId: PublicKey, job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('escrow_auth'), job.toBuffer()],
    programId,
  )[0];
}

export function stakeAuthPda(programId: PublicKey, workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('stake_auth'), workerAccount.toBuffer()],
    programId,
  )[0];
}

export function stakeVaultPda(programId: PublicKey, worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('stake_vault'), worker.toBuffer()],
    programId,
  )[0];
}

export function votePda(
  programId: PublicKey,
  fragment: PublicKey,
  verifier: PublicKey,
  round: number,
): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('fragment_vote'), fragment.toBuffer(), verifier.toBuffer(), u16le(round)],
    programId,
  )[0];
}

export function roundResolutionPda(
  programId: PublicKey,
  fragment: PublicKey,
  round: number,
): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('fragment_resolution'), fragment.toBuffer(), u16le(round)],
    programId,
  )[0];
}

export function splitProposalPda(
  programId: PublicKey,
  parentFragment: PublicKey,
  round: number,
): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('split_proposal'), parentFragment.toBuffer(), u16le(round)],
    programId,
  )[0];
}

export function resultPda(programId: PublicKey, job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync([Buffer.from('result'), job.toBuffer()], programId)[0];
}

export function treasuryStatePda(programId: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync([Buffer.from('treasury'), mint.toBuffer()], programId)[0];
}

export function treasuryAuthPda(programId: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('treasury_auth'), mint.toBuffer()],
    programId,
  )[0];
}

export function stakingPoolPda(programId: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('staking_pool'), mint.toBuffer()],
    programId,
  )[0];
}

export function stakingPoolAuthPda(programId: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('staking_pool_auth'), mint.toBuffer()],
    programId,
  )[0];
}

export function networkStakerPda(
  programId: PublicKey,
  owner: PublicKey,
  mint: PublicKey,
): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('network_staker'), owner.toBuffer(), mint.toBuffer()],
    programId,
  )[0];
}
