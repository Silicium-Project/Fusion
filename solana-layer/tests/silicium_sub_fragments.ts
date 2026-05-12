import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { PublicKey, SystemProgram, SYSVAR_RENT_PUBKEY } from "@solana/web3.js";
import { assert } from "chai";
import {
  TOKEN_PROGRAM_ID,
  createMint,
  createAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";

const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer as Program;

const ZERO_PUBKEY = new PublicKey(new Uint8Array(32));
const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);
const VERIFIER_REWARD_BUDGET = new anchor.BN(2_000_000);

// Important pour ce test local :
// - soit baisser SPLIT_MIN_REPUTATION à 5_000 dans constants.rs,
// - soit créer un worker premium avec reputation >= 8_500 dans un setup dédié.
// Même chose pour la complexité : avec le claim_fragment actuel, un fragment racine a
// DEFAULT_ROOT_COMPLEXITY_SCORE = 1_000. Il faut donc soit baisser SPLIT_MIN_COMPLEXITY
// à 1_000 en test local, soit initialiser les fragments racine avec une complexité >= 6_000.

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
    program.programId
  )[0];
}

function fragmentPda(job: PublicKey, fragmentIndex: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment"), job.toBuffer(), u32le(fragmentIndex)],
    program.programId
  )[0];
}

function splitProposalPda(parentFragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("split_proposal"), parentFragment.toBuffer(), u16le(round)],
    program.programId
  )[0];
}

function workerPda(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("worker"), worker.toBuffer()],
    program.programId
  )[0];
}

function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), job.toBuffer()],
    program.programId
  )[0];
}

function stakeAuthPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_auth"), workerAccount.toBuffer()],
    program.programId
  )[0];
}

function stakeVaultPda(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_vault"), worker.toBuffer()],
    program.programId
  )[0];
}

function votePda(fragment: PublicKey, verifier: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment_vote"), fragment.toBuffer(), verifier.toBuffer(), u16le(round)],
    program.programId
  )[0];
}

function roundResolutionPda(fragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment_resolution"), fragment.toBuffer(), u16le(round)],
    program.programId
  )[0];
}

async function airdrop(pubkey: PublicKey, lamports = 2_000_000_000) {
  await provider.connection.requestAirdrop(pubkey, lamports);
  await sleep(1000);
}

async function registerWorker(workerKeypair: anchor.web3.Keypair): Promise<PublicKey> {
  const workerAccount = workerPda(workerKeypair.publicKey);

  await program.methods
    .registerWorker()
    .accounts({
      worker: workerKeypair.publicKey,
      workerAccount,
      systemProgram: SystemProgram.programId,
    })
    .signers([workerKeypair])
    .rpc();

  return workerAccount;
}

async function createWorkerToken(
  mint: PublicKey,
  owner: PublicKey,
  amount = 10_000_000
): Promise<PublicKey> {
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const authority = provider.wallet.publicKey;

  const token = await createAssociatedTokenAccount(
    provider.connection,
    payer,
    mint,
    owner
  );

  await mintTo(
    provider.connection,
    payer,
    mint,
    token,
    authority,
    amount
  );

  return token;
}

async function stakeRegisteredWorker(
  mint: PublicKey,
  workerKeypair: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  amount = 1_000_000
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

async function createReadyWorker(mint: PublicKey, stakeAmount = 1_000_000) {
  const keypair = anchor.web3.Keypair.generate();
  await airdrop(keypair.publicKey);

  const workerAccount = await registerWorker(keypair);
  const workerToken = await createWorkerToken(mint, keypair.publicKey);
  const stake = await stakeRegisteredWorker(
    mint,
    keypair,
    workerAccount,
    workerToken,
    stakeAmount
  );

  return {
    keypair,
    workerAccount,
    workerToken,
    stakeAuth: stake.stakeAuth,
    stakeVault: stake.stakeVault,
  };
}

async function createTestJob(
  mint: PublicKey,
  clientToken: PublicKey,
  jobId: anchor.BN,
  expectedFragments = 1,
  fragmentQuorum = 2,
  rewardPerFragment = new anchor.BN(100_000),
  verifierRewardPerVote = VERIFIER_REWARD_PER_VOTE,
  verifierRewardBudget = VERIFIER_REWARD_BUDGET
) {
  const client = provider.wallet.publicKey;
  const payer = provider.wallet.payer as anchor.web3.Keypair;

  const job = jobPda(client, jobId);
  const escrowAuth = escrowAuthPda(job);
  const escrow = anchor.web3.Keypair.generate();
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);

  const totalToMint = rewardPerFragment
    .mul(new anchor.BN(expectedFragments))
    .add(verifierRewardBudget)
    .add(new anchor.BN(1_000_000));

  await mintTo(
    provider.connection,
    payer,
    mint,
    clientToken,
    client,
    Number(totalToMint.toString())
  );

  await program.methods
    .createJob(
      jobId,
      expectedFragments,
      rewardPerFragment,
      verifierRewardPerVote,
      verifierRewardBudget,
      deadlineUnix,
      fragmentQuorum
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

async function claimFragment(
  worker: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  job: PublicKey,
  fragmentIndex: number
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

async function submitFragment(
  worker: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  job: PublicKey,
  fragmentIndex: number,
  resultByte: number,
  proofByte: number
): Promise<PublicKey> {
  const fragment = fragmentPda(job, fragmentIndex);

  await program.methods
    .submitFragmentResult(
      fragmentIndex,
      Array(32).fill(resultByte),
      Array(32).fill(proofByte)
    )
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

async function voteOnFragment(
  verifier: anchor.web3.Keypair,
  verifierWorker: PublicKey,
  job: PublicKey,
  fragment: PublicKey,
  escrow: PublicKey,
  workerToken: PublicKey,
  choice: boolean
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
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier])
    .rpc();

  return { vote, roundResolution };
}

describe("silicium v2 - sub fragments", () => {
  let mint: PublicKey;
  let clientToken: PublicKey;

  before(async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    mint = await createMint(provider.connection, payer, client, null, 6);
    clientToken = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      mint,
      client
    );

    await mintTo(provider.connection, payer, mint, clientToken, client, 50_000_000);
  });

  it("splits one root fragment into sub-fragments, then processes one sub-fragment", async () => {
    const splitter = await createReadyWorker(mint, 1_000_000);
    const childWorker = await createReadyWorker(mint, 1_000_000);
    const verifier1 = await createReadyWorker(mint, 1_000_000);
    const verifier2 = await createReadyWorker(mint, 1_000_000);

    const jobId = new anchor.BN(900);
    const { job, escrow } = await createTestJob(
      mint,
      clientToken,
      jobId,
      1,
      2,
      new anchor.BN(100_000),
      VERIFIER_REWARD_PER_VOTE,
      VERIFIER_REWARD_BUDGET
    );

    const parentIndex = 0;
    const parentFragment = await claimFragment(
      splitter.keypair,
      splitter.workerAccount,
      splitter.workerToken,
      job,
      parentIndex
    );

    const parentBeforeSplit = await program.account.fragment.fetch(parentFragment);
    assert.deepEqual(parentBeforeSplit.status, { claimed: {} });
    assert.equal(parentBeforeSplit.isLeaf, true);
    assert.equal(parentBeforeSplit.depth, 0);

    const proposal = splitProposalPda(parentFragment, parentBeforeSplit.round);
    const manifestHash = Array(32).fill(9);
    const childCount = 3;

    await program.methods
      .proposeFragmentSplit(manifestHash, childCount)
      .accounts({
        splitter: splitter.keypair.publicKey,
        splitterWorker: splitter.workerAccount,
        job,
        parentFragment,
        splitProposal: proposal,
        systemProgram: SystemProgram.programId,
      })
      .signers([splitter.keypair])
      .rpc();

    const parentAfterProposal = await program.account.fragment.fetch(parentFragment);
    const proposalAfterCreate = await program.account.splitProposal.fetch(proposal);

    assert.deepEqual(parentAfterProposal.status, { splitPending: {} });
    assert.deepEqual(parentAfterProposal.splitManifestHash, manifestHash);
    assert.equal(parentAfterProposal.childrenCount, childCount);
    assert.equal(proposalAfterCreate.approved, false);
    assert.equal(proposalAfterCreate.childCount, childCount);

    await program.methods
      .approveFragmentSplit(true)
      .accounts({
        authority: provider.wallet.publicKey,
        job,
        parentFragment,
        splitProposal: proposal,
      })
      .rpc();

    const jobAfterApproval = await program.account.job.fetch(job);
    const parentAfterApproval = await program.account.fragment.fetch(parentFragment);
    const proposalAfterApproval = await program.account.splitProposal.fetch(proposal);

    assert.deepEqual(parentAfterApproval.status, { splitApproved: {} });
    assert.equal(parentAfterApproval.isLeaf, false);
    assert.equal(proposalAfterApproval.approved, true);
    assert.equal(jobAfterApproval.expectedFragments, 3);
    assert.equal(jobAfterApproval.totalFragmentsCreated, 4);

    const childIndexes = [1, 2, 3];

    for (const childIndex of childIndexes) {
      const child = fragmentPda(job, childIndex);
      const inputHash = Array(32).fill(20 + childIndex);

      await program.methods
        .createSubFragment(
          childIndex,
          new anchor.BN(1_500),
          new anchor.BN(1),
          3_000 + childIndex,
          inputHash
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

      const childAccount = await program.account.fragment.fetch(child);
      assert.equal(childAccount.job.toBase58(), job.toBase58());
      assert.equal(childAccount.fragmentIndex, childIndex);
      assert.equal(childAccount.parentFragment.toBase58(), parentFragment.toBase58());
      assert.equal(childAccount.depth, 1);
      assert.equal(childAccount.isLeaf, true);
      assert.deepEqual(childAccount.status, { available: {} });
      assert.deepEqual(childAccount.proofRef, inputHash);
      assert.equal(childAccount.requiredReputation.toString(), "1500");
      assert.equal(childAccount.requiredStake.toString(), "1");
    }

    const parentAfterChildren = await program.account.fragment.fetch(parentFragment);
    const proposalAfterChildren = await program.account.splitProposal.fetch(proposal);

    assert.deepEqual(parentAfterChildren.status, { splitParent: {} });
    assert.equal(parentAfterChildren.isLeaf, false);
    assert.equal(proposalAfterChildren.createdChildren, childCount);

    const firstChildIndex = 1;
    const firstChild = await claimFragment(
      childWorker.keypair,
      childWorker.workerAccount,
      childWorker.workerToken,
      job,
      firstChildIndex
    );

    await submitFragment(
      childWorker.keypair,
      childWorker.workerAccount,
      childWorker.workerToken,
      job,
      firstChildIndex,
      31,
      32
    );

    await voteOnFragment(
      verifier1.keypair,
      verifier1.workerAccount,
      job,
      firstChild,
      escrow,
      childWorker.workerToken,
      true
    );

    const childAfterOneVote = await program.account.fragment.fetch(firstChild);
    assert.deepEqual(childAfterOneVote.status, { submitted: {} });
    assert.equal(childAfterOneVote.yesVotes, 1);

    await voteOnFragment(
      verifier2.keypair,
      verifier2.workerAccount,
      job,
      firstChild,
      escrow,
      childWorker.workerToken,
      true
    );

    const childAfterQuorum = await program.account.fragment.fetch(firstChild);
    const jobAfterOneChild = await program.account.job.fetch(job);
    const childWorkerAfter = await program.account.worker.fetch(childWorker.workerAccount);

    assert.deepEqual(childAfterQuorum.status, { verified: {} });
    assert.equal(jobAfterOneChild.verifiedFragments, 1);
    assert.equal(jobAfterOneChild.expectedFragments, 3);
    assert.isAbove(Number(childWorkerAfter.reputation.toString()), 5_000);
  });

  it("rejects claiming a split parent directly", async () => {
    const splitter = await createReadyWorker(mint, 1_000_000);
    const otherWorker = await createReadyWorker(mint, 1_000_000);

    const jobId = new anchor.BN(901);
    const { job } = await createTestJob(
      mint,
      clientToken,
      jobId,
      1,
      2,
      new anchor.BN(100_000),
      VERIFIER_REWARD_PER_VOTE,
      VERIFIER_REWARD_BUDGET
    );

    const parentFragment = await claimFragment(
      splitter.keypair,
      splitter.workerAccount,
      splitter.workerToken,
      job,
      0
    );

    const parentBeforeSplit = await program.account.fragment.fetch(parentFragment);
    const proposal = splitProposalPda(parentFragment, parentBeforeSplit.round);

    await program.methods
      .proposeFragmentSplit(Array(32).fill(7), 2)
      .accounts({
        splitter: splitter.keypair.publicKey,
        splitterWorker: splitter.workerAccount,
        job,
        parentFragment,
        splitProposal: proposal,
        systemProgram: SystemProgram.programId,
      })
      .signers([splitter.keypair])
      .rpc();

    await program.methods
      .approveFragmentSplit(true)
      .accounts({
        authority: provider.wallet.publicKey,
        job,
        parentFragment,
        splitProposal: proposal,
      })
      .rpc();

    for (const childIndex of [1, 2]) {
      await program.methods
        .createSubFragment(
          childIndex,
          new anchor.BN(1_500),
          new anchor.BN(1),
          2_000 + childIndex,
          Array(32).fill(40 + childIndex)
        )
        .accounts({
          payer: provider.wallet.publicKey,
          job,
          parentFragment,
          splitProposal: proposal,
          childFragment: fragmentPda(job, childIndex),
          systemProgram: SystemProgram.programId,
        })
        .rpc();
    }

    const parent = await program.account.fragment.fetch(parentFragment);
    assert.deepEqual(parent.status, { splitParent: {} });
    assert.equal(parent.isLeaf, false);

    try {
      await program.methods
        .claimFragment(0)
        .accounts({
          worker: otherWorker.keypair.publicKey,
          workerAccount: otherWorker.workerAccount,
          job,
          fragment: parentFragment,
          workerToken: otherWorker.workerToken,
          systemProgram: SystemProgram.programId,
        })
        .signers([otherWorker.keypair])
        .rpc();

      assert.fail("claimFragment should reject a SplitParent / non-leaf fragment");
    } catch (e: any) {
      assert.include(String(e), "BadFragmentState");
    }
  });
});
