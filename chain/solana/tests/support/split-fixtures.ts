import * as anchor from '@coral-xyz/anchor';
import { Program } from '@coral-xyz/anchor';
import { PublicKey, SystemProgram, SYSVAR_RENT_PUBKEY } from '@solana/web3.js';
import { assert } from 'chai';
import {
  TOKEN_PROGRAM_ID,
  createMint,
  createAssociatedTokenAccount,
  mintTo,
} from '@solana/spl-token';

export const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

export const program = anchor.workspace.SolanaLayer as Program<any>;

export const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);
export const DEFAULT_REWARD_PER_FRAGMENT = new anchor.BN(100_000);
export const DEFAULT_FRAGMENT_QUORUM = 2;

export function u32le(n: number): Buffer {
  const buf = Buffer.alloc(4);
  buf.writeUInt32LE(n, 0);
  return buf;
}

export function u16le(n: number): Buffer {
  const buf = Buffer.alloc(2);
  buf.writeUInt16LE(n, 0);
  return buf;
}

export function jobPda(client: PublicKey, jobId: anchor.BN): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('job'), client.toBuffer(), jobId.toArrayLike(Buffer, 'le', 8)],
    program.programId,
  )[0];
}

export function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('escrow_auth'), job.toBuffer()],
    program.programId,
  )[0];
}

export function fragmentPda(job: PublicKey, fragmentIndex: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('fragment'), job.toBuffer(), u32le(fragmentIndex)],
    program.programId,
  )[0];
}

export function splitProposalPda(parentFragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('split_proposal'), parentFragment.toBuffer(), u16le(round)],
    program.programId,
  )[0];
}

export function workerPda(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('worker'), worker.toBuffer()],
    program.programId,
  )[0];
}

export function workerPayoutPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('worker_payout'), workerAccount.toBuffer()],
    program.programId,
  )[0];
}

export function stakeAuthPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('stake_auth'), workerAccount.toBuffer()],
    program.programId,
  )[0];
}

export function stakeVaultPda(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('stake_vault'), worker.toBuffer()],
    program.programId,
  )[0];
}

export function votePda(fragment: PublicKey, verifier: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('fragment_vote'), fragment.toBuffer(), verifier.toBuffer(), u16le(round)],
    program.programId,
  )[0];
}

export function roundResolutionPda(fragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('fragment_resolution'), fragment.toBuffer(), u16le(round)],
    program.programId,
  )[0];
}

export function maxLeafFragments(initialFragments: number): number {
  const childSlotsPerRoot = Math.floor((1_000 - initialFragments) / initialFragments);
  return Math.min(
    initialFragments * 16,
    initialFragments * (1 + Math.floor(childSlotsPerRoot / 2)),
    1_000,
  );
}

export function minimumVerifierRewardBudget(
  initialFragments: number,
  fragmentQuorum: number,
  rewardPerVote = VERIFIER_REWARD_PER_VOTE,
): anchor.BN {
  return new anchor.BN(maxLeafFragments(initialFragments))
    .mul(new anchor.BN(fragmentQuorum))
    .mul(rewardPerVote);
}

export function resultPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from('result'), job.toBuffer()],
    program.programId,
  )[0];
}

export async function airdrop(pubkey: PublicKey, lamports = 2_000_000_000) {
  const signature = await provider.connection.requestAirdrop(pubkey, lamports);
  await provider.connection.confirmTransaction(signature, 'confirmed');
}

export function assertAnchorError(error: any, expectedCode: string) {
  const text = String(error);
  if (!text.includes(expectedCode)) {
    console.error('Unexpected Anchor error:', text);
  }
  assert.include(text, expectedCode);
}

export async function registerWorker(workerKeypair: anchor.web3.Keypair): Promise<PublicKey> {
  const workerAccount = workerPda(workerKeypair.publicKey);
  const workerPayout = workerPayoutPda(workerAccount);

  await program.methods
    .registerWorker()
    .accounts({
      worker: workerKeypair.publicKey,
      workerAccount,
      workerPayout,
      systemProgram: SystemProgram.programId,
    })
    .signers([workerKeypair])
    .rpc();

  return workerAccount;
}

export async function createWorkerToken(
  mint: PublicKey,
  owner: PublicKey,
  amount = 10_000_000,
): Promise<PublicKey> {
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const authority = provider.wallet.publicKey;

  const token = await createAssociatedTokenAccount(provider.connection, payer, mint, owner);

  await mintTo(provider.connection, payer, mint, token, authority, amount);
  return token;
}

export async function stakeRegisteredWorker(
  mint: PublicKey,
  workerKeypair: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  amount = 1_000_000,
) {
  const stakeAuth = stakeAuthPda(workerAccount);
  const stakeVault = stakeVaultPda(workerKeypair.publicKey);

  await program.methods
    .stakeWorker(new anchor.BN(amount))
    .accounts({
      worker: workerKeypair.publicKey,
      workerAccount,
      mint,
      workerToken,
      stakeAuth,
      stakeVault,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([workerKeypair])
    .rpc();

  return { stakeAuth, stakeVault };
}

export async function createReadyWorker(mint: PublicKey, stakeAmount = 1_000_000) {
  const keypair = anchor.web3.Keypair.generate();
  await airdrop(keypair.publicKey);

  const workerAccount = await registerWorker(keypair);
  const workerToken = await createWorkerToken(mint, keypair.publicKey);
  const stake = await stakeRegisteredWorker(mint, keypair, workerAccount, workerToken, stakeAmount);

  return {
    keypair,
    workerAccount,
    workerToken,
    stakeAuth: stake.stakeAuth,
    stakeVault: stake.stakeVault,
  };
}

export async function createRegisteredUnstakedWorker(mint: PublicKey) {
  const keypair = anchor.web3.Keypair.generate();
  await airdrop(keypair.publicKey);
  const workerAccount = await registerWorker(keypair);
  const workerToken = await createWorkerToken(mint, keypair.publicKey);
  return { keypair, workerAccount, workerToken };
}

export async function createTestJob(
  mint: PublicKey,
  clientToken: PublicKey,
  jobId: anchor.BN,
  expectedFragments = 1,
  fragmentQuorum = DEFAULT_FRAGMENT_QUORUM,
  rewardPerFragment = DEFAULT_REWARD_PER_FRAGMENT,
  verifierRewardPerVote = VERIFIER_REWARD_PER_VOTE,
  verifierRewardBudget = minimumVerifierRewardBudget(
    expectedFragments,
    fragmentQuorum,
    verifierRewardPerVote,
  ),
) {
  const client = provider.wallet.publicKey;
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const job = jobPda(client, jobId);
  const escrowAuth = escrowAuthPda(job);
  const escrow = anchor.web3.Keypair.generate();
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);

  const topUp = rewardPerFragment
    .mul(new anchor.BN(maxLeafFragments(expectedFragments)))
    .add(verifierRewardBudget)
    .add(new anchor.BN(1_000_000));

  await mintTo(provider.connection, payer, mint, clientToken, client, Number(topUp.toString()));

  await program.methods
    .createJob(
      jobId,
      expectedFragments,
      rewardPerFragment,
      verifierRewardPerVote,
      verifierRewardBudget,
      deadlineUnix,
      fragmentQuorum,
    )
    .accounts({
      client,
      mint,
      job,
      escrowAuth,
      escrow: escrow.publicKey,
      clientToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([escrow])
    .rpc();

  return { job, escrow: escrow.publicKey, escrowAuth };
}

export async function claimFragment(
  worker: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  job: PublicKey,
  fragmentIndex: number,
): Promise<PublicKey> {
  const fragment = fragmentPda(job, fragmentIndex);

  await program.methods
    .claimFragment(fragmentIndex)
    .accounts({
      worker: worker.publicKey,
      workerAccount,
      job,
      fragment,
      workerToken,
      systemProgram: SystemProgram.programId,
    })
    .signers([worker])
    .rpc();

  return fragment;
}

export async function submitFragment(
  worker: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  job: PublicKey,
  fragmentIndex: number,
  resultByte: number,
  proofByte: number,
): Promise<PublicKey> {
  const fragment = fragmentPda(job, fragmentIndex);

  await program.methods
    .submitFragmentResult(fragmentIndex, Array(32).fill(resultByte), Array(32).fill(proofByte))
    .accounts({
      worker: worker.publicKey,
      workerAccount,
      job,
      fragment,
      workerToken,
    })
    .signers([worker])
    .rpc();

  return fragment;
}

export async function voteOnFragment(
  verifier: anchor.web3.Keypair,
  verifierWorker: PublicKey,
  job: PublicKey,
  fragment: PublicKey,
  escrow: PublicKey,
  workerToken: PublicKey,
  choice: boolean,
) {
  const fragmentBefore = await program.account.fragment.fetch(fragment);
  const vote = votePda(fragment, verifier.publicKey, fragmentBefore.round);
  const roundResolution = roundResolutionPda(fragment, fragmentBefore.round);
  const computeWorker = workerPda(fragmentBefore.worker);
  const escrowAuth = escrowAuthPda(job);

  await program.methods
    .voteFragment(choice)
    .accounts({
      verifier: verifier.publicKey,
      job,
      fragment,
      verifierWorker,
      computeWorker,
      vote,
      roundResolution,
      escrowAuth,
      escrow,
      workerToken,
      workerPayout: workerPayoutPda(computeWorker),
      workerPayoutToken: workerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier])
    .rpc();

  return { vote, roundResolution };
}

export async function claimVerifierReward(
  verifier: anchor.web3.Keypair,
  verifierWorker: PublicKey,
  verifierToken: PublicKey,
  job: PublicKey,
  fragment: PublicKey,
  escrow: PublicKey,
) {
  const fragmentState = await program.account.fragment.fetch(fragment);
  const round = fragmentState.round;
  const vote = votePda(fragment, verifier.publicKey, round);
  const roundResolution = roundResolutionPda(fragment, round);
  const escrowAuth = escrowAuthPda(job);

  await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: verifier.publicKey,
      job,
      fragment,
      roundResolution,
      vote,
      verifierWorker,
      escrowAuth,
      escrow,
      verifierToken,
      verifierPayout: workerPayoutPda(verifierWorker),
      verifierPayoutToken: verifierToken,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier])
    .rpc();
}

export async function verifyFragmentWithTwoVotes(
  computeWorker: Awaited<ReturnType<typeof createReadyWorker>>,
  verifier1: Awaited<ReturnType<typeof createReadyWorker>>,
  verifier2: Awaited<ReturnType<typeof createReadyWorker>>,
  job: PublicKey,
  escrow: PublicKey,
  fragmentIndex: number,
  resultByte: number,
): Promise<PublicKey> {
  const fragment = await claimFragment(
    computeWorker.keypair,
    computeWorker.workerAccount,
    computeWorker.workerToken,
    job,
    fragmentIndex,
  );

  await submitFragment(
    computeWorker.keypair,
    computeWorker.workerAccount,
    computeWorker.workerToken,
    job,
    fragmentIndex,
    resultByte,
    resultByte + 1,
  );

  await voteOnFragment(
    verifier1.keypair,
    verifier1.workerAccount,
    job,
    fragment,
    escrow,
    computeWorker.workerToken,
    true,
  );

  await voteOnFragment(
    verifier2.keypair,
    verifier2.workerAccount,
    job,
    fragment,
    escrow,
    computeWorker.workerToken,
    true,
  );

  const fragmentAfter = await program.account.fragment.fetch(fragment);
  assert.deepEqual(fragmentAfter.status, { verified: {} });

  return fragment;
}

export async function proposeSplit(
  splitter: Awaited<ReturnType<typeof createReadyWorker>>,
  job: PublicKey,
  parentFragment: PublicKey,
  manifestByte = 7,
  childCount = 2,
): Promise<PublicKey> {
  const parentBefore = await program.account.fragment.fetch(parentFragment);
  const jobAccount = await program.account.job.fetch(job);
  const proposal = splitProposalPda(parentFragment, parentBefore.round);

  await program.methods
    .proposeFragmentSplit(Array(32).fill(manifestByte), childCount)
    .accounts({
      splitter: splitter.keypair.publicKey,
      splitterWorker: splitter.workerAccount,
      job,
      parentFragment,
      splitProposal: proposal,
      escrow: jobAccount.escrow,
      systemProgram: SystemProgram.programId,
    })
    .signers([splitter.keypair])
    .rpc();

  return proposal;
}

export async function approveSplit(
  job: PublicKey,
  parentFragment: PublicKey,
  proposal: PublicKey,
  approve = true,
) {
  await program.methods
    .approveFragmentSplit(approve)
    .accounts({
      authority: provider.wallet.publicKey,
      job,
      parentFragment,
      splitProposal: proposal,
    })
    .rpc();
}

export async function createSubFragment(
  job: PublicKey,
  parentFragment: PublicKey,
  proposal: PublicKey,
  childIndex: number,
  requiredReputation = 1_500,
  requiredStake = 1,
  complexityScore = 3_000,
  inputByte = 44,
): Promise<PublicKey> {
  const child = fragmentPda(job, childIndex);

  await program.methods
    .createSubFragment(
      childIndex,
      new anchor.BN(requiredReputation),
      new anchor.BN(requiredStake),
      complexityScore,
      Array(32).fill(inputByte),
    )
    .accounts({
      payer: provider.wallet.publicKey,
      job,
      parentFragment,
      splitProposal: proposal,
      childFragment: child,
      systemProgram: SystemProgram.programId,
    })
    .rpc();

  return child;
}

export async function setupClaimedParent(
  mint: PublicKey,
  clientToken: PublicKey,
  jobIdNumber: number,
  expectedFragments = 1,
) {
  const splitter = await createReadyWorker(mint, 1_000_000);
  const { job, escrow } = await createTestJob(
    mint,
    clientToken,
    new anchor.BN(jobIdNumber),
    expectedFragments,
    DEFAULT_FRAGMENT_QUORUM,
  );

  const parentFragment = await claimFragment(
    splitter.keypair,
    splitter.workerAccount,
    splitter.workerToken,
    job,
    0,
  );

  return { splitter, job, escrow, parentFragment };
}
