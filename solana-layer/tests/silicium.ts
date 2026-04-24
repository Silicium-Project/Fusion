import * as anchor from "@coral-xyz/anchor";
import { Program, BN } from "@coral-xyz/anchor";
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

const program = anchor.workspace.SolanaLayer as Program<any>;
const payer = provider.wallet.payer as anchor.web3.Keypair;
const client = provider.wallet.publicKey;

const REWARD_PER_FRAGMENT = new BN(1_000_000);
const VERIFIER_REWARD_PER_VOTE = new BN(100_000);
const QUORUM = 2;

let sharedWorkerToken: PublicKey;
let sharedMint: PublicKey;
let sharedEscrow: PublicKey;

let verifierKeypair: anchor.web3.Keypair;
let verifierToken: PublicKey;

let rejectedJobId = new BN(2);
let rejectedJob: PublicKey;
let rejectedFragment: PublicKey;
let rejectedEscrow: PublicKey;

let finalizeJobId = new BN(3);
let finalizeJob: PublicKey;
let finalizeEscrow: PublicKey;

let slashJobId = new BN(4);

function u16le(value: number): Buffer {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(value, 0);
  return b;
}

function u32le(value: number): Buffer {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(value, 0);
  return b;
}

function u64le(value: BN): Buffer {
  return value.toArrayLike(Buffer, "le", 8);
}

function workerPda(owner: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("worker"), owner.toBuffer()],
    program.programId
  )[0];
}

function stakeAuthPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_auth"), workerAccount.toBuffer()],
    program.programId
  )[0];
}

function stakeVaultPda(owner: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_vault"), owner.toBuffer()],
    program.programId
  )[0];
}

function jobPda(clientPk: PublicKey, jobId: BN): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("job"), clientPk.toBuffer(), u64le(jobId)],
    program.programId
  )[0];
}

function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), job.toBuffer()],
    program.programId
  )[0];
}

function fragmentPda(job: PublicKey, fragmentIndex: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment"), job.toBuffer(), u32le(fragmentIndex)],
    program.programId
  )[0];
}

function votePda(fragment: PublicKey, verifier: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [
      Buffer.from("fragment_vote"),
      fragment.toBuffer(),
      verifier.toBuffer(),
      u16le(round),
    ],
    program.programId
  )[0];
}

function resolutionPda(fragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [
      Buffer.from("fragment_resolution"),
      fragment.toBuffer(),
      u16le(round),
    ],
    program.programId
  )[0];
}

function resultPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("result"), job.toBuffer()],
    program.programId
  )[0];
}

function verifierBudget(expectedFragments: number): BN {
  return new BN(
    expectedFragments * QUORUM * VERIFIER_REWARD_PER_VOTE.toNumber()
  );
}

async function airdrop(pk: PublicKey, amount = 2_000_000_000) {
  await provider.connection.requestAirdrop(pk, amount);
  await new Promise((r) => setTimeout(r, 1000));
}

async function registerVerifierAndStake(verifier: anchor.web3.Keypair) {
  await airdrop(verifier.publicKey);

  const verifierWorker = workerPda(verifier.publicKey);

  await program.methods
    .registerWorker()
    .accounts({
      worker: verifier.publicKey,
      workerAccount: verifierWorker,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier])
    .rpc();

  const token = await createAssociatedTokenAccount(
    provider.connection,
    payer,
    sharedMint,
    verifier.publicKey
  );

  await mintTo(
    provider.connection,
    payer,
    sharedMint,
    token,
    client,
    10_000_000
  );

  const stakeAuth = stakeAuthPda(verifierWorker);
  const stakeVault = stakeVaultPda(verifier.publicKey);

  await program.methods
    .stakeWorker(new BN(1_000_000))
    .accounts({
      worker: verifier.publicKey,
      workerAccount: verifierWorker,
      mint: sharedMint,
      workerToken: token,
      stakeAuth,
      stakeVault,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([verifier])
    .rpc();

  return {
    verifierWorker,
    verifierToken: token,
    stakeAuth,
    stakeVault,
  };
}

async function claimVerifierReward(
  verifier: anchor.web3.Keypair,
  job: PublicKey,
  fragment: PublicKey,
  verifierTokenPk: PublicKey,
  round: number
) {
  const vote = votePda(fragment, verifier.publicKey, round);
  const roundResolution = resolutionPda(fragment, round);
  const verifierWorker = workerPda(verifier.publicKey);
  const escrowAuth = escrowAuthPda(job);
  const jobAccount = await program.account.job.fetch(job);

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
      escrow: jobAccount.escrow,
      verifierToken: verifierTokenPk,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier])
    .rpc();
}

describe("silicium", () => {
  it("registers a worker", async () => {
    const workerAccount = workerPda(client);

    await program.methods
      .registerWorker()
      .accounts({
        worker: client,
        workerAccount,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const account = await program.account.worker.fetch(workerAccount);
    assert.equal(account.owner.toBase58(), client.toBase58());
  });

  it("stakes SPL tokens for a worker", async () => {
    const workerAccount = workerPda(client);

    sharedMint = await createMint(
      provider.connection,
      payer,
      client,
      null,
      6
    );

    sharedWorkerToken = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      sharedMint,
      client
    );

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      1_000_000_000
    );

    const stakeAuth = stakeAuthPda(workerAccount);
    const stakeVault = stakeVaultPda(client);

    const amount = new BN(1_000_000);

    await program.methods
      .stakeWorker(amount)
      .accounts({
        worker: client,
        workerAccount,
        mint: sharedMint,
        workerToken: sharedWorkerToken,
        stakeAuth,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .rpc();

    const account = await program.account.worker.fetch(workerAccount);

    assert.equal(account.stakeAmount.toString(), amount.toString());
    assert.equal(account.stakeMint.toBase58(), sharedMint.toBase58());
    assert.equal(account.stakeVault.toBase58(), stakeVault.toBase58());
  });

  it("creates a job and funds escrow with verifier budget", async () => {
    const jobId = new BN(1);
    const expectedFragments = 3;
    const deadlineUnix = new BN(Math.floor(Date.now() / 1000) + 3600);
    const budget = verifierBudget(expectedFragments);

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      10_000_000
    );

    const job = jobPda(client, jobId);
    const escrowAuth = escrowAuthPda(job);
    const escrow = anchor.web3.Keypair.generate();
    sharedEscrow = escrow.publicKey;

    await program.methods
      .createJob(
        jobId,
        expectedFragments,
        REWARD_PER_FRAGMENT,
        VERIFIER_REWARD_PER_VOTE,
        budget,
        deadlineUnix,
        QUORUM
      )
      .accounts({
        client,
        mint: sharedMint,
        job,
        escrowAuth,
        escrow: escrow.publicKey,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const jobAccount = await program.account.job.fetch(job);

    const expectedDeposit =
      expectedFragments * REWARD_PER_FRAGMENT.toNumber() + budget.toNumber();

    assert.equal(jobAccount.jobId.toString(), jobId.toString());
    assert.equal(jobAccount.client.toBase58(), client.toBase58());
    assert.equal(jobAccount.mint.toBase58(), sharedMint.toBase58());
    assert.equal(jobAccount.escrow.toBase58(), escrow.publicKey.toBase58());
    assert.equal(jobAccount.expectedFragments, expectedFragments);
    assert.equal(jobAccount.verifiedFragments, 0);
    assert.equal(jobAccount.rewardPerFragment.toString(), REWARD_PER_FRAGMENT.toString());
    assert.equal(
      jobAccount.verifierRewardPerVote.toString(),
      VERIFIER_REWARD_PER_VOTE.toString()
    );
    assert.equal(jobAccount.verifierRewardBudget.toString(), budget.toString());
    assert.equal(jobAccount.depositedAmount.toString(), expectedDeposit.toString());
    assert.equal(jobAccount.paidAmount.toString(), "0");
    assert.equal(jobAccount.claimableVerifierRewardsTotal.toString(), "0");
    assert.equal(jobAccount.claimedVerifierRewardsTotal.toString(), "0");
    assert.equal(jobAccount.fragmentQuorum, QUORUM);
    assert.isAbove(Number(jobAccount.createdAtUnix.toString()), 0);
    assert.deepEqual(jobAccount.status, { open: {} });
  });

  it("submits a fragment result", async () => {
    const jobId = new BN(1);
    const workerAccount = workerPda(client);
    const job = jobPda(client, jobId);
    const fragmentIndex = 0;
    const fragment = fragmentPda(job, fragmentIndex);

    await program.methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: client,
        workerAccount,
        job,
        fragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const fragmentAccount = await program.account.fragment.fetch(fragment);
    const workerAccountData = await program.account.worker.fetch(workerAccount);

    assert.equal(fragmentAccount.job.toBase58(), job.toBase58());
    assert.equal(fragmentAccount.fragmentIndex, fragmentIndex);
    assert.equal(fragmentAccount.worker.toBase58(), client.toBase58());
    assert.deepEqual(fragmentAccount.status, { submitted: {} });
    assert.equal(workerAccountData.totalSubmitted, 1);
  });

  it("registers and stakes a verifier", async () => {
    verifierKeypair = anchor.web3.Keypair.generate();
    const setup = await registerVerifierAndStake(verifierKeypair);
    verifierToken = setup.verifierToken;

    const verifierAccount = await program.account.worker.fetch(setup.verifierWorker);
    assert.equal(verifierAccount.stakeAmount.toString(), "1000000");
  });

  it("records a first yes vote without resolving the fragment", async () => {
    const jobId = new BN(1);
    const fragmentIndex = 0;

    const job = jobPda(client, jobId);
    const fragment = fragmentPda(job, fragmentIndex);
    const verifierWorker = workerPda(verifierKeypair.publicKey);

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const round = fragmentBefore.round;

    const vote = votePda(fragment, verifierKeypair.publicKey, round);
    const roundResolution = resolutionPda(fragment, round);
    const escrowAuth = escrowAuthPda(job);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: verifierKeypair.publicKey,
        job,
        fragment,
        verifierWorker,
        vote,
        roundResolution,
        escrowAuth,
        escrow: sharedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([verifierKeypair])
      .rpc();

    const fragmentAfter = await program.account.fragment.fetch(fragment);
    const jobAfter = await program.account.job.fetch(job);
    const verifierAccount = await program.account.worker.fetch(verifierWorker);
    const voteAccount = await program.account.fragmentVote.fetch(vote);
    const resolutionAccount = await program.account.fragmentResolution.fetch(roundResolution);

    assert.equal(voteAccount.choice, true);
    assert.equal(voteAccount.rewardClaimed, false);
    assert.equal(fragmentAfter.yesVotes, 1);
    assert.deepEqual(fragmentAfter.status, { submitted: {} });
    assert.equal(jobAfter.verifiedFragments, 0);
    assert.equal(jobAfter.claimableVerifierRewardsTotal.toString(), "0");
    assert.equal(verifierAccount.totalVerified, 0);
    assert.equal(resolutionAccount.resolved, false);
  });

  it("reaches quorum, pays worker, and reserves verifier rewards", async () => {
    const jobId = new BN(1);
    const fragmentIndex = 0;

    const verifier2 = anchor.web3.Keypair.generate();
    const {
      verifierWorker: verifierWorker2,
      verifierToken: verifierToken2,
    } = await registerVerifierAndStake(verifier2);

    const job = jobPda(client, jobId);
    const fragment = fragmentPda(job, fragmentIndex);

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const round = fragmentBefore.round;

    const vote2 = votePda(fragment, verifier2.publicKey, round);
    const roundResolution = resolutionPda(fragment, round);
    const escrowAuth = escrowAuthPda(job);

    const workerTokenBefore = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: verifier2.publicKey,
        job,
        fragment,
        verifierWorker: verifierWorker2,
        vote: vote2,
        roundResolution,
        escrowAuth,
        escrow: sharedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([verifier2])
      .rpc();

    const fragmentAfter = await program.account.fragment.fetch(fragment);
    const resolutionAfter = await program.account.fragmentResolution.fetch(roundResolution);
    const jobAfter = await program.account.job.fetch(job);
    const workerTokenAfter = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

    assert.deepEqual(fragmentAfter.status, { verified: {} });
    assert.equal(jobAfter.verifiedFragments, 1);
    assert.equal(
      jobAfter.claimableVerifierRewardsTotal.toString(),
      (QUORUM * VERIFIER_REWARD_PER_VOTE.toNumber()).toString()
    );
    assert.equal(resolutionAfter.resolved, true);
    assert.equal(resolutionAfter.winningChoice, true);
    assert.equal(resolutionAfter.eligibleRewards, QUORUM);
    assert.equal(resolutionAfter.claimedRewards, 0);

    const before = Number(workerTokenBefore.value.amount);
    const after = Number(workerTokenAfter.value.amount);
    assert.equal(after - before, REWARD_PER_FRAGMENT.toNumber());

    // stash for next claim test
    (globalThis as any).__verifier2 = verifier2;
    (globalThis as any).__verifier2Token = verifierToken2;
    (globalThis as any).__round0 = round;
  });

  it("claims verifier rewards for the winning yes votes", async () => {
    const job = jobPda(client, new BN(1));
    const fragment = fragmentPda(job, 0);
    const round = (globalThis as any).__round0 as number;
    const verifier2 = (globalThis as any).__verifier2 as anchor.web3.Keypair;
    const verifier2Token = (globalThis as any).__verifier2Token as PublicKey;

    const before1 = await provider.connection.getTokenAccountBalance(verifierToken);
    const before2 = await provider.connection.getTokenAccountBalance(verifier2Token);

    await claimVerifierReward(verifierKeypair, job, fragment, verifierToken, round);
    await claimVerifierReward(verifier2, job, fragment, verifier2Token, round);

    const after1 = await provider.connection.getTokenAccountBalance(verifierToken);
    const after2 = await provider.connection.getTokenAccountBalance(verifier2Token);

    assert.equal(
      Number(after1.value.amount) - Number(before1.value.amount),
      VERIFIER_REWARD_PER_VOTE.toNumber()
    );

    assert.equal(
      Number(after2.value.amount) - Number(before2.value.amount),
      VERIFIER_REWARD_PER_VOTE.toNumber()
    );

    const vote1 = votePda(fragment, verifierKeypair.publicKey, round);
    const vote2 = votePda(fragment, verifier2.publicKey, round);
    const resolution = resolutionPda(fragment, round);
    const jobAccount = await program.account.job.fetch(job);

    const vote1Account = await program.account.fragmentVote.fetch(vote1);
    const vote2Account = await program.account.fragmentVote.fetch(vote2);
    const resolutionAccount = await program.account.fragmentResolution.fetch(resolution);

    assert.equal(vote1Account.rewardClaimed, true);
    assert.equal(vote2Account.rewardClaimed, true);
    assert.equal(resolutionAccount.claimedRewards, QUORUM);
    assert.equal(
      jobAccount.claimedVerifierRewardsTotal.toString(),
      (QUORUM * VERIFIER_REWARD_PER_VOTE.toNumber()).toString()
    );
  });

  it("creates a rejected fragment", async () => {
    const expectedFragments = 2;
    const deadlineUnix = new BN(Math.floor(Date.now() / 1000) + 3600);
    const budget = verifierBudget(expectedFragments);

    rejectedJob = jobPda(client, rejectedJobId);
    const escrowAuth = escrowAuthPda(rejectedJob);
    const escrow = anchor.web3.Keypair.generate();
    rejectedEscrow = escrow.publicKey;

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      2_000_000 + budget.toNumber()
    );

    await program.methods
      .createJob(
        rejectedJobId,
        expectedFragments,
        REWARD_PER_FRAGMENT,
        VERIFIER_REWARD_PER_VOTE,
        budget,
        deadlineUnix,
        QUORUM
      )
      .accounts({
        client,
        mint: sharedMint,
        job: rejectedJob,
        escrowAuth,
        escrow: rejectedEscrow,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    rejectedFragment = fragmentPda(rejectedJob, 0);

    await program.methods
      .submitFragmentResult(0, Array(32).fill(7), Array(32).fill(8))
      .accounts({
        worker: client,
        workerAccount: workerPda(client),
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const rejectVerifier1 = anchor.web3.Keypair.generate();
    const rejectVerifier2 = anchor.web3.Keypair.generate();

    const {
      verifierWorker: rejectVerifierWorker1,
      verifierToken: rejectVerifierToken1,
    } = await registerVerifierAndStake(rejectVerifier1);

    const {
      verifierWorker: rejectVerifierWorker2,
      verifierToken: rejectVerifierToken2,
    } = await registerVerifierAndStake(rejectVerifier2);

    const fragmentBefore = await program.account.fragment.fetch(rejectedFragment);
    const round = fragmentBefore.round;

    const vote1 = votePda(rejectedFragment, rejectVerifier1.publicKey, round);
    const vote2 = votePda(rejectedFragment, rejectVerifier2.publicKey, round);
    const roundResolution = resolutionPda(rejectedFragment, round);

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: rejectVerifier1.publicKey,
        job: rejectedJob,
        fragment: rejectedFragment,
        verifierWorker: rejectVerifierWorker1,
        vote: vote1,
        roundResolution,
        escrowAuth,
        escrow: rejectedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([rejectVerifier1])
      .rpc();

    const midFragment = await program.account.fragment.fetch(rejectedFragment);
    assert.deepEqual(midFragment.status, { submitted: {} });

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: rejectVerifier2.publicKey,
        job: rejectedJob,
        fragment: rejectedFragment,
        verifierWorker: rejectVerifierWorker2,
        vote: vote2,
        roundResolution,
        escrowAuth,
        escrow: rejectedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([rejectVerifier2])
      .rpc();

    const fragmentAfter = await program.account.fragment.fetch(rejectedFragment);
    const resolutionAfter = await program.account.fragmentResolution.fetch(roundResolution);
    const jobAfter = await program.account.job.fetch(rejectedJob);

    assert.deepEqual(fragmentAfter.status, { rejected: {} });
    assert.equal(resolutionAfter.resolved, true);
    assert.equal(resolutionAfter.winningChoice, false);
    assert.equal(resolutionAfter.eligibleRewards, QUORUM);
    assert.equal(
      jobAfter.claimableVerifierRewardsTotal.toString(),
      (QUORUM * VERIFIER_REWARD_PER_VOTE.toNumber()).toString()
    );

    const before1 = await provider.connection.getTokenAccountBalance(rejectVerifierToken1);
    const before2 = await provider.connection.getTokenAccountBalance(rejectVerifierToken2);

    await claimVerifierReward(
      rejectVerifier1,
      rejectedJob,
      rejectedFragment,
      rejectVerifierToken1,
      round
    );

    await claimVerifierReward(
      rejectVerifier2,
      rejectedJob,
      rejectedFragment,
      rejectVerifierToken2,
      round
    );

    const after1 = await provider.connection.getTokenAccountBalance(rejectVerifierToken1);
    const after2 = await provider.connection.getTokenAccountBalance(rejectVerifierToken2);

    assert.equal(
      Number(after1.value.amount) - Number(before1.value.amount),
      VERIFIER_REWARD_PER_VOTE.toNumber()
    );
    assert.equal(
      Number(after2.value.amount) - Number(before2.value.amount),
      VERIFIER_REWARD_PER_VOTE.toNumber()
    );
  });

  it("resubmits a rejected fragment", async () => {
    const before = await program.account.fragment.fetch(rejectedFragment);

    await program.methods
      .resubmitFragmentResult(0, Array(32).fill(9), Array(32).fill(10))
      .accounts({
        worker: client,
        workerAccount: workerPda(client),
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const after = await program.account.fragment.fetch(rejectedFragment);
    const workerAfter = await program.account.worker.fetch(workerPda(client));

    assert.equal(after.round, before.round + 1);
    assert.equal(after.yesVotes, 0);
    assert.equal(after.noVotes, 0);
    assert.deepEqual(after.status, { submitted: {} });
    assert.deepEqual(after.resultHash, Array(32).fill(9));
    assert.deepEqual(after.proofRef, Array(32).fill(10));
    assert.equal(workerAfter.totalSubmitted, 3);
  });

  it("creates, verifies, claims, and finalizes a job", async () => {
    const expectedFragments = 2;
    const deadlineUnix = new BN(Math.floor(Date.now() / 1000) + 3600);
    const budget = verifierBudget(expectedFragments);

    finalizeJob = jobPda(client, finalizeJobId);
    const escrowAuth = escrowAuthPda(finalizeJob);
    const escrow = anchor.web3.Keypair.generate();
    finalizeEscrow = escrow.publicKey;

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      2_000_000 + budget.toNumber()
    );

    await program.methods
      .createJob(
        finalizeJobId,
        expectedFragments,
        REWARD_PER_FRAGMENT,
        VERIFIER_REWARD_PER_VOTE,
        budget,
        deadlineUnix,
        QUORUM
      )
      .accounts({
        client,
        mint: sharedMint,
        job: finalizeJob,
        escrowAuth,
        escrow: finalizeEscrow,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const workerAccount = workerPda(client);

    const submitAndVerifyFragment = async (fragmentIndex: number) => {
      const fragment = fragmentPda(finalizeJob, fragmentIndex);

      await program.methods
        .submitFragmentResult(
          fragmentIndex,
          Array(32).fill(11 + fragmentIndex),
          Array(32).fill(12 + fragmentIndex)
        )
        .accounts({
          worker: client,
          workerAccount,
          job: finalizeJob,
          fragment,
          workerToken: sharedWorkerToken,
          systemProgram: SystemProgram.programId,
        })
        .rpc();

      const verifierA = anchor.web3.Keypair.generate();
      const verifierB = anchor.web3.Keypair.generate();

      const {
        verifierWorker: verifierWorkerA,
        verifierToken: verifierTokenA,
      } = await registerVerifierAndStake(verifierA);

      const {
        verifierWorker: verifierWorkerB,
        verifierToken: verifierTokenB,
      } = await registerVerifierAndStake(verifierB);

      const fragmentBefore = await program.account.fragment.fetch(fragment);
      const round = fragmentBefore.round;
      const roundResolution = resolutionPda(fragment, round);

      const voteA = votePda(fragment, verifierA.publicKey, round);
      const voteB = votePda(fragment, verifierB.publicKey, round);

      await program.methods
        .voteFragment(true)
        .accounts({
          verifier: verifierA.publicKey,
          job: finalizeJob,
          fragment,
          verifierWorker: verifierWorkerA,
          vote: voteA,
          roundResolution,
          escrowAuth,
          escrow: finalizeEscrow,
          workerToken: sharedWorkerToken,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
        })
        .signers([verifierA])
        .rpc();

      await program.methods
        .voteFragment(true)
        .accounts({
          verifier: verifierB.publicKey,
          job: finalizeJob,
          fragment,
          verifierWorker: verifierWorkerB,
          vote: voteB,
          roundResolution,
          escrowAuth,
          escrow: finalizeEscrow,
          workerToken: sharedWorkerToken,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
        })
        .signers([verifierB])
        .rpc();

      await claimVerifierReward(verifierA, finalizeJob, fragment, verifierTokenA, round);
      await claimVerifierReward(verifierB, finalizeJob, fragment, verifierTokenB, round);

      const fragmentAfter = await program.account.fragment.fetch(fragment);
      assert.deepEqual(fragmentAfter.status, { verified: {} });
    };

    await submitAndVerifyFragment(0);
    await submitAndVerifyFragment(1);

    const jobAfterVotes = await program.account.job.fetch(finalizeJob);
    assert.equal(jobAfterVotes.verifiedFragments, 2);
    assert.equal(
      jobAfterVotes.claimedVerifierRewardsTotal.toString(),
      (2 * QUORUM * VERIFIER_REWARD_PER_VOTE.toNumber()).toString()
    );

    const result = resultPda(finalizeJob);
    const finalHash = Array(32).fill(42);
    const outputUri = Buffer.from("ipfs://silicium-result-3");

    await program.methods
      .finalizeJob(finalHash, outputUri)
      .accounts({
        client,
        job: finalizeJob,
        result,
        escrowAuth,
        escrow: finalizeEscrow,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const jobAccount = await program.account.job.fetch(finalizeJob);
    const resultAccount = await program.account.jobResult.fetch(result);

    assert.deepEqual(jobAccount.status, { finalized: {} });
    assert.deepEqual(resultAccount.finalHash, finalHash);
    assert.equal(resultAccount.uriLen, outputUri.length);

    const uri = Buffer.from(resultAccount.uriBytes)
      .slice(0, resultAccount.uriLen)
      .toString();

    assert.equal(uri, "ipfs://silicium-result-3");
  });

  it("slashes a wrong vote", async () => {
    const fragmentIndex = 0;

    const [treasuryState] = PublicKey.findProgramAddressSync(
      [Buffer.from("treasury"), sharedMint.toBuffer()],
      program.programId
    );

    const [treasuryAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("treasury_auth"), sharedMint.toBuffer()],
      program.programId
    );

    const treasury = anchor.web3.Keypair.generate();

    await program.methods
      .initTreasury()
      .accounts({
        payer: client,
        mint: sharedMint,
        treasuryState,
        treasuryAuth,
        treasury: treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([treasury])
      .rpc();

    const budget = verifierBudget(2);
    const job = jobPda(client, slashJobId);
    const escrowAuth = escrowAuthPda(job);
    const escrow = anchor.web3.Keypair.generate();

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      2_000_000 + budget.toNumber()
    );

    await program.methods
      .createJob(
        slashJobId,
        2,
        REWARD_PER_FRAGMENT,
        VERIFIER_REWARD_PER_VOTE,
        budget,
        new BN(Math.floor(Date.now() / 1000) + 3600),
        QUORUM
      )
      .accounts({
        client,
        mint: sharedMint,
        job,
        escrowAuth,
        escrow: escrow.publicKey,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const fragment = fragmentPda(job, fragmentIndex);
    const workerAccount = workerPda(client);

    await program.methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: client,
        workerAccount,
        job,
        fragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const badVerifier = anchor.web3.Keypair.generate();
    const goodVerifier1 = anchor.web3.Keypair.generate();
    const goodVerifier2 = anchor.web3.Keypair.generate();

    const {
      verifierWorker: badVerifierWorker,
      verifierToken: badVerifierToken,
      stakeAuth,
      stakeVault,
    } = await registerVerifierAndStake(badVerifier);

    const {
      verifierWorker: goodVerifierWorker1,
      verifierToken: goodVerifierToken1,
    } = await registerVerifierAndStake(goodVerifier1);

    const {
      verifierWorker: goodVerifierWorker2,
      verifierToken: goodVerifierToken2,
    } = await registerVerifierAndStake(goodVerifier2);

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const round = fragmentBefore.round;
    const roundResolution = resolutionPda(fragment, round);

    const badVote = votePda(fragment, badVerifier.publicKey, round);
    const goodVote1 = votePda(fragment, goodVerifier1.publicKey, round);
    const goodVote2 = votePda(fragment, goodVerifier2.publicKey, round);

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: badVerifier.publicKey,
        job,
        fragment,
        verifierWorker: badVerifierWorker,
        vote: badVote,
        roundResolution,
        escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([badVerifier])
      .rpc();

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: goodVerifier1.publicKey,
        job,
        fragment,
        verifierWorker: goodVerifierWorker1,
        vote: goodVote1,
        roundResolution,
        escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier1])
      .rpc();

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: goodVerifier2.publicKey,
        job,
        fragment,
        verifierWorker: goodVerifierWorker2,
        vote: goodVote2,
        roundResolution,
        escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier2])
      .rpc();

    const beforeGood1 = await provider.connection.getTokenAccountBalance(goodVerifierToken1);
    const beforeGood2 = await provider.connection.getTokenAccountBalance(goodVerifierToken2);

    await claimVerifierReward(goodVerifier1, job, fragment, goodVerifierToken1, round);
    await claimVerifierReward(goodVerifier2, job, fragment, goodVerifierToken2, round);

    const afterGood1 = await provider.connection.getTokenAccountBalance(goodVerifierToken1);
    const afterGood2 = await provider.connection.getTokenAccountBalance(goodVerifierToken2);

    assert.equal(
      Number(afterGood1.value.amount) - Number(beforeGood1.value.amount),
      VERIFIER_REWARD_PER_VOTE.toNumber()
    );
    assert.equal(
      Number(afterGood2.value.amount) - Number(beforeGood2.value.amount),
      VERIFIER_REWARD_PER_VOTE.toNumber()
    );

    const stakeBefore = await provider.connection.getTokenAccountBalance(stakeVault);
    const treasuryBefore = await provider.connection.getTokenAccountBalance(treasury.publicKey);

    await program.methods
      .slashVote()
      .accounts({
        slasher: client,
        job,
        fragment,
        vote: badVote,
        verifierWorker: badVerifierWorker,
        treasuryState,
        stakeAuth,
        stakeVault,
        treasuryAuth,
        treasury: treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();

    const voteAfter = await program.account.fragmentVote.fetch(badVote);
    const workerAfter = await program.account.worker.fetch(badVerifierWorker);
    const stakeAfter = await provider.connection.getTokenAccountBalance(stakeVault);
    const treasuryAfter = await provider.connection.getTokenAccountBalance(treasury.publicKey);

    assert.equal(voteAfter.slashed, true);
    assert.equal(voteAfter.rewardClaimed, false);
    assert.equal(workerAfter.stakeAmount.toString(), "900000");

    assert.equal(
      Number(stakeBefore.value.amount) - Number(stakeAfter.value.amount),
      100000
    );

    assert.equal(
      Number(treasuryAfter.value.amount) - Number(treasuryBefore.value.amount),
      100000
    );

    const badBefore = await provider.connection.getTokenAccountBalance(badVerifierToken);
    try {
      await claimVerifierReward(badVerifier, job, fragment, badVerifierToken, round);
      assert.fail("bad verifier should not be able to claim");
    } catch (_) {
      // expected
    }
    const badAfter = await provider.connection.getTokenAccountBalance(badVerifierToken);
    assert.equal(badAfter.value.amount, badBefore.value.amount);
  });
});