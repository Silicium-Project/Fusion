/**
 * Full local V2 flow for Silicium / solana-layer.
 *
 * Put this file in:
 *   scripts/silicium_v2_full_flow.ts
 *
 * Run after your V2 program and SDK are updated:
 *   anchor build
 *   npx ts-node scripts/silicium_v2_full_flow.ts
 *
 * What this script does:
 * 1. Creates a local SPL mint and client token account.
 * 2. Registers and stakes: one splitter, one compute worker, two verifiers.
 * 3. Creates a job with 2 root fragments.
 * 4. Claims fragment 0 as parent and splits it into two sub-fragments.
 * 5. Processes fragment 1 normally.
 * 6. Processes sub-fragments 2 and 3 normally.
 * 7. Claims all verifier rewards.
 * 8. Finalizes the mixed V1/V2 job.
 *
 * Assumptions:
 * - You are running against localnet/test validator through AnchorProvider.env().
 * - SPLIT_MIN_REPUTATION is compatible with local test workers, usually 5_000.
 * - SPLIT_MIN_COMPLEXITY is compatible with local test fragments, usually <= 3_000.
 */

import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { PublicKey, SystemProgram, SYSVAR_RENT_PUBKEY } from "@solana/web3.js";
import {
  TOKEN_PROGRAM_ID,
  createAssociatedTokenAccount,
  createMint,
  mintTo,
} from "@solana/spl-token";

const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer as Program<any>;

// Anchor generated types can be extremely deep with ts-node and Program<any>.
// Use an untyped facade for method/account namespaces in this executable example.
const programAny = program as any;

const REWARD_PER_FRAGMENT = new anchor.BN(100_000);
const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);
const VERIFIER_REWARD_BUDGET = new anchor.BN(2_000_000);
const FRAGMENT_QUORUM = 2;

function logStep(title: string) {
  console.log(`\n=== ${title} ===`);
}

function u32le(n: number): Buffer {
  const buf = Buffer.alloc(4);
  buf.writeUInt32LE(n, 0);
  return buf;
}

function u16le(n: number): Buffer {
  const buf = Buffer.alloc(2);
  buf.writeUInt16LE(n, 0);
  return buf;
}

function jobPda(client: PublicKey, jobId: anchor.BN): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
    program.programId,
  )[0];
}

function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), job.toBuffer()],
    program.programId,
  )[0];
}

function fragmentPda(job: PublicKey, fragmentIndex: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment"), job.toBuffer(), u32le(fragmentIndex)],
    program.programId,
  )[0];
}

function splitProposalPda(parentFragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("split_proposal"), parentFragment.toBuffer(), u16le(round)],
    program.programId,
  )[0];
}

function workerPda(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("worker"), worker.toBuffer()],
    program.programId,
  )[0];
}

function stakeAuthPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_auth"), workerAccount.toBuffer()],
    program.programId,
  )[0];
}

function stakeVaultPda(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_vault"), worker.toBuffer()],
    program.programId,
  )[0];
}

function votePda(fragment: PublicKey, verifier: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment_vote"), fragment.toBuffer(), verifier.toBuffer(), u16le(round)],
    program.programId,
  )[0];
}

function roundResolutionPda(fragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment_resolution"), fragment.toBuffer(), u16le(round)],
    program.programId,
  )[0];
}

function resultPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("result"), job.toBuffer()],
    program.programId,
  )[0];
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function airdrop(pubkey: PublicKey, lamports = 2_000_000_000) {
  const sig = await provider.connection.requestAirdrop(pubkey, lamports);
  await provider.connection.confirmTransaction(sig, "confirmed");
  await sleep(400);
}

async function registerWorker(worker: anchor.web3.Keypair): Promise<PublicKey> {
  const workerAccount = workerPda(worker.publicKey);

  const sig = await programAny.methods
    .registerWorker()
    .accounts({
      worker: worker.publicKey,
      workerAccount,
      systemProgram: SystemProgram.programId,
    })
    .signers([worker])
    .rpc();

  console.log("registered worker", worker.publicKey.toBase58(), sig);
  return workerAccount;
}

async function createFundedTokenAccount(
  mint: PublicKey,
  owner: PublicKey,
  amount = 10_000_000,
): Promise<PublicKey> {
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const mintAuthority = provider.wallet.publicKey;

  const tokenAccount = await createAssociatedTokenAccount(
    provider.connection,
    payer,
    mint,
    owner,
  );

  await mintTo(
    provider.connection,
    payer,
    mint,
    tokenAccount,
    mintAuthority,
    amount,
  );

  return tokenAccount;
}

async function stakeWorker(params: {
  mint: PublicKey;
  worker: anchor.web3.Keypair;
  workerAccount: PublicKey;
  workerToken: PublicKey;
  amount?: number;
}) {
  const stakeAuth = stakeAuthPda(params.workerAccount);
  const stakeVault = stakeVaultPda(params.worker.publicKey);

  const sig = await programAny.methods
    .stakeWorker(new anchor.BN(params.amount ?? 1_000_000))
    .accounts({
      worker: params.worker.publicKey,
      workerAccount: params.workerAccount,
      mint: params.mint,
      workerToken: params.workerToken,
      stakeAuth,
      stakeVault,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([params.worker])
    .rpc();

  console.log("staked worker", params.worker.publicKey.toBase58(), sig);
  return { stakeAuth, stakeVault };
}

type ReadyWorker = {
  keypair: anchor.web3.Keypair;
  workerAccount: PublicKey;
  workerToken: PublicKey;
};

async function createReadyWorker(mint: PublicKey, label: string): Promise<ReadyWorker> {
  const keypair = anchor.web3.Keypair.generate();
  await airdrop(keypair.publicKey);

  const workerAccount = await registerWorker(keypair);
  const workerToken = await createFundedTokenAccount(mint, keypair.publicKey);

  await stakeWorker({
    mint,
    worker: keypair,
    workerAccount,
    workerToken,
    amount: 1_000_000,
  });

  const workerState = await programAny.account.worker.fetch(workerAccount);
  console.log(label, {
    owner: keypair.publicKey.toBase58(),
    workerAccount: workerAccount.toBase58(),
    token: workerToken.toBase58(),
    reputation: Number(workerState.reputation.toString()),
    stakeAmount: Number(workerState.stakeAmount.toString()),
  });

  return { keypair, workerAccount, workerToken };
}

async function createJob(params: {
  mint: PublicKey;
  clientToken: PublicKey;
  jobId: anchor.BN;
  expectedFragments: number;
}) {
  const client = provider.wallet.publicKey;
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const job = jobPda(client, params.jobId);
  const escrowAuth = escrowAuthPda(job);
  const escrow = anchor.web3.Keypair.generate();
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);

  const topUp = REWARD_PER_FRAGMENT
    .mul(new anchor.BN(params.expectedFragments))
    .add(VERIFIER_REWARD_BUDGET)
    .add(new anchor.BN(2_000_000));

  await mintTo(
    provider.connection,
    payer,
    params.mint,
    params.clientToken,
    client,
    Number(topUp.toString()),
  );

  const sig = await programAny.methods
    .createJob(
      params.jobId,
      params.expectedFragments,
      REWARD_PER_FRAGMENT,
      VERIFIER_REWARD_PER_VOTE,
      VERIFIER_REWARD_BUDGET,
      deadlineUnix,
      FRAGMENT_QUORUM,
    )
    .accounts({
      client,
      mint: params.mint,
      job,
      escrowAuth,
      escrow: escrow.publicKey,
      clientToken: params.clientToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([escrow])
    .rpc();

  console.log("created job", {
    signature: sig,
    job: job.toBase58(),
    escrow: escrow.publicKey.toBase58(),
    expectedFragments: params.expectedFragments,
  });

  return { job, escrow: escrow.publicKey, escrowAuth };
}

async function claimFragment(
  worker: ReadyWorker,
  job: PublicKey,
  fragmentIndex: number,
): Promise<PublicKey> {
  const fragment = fragmentPda(job, fragmentIndex);

  const sig = await programAny.methods
    .claimFragment(fragmentIndex)
    .accounts({
      worker: worker.keypair.publicKey,
      workerAccount: worker.workerAccount,
      job,
      fragment,
      workerToken: worker.workerToken,
      systemProgram: SystemProgram.programId,
    })
    .signers([worker.keypair])
    .rpc();

  console.log("claimed fragment", fragmentIndex, fragment.toBase58(), sig);
  return fragment;
}

async function submitFragment(
  worker: ReadyWorker,
  job: PublicKey,
  fragmentIndex: number,
  resultByte: number,
): Promise<PublicKey> {
  const fragment = fragmentPda(job, fragmentIndex);

  const sig = await programAny.methods
    .submitFragmentResult(
      fragmentIndex,
      Array(32).fill(resultByte),
      Array(32).fill(resultByte + 1),
    )
    .accounts({
      worker: worker.keypair.publicKey,
      workerAccount: worker.workerAccount,
      job,
      fragment,
      workerToken: worker.workerToken,
    })
    .signers([worker.keypair])
    .rpc();

  console.log("submitted fragment", fragmentIndex, sig);
  return fragment;
}

async function voteOnFragment(params: {
  verifier: ReadyWorker;
  job: PublicKey;
  fragment: PublicKey;
  escrow: PublicKey;
  workerToken: PublicKey;
  choice: boolean;
}) {
  const fragmentBefore = await programAny.account.fragment.fetch(params.fragment);
  const round = Number(fragmentBefore.round);
  const vote = votePda(params.fragment, params.verifier.keypair.publicKey, round);
  const roundResolution = roundResolutionPda(params.fragment, round);
  const computeWorker = workerPda(fragmentBefore.worker);
  const escrowAuth = escrowAuthPda(params.job);

  const sig = await programAny.methods
    .voteFragment(params.choice)
    .accounts({
      verifier: params.verifier.keypair.publicKey,
      job: params.job,
      fragment: params.fragment,
      verifierWorker: params.verifier.workerAccount,
      computeWorker,
      vote,
      roundResolution,
      escrowAuth,
      escrow: params.escrow,
      workerToken: params.workerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([params.verifier.keypair])
    .rpc();

  console.log("voted", params.choice ? "YES" : "NO", params.fragment.toBase58(), sig);
  return { vote, roundResolution };
}

async function verifyFragmentWithTwoVotes(params: {
  computeWorker: ReadyWorker;
  verifier1: ReadyWorker;
  verifier2: ReadyWorker;
  job: PublicKey;
  escrow: PublicKey;
  fragmentIndex: number;
  resultByte: number;
}): Promise<PublicKey> {
  const fragment = await claimFragment(params.computeWorker, params.job, params.fragmentIndex);
  await submitFragment(params.computeWorker, params.job, params.fragmentIndex, params.resultByte);

  await voteOnFragment({
    verifier: params.verifier1,
    job: params.job,
    fragment,
    escrow: params.escrow,
    workerToken: params.computeWorker.workerToken,
    choice: true,
  });

  await voteOnFragment({
    verifier: params.verifier2,
    job: params.job,
    fragment,
    escrow: params.escrow,
    workerToken: params.computeWorker.workerToken,
    choice: true,
  });

  const fragmentAfter = await programAny.account.fragment.fetch(fragment);
  if (!fragmentAfter.status.verified) {
    throw new Error(`Fragment ${params.fragmentIndex} was not verified`);
  }

  console.log("verified fragment", params.fragmentIndex);
  return fragment;
}

async function claimVerifierReward(params: {
  verifier: ReadyWorker;
  job: PublicKey;
  fragment: PublicKey;
  escrow: PublicKey;
}) {
  const fragmentState = await programAny.account.fragment.fetch(params.fragment);
  const round = Number(fragmentState.round);
  const vote = votePda(params.fragment, params.verifier.keypair.publicKey, round);
  const roundResolution = roundResolutionPda(params.fragment, round);
  const escrowAuth = escrowAuthPda(params.job);

  const sig = await programAny.methods
    .claimVerifierReward()
    .accounts({
      verifier: params.verifier.keypair.publicKey,
      job: params.job,
      fragment: params.fragment,
      roundResolution,
      vote,
      verifierWorker: params.verifier.workerAccount,
      escrowAuth,
      escrow: params.escrow,
      verifierToken: params.verifier.workerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([params.verifier.keypair])
    .rpc();

  console.log("claimed verifier reward", params.verifier.keypair.publicKey.toBase58(), sig);
}

async function proposeAndCreateSplit(params: {
  splitter: ReadyWorker;
  job: PublicKey;
  parentFragment: PublicKey;
  childIndexes: number[];
}): Promise<PublicKey[]> {
  const parentBefore = await programAny.account.fragment.fetch(params.parentFragment);
  const parentRound = Number(parentBefore.round);
  const splitProposal = splitProposalPda(params.parentFragment, parentRound);

  const manifestHash = Array(32).fill(77);

  logStep("Propose split");
  const proposeSig = await programAny.methods
    .proposeFragmentSplit(manifestHash, params.childIndexes.length)
    .accounts({
      splitter: params.splitter.keypair.publicKey,
      splitterWorker: params.splitter.workerAccount,
      job: params.job,
      parentFragment: params.parentFragment,
      splitProposal,
      systemProgram: SystemProgram.programId,
    })
    .signers([params.splitter.keypair])
    .rpc();

  console.log("proposed split", { splitProposal: splitProposal.toBase58(), proposeSig });

  logStep("Approve split");
  const approveSig = await programAny.methods
    .approveFragmentSplit(true)
    .accounts({
      authority: provider.wallet.publicKey,
      job: params.job,
      parentFragment: params.parentFragment,
      splitProposal,
    })
    .rpc();

  console.log("approved split", approveSig);

  logStep("Create sub-fragments");
  const childFragments: PublicKey[] = [];

  for (let i = 0; i < params.childIndexes.length; i++) {
    const childIndex = params.childIndexes[i];
    const childFragment = fragmentPda(params.job, childIndex);

    const createSig = await programAny.methods
      .createSubFragment(
        childIndex,
        new anchor.BN(1_500),
        new anchor.BN(1),
        3_000 + i,
        Array(32).fill(90 + i),
      )
      .accounts({
        payer: provider.wallet.publicKey,
        job: params.job,
        parentFragment: params.parentFragment,
        splitProposal,
        childFragment,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    console.log("created sub-fragment", childIndex, childFragment.toBase58(), createSig);
    childFragments.push(childFragment);
  }

  const parentAfter = await programAny.account.fragment.fetch(params.parentFragment);
  const proposalAfter = await programAny.account.splitProposal.fetch(splitProposal);
  const jobAfter = await programAny.account.job.fetch(params.job);

  console.log("parent status after split:", parentAfter.status);
  console.log("proposal createdChildren:", Number(proposalAfter.createdChildren));
  console.log("job expectedFragments after split:", Number(jobAfter.expectedFragments));

  return childFragments;
}

async function main() {
  logStep("Provider");
  console.log("wallet", provider.wallet.publicKey.toBase58());
  console.log("program", program.programId.toBase58());

  logStep("Create mint and client token account");
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const client = provider.wallet.publicKey;

  const mint = await createMint(provider.connection, payer, client, null, 6);
  const clientToken = await createAssociatedTokenAccount(
    provider.connection,
    payer,
    mint,
    client,
  );

  await mintTo(provider.connection, payer, mint, clientToken, client, 100_000_000);

  console.log("mint", mint.toBase58());
  console.log("clientToken", clientToken.toBase58());

  logStep("Create ready participants");
  const splitter = await createReadyWorker(mint, "splitter");
  const computeWorker = await createReadyWorker(mint, "computeWorker");
  const verifier1 = await createReadyWorker(mint, "verifier1");
  const verifier2 = await createReadyWorker(mint, "verifier2");

  logStep("Create V2 mixed job");
  const jobId = new anchor.BN(Date.now());
  const { job, escrow } = await createJob({
    mint,
    clientToken,
    jobId,
    expectedFragments: 2,
  });

  logStep("Claim parent fragment 0 by splitter");
  const parentFragment = await claimFragment(splitter, job, 0);

  const childIndexes = [2, 3];
  const childFragments = await proposeAndCreateSplit({
    splitter,
    job,
    parentFragment,
    childIndexes,
  });

  logStep("Process normal V1 leaf fragment 1");
  const normalLeaf = await verifyFragmentWithTwoVotes({
    computeWorker,
    verifier1,
    verifier2,
    job,
    escrow,
    fragmentIndex: 1,
    resultByte: 41,
  });

  logStep("Process V2 sub-fragment 2");
  const child2 = await verifyFragmentWithTwoVotes({
    computeWorker,
    verifier1,
    verifier2,
    job,
    escrow,
    fragmentIndex: 2,
    resultByte: 42,
  });

  logStep("Process V2 sub-fragment 3");
  const child3 = await verifyFragmentWithTwoVotes({
    computeWorker,
    verifier1,
    verifier2,
    job,
    escrow,
    fragmentIndex: 3,
    resultByte: 43,
  });

  logStep("Check job before verifier reward claims");
  const jobBeforeRewards = await programAny.account.job.fetch(job);
  console.log({
    expectedFragments: Number(jobBeforeRewards.expectedFragments),
    verifiedFragments: Number(jobBeforeRewards.verifiedFragments),
    claimableVerifierRewardsTotal: Number(jobBeforeRewards.claimableVerifierRewardsTotal),
    claimedVerifierRewardsTotal: Number(jobBeforeRewards.claimedVerifierRewardsTotal),
    status: jobBeforeRewards.status,
  });

  logStep("Claim verifier rewards");
  for (const fragment of [normalLeaf, child2, child3]) {
    await claimVerifierReward({ verifier: verifier1, job, fragment, escrow });
    await claimVerifierReward({ verifier: verifier2, job, fragment, escrow });
  }

  logStep("Finalize job");
  const result = resultPda(job);
  const finalizeSig = await programAny.methods
    .finalizeJob(Array(32).fill(123), Buffer.from("ipfs://silicium-v2-full-flow-result"))
    .accounts({
      client,
      job,
      result,
      escrowAuth: escrowAuthPda(job),
      escrow,
      clientToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .rpc();

  const finalJob = await programAny.account.job.fetch(job);
  const finalResult = await programAny.account.jobResult.fetch(result);

  console.log("finalize tx", finalizeSig);
  console.log("final job", {
    status: finalJob.status,
    expectedFragments: Number(finalJob.expectedFragments),
    verifiedFragments: Number(finalJob.verifiedFragments),
    paidAmount: Number(finalJob.paidAmount),
    claimedVerifierRewardsTotal: Number(finalJob.claimedVerifierRewardsTotal),
  });
  console.log("final result", {
    result: result.toBase58(),
    finalHash: finalResult.finalHash,
  });

  if (!finalJob.status.finalized) {
    throw new Error("Full V2 flow finished but job is not finalized");
  }

  if (Number(finalJob.expectedFragments) !== 3 || Number(finalJob.verifiedFragments) !== 3) {
    throw new Error("Full V2 flow finished with unexpected fragment counters");
  }

  console.log("\n✅ Full V2 flow completed successfully");
  console.log("Job:", job.toBase58());
  console.log("Parent fragment:", parentFragment.toBase58());
  console.log("Child fragments:", childFragments.map((p) => p.toBase58()).join(", "));
  console.log("Result:", result.toBase58());
}

main().catch((error) => {
  console.error("\n❌ Full V2 flow failed");
  console.error(error);
  process.exit(1);
});
