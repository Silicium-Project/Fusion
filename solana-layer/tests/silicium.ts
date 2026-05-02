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
const VERIFIER_REWARD_BUDGET = new anchor.BN(1_000_000);

let sharedWorkerToken: PublicKey;
let sharedMint: PublicKey;
let verifierKeypair: anchor.web3.Keypair;
let sharedEscrow: PublicKey;

let rejectedJobId = new anchor.BN(2);
let rejectedJob: PublicKey;
let rejectedFragment: PublicKey;
let rejectedEscrow: PublicKey;

let finalizeJobId = new anchor.BN(3);
let finalizeJob: PublicKey;
let finalizeEscrow: PublicKey;

let reclaimJobId = new anchor.BN(4);
let reclaimJob: PublicKey;
let reclaimFragment: PublicKey;
let reclaimEscrow: PublicKey;

let slashJobId = new anchor.BN(5);
let stakingPool: PublicKey;
let stakingPoolAuth: PublicKey;
let stakingStakeVault: PublicKey;
let stakingRewardVault: PublicKey;

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
    [
      Buffer.from("fragment_vote"),
      fragment.toBuffer(),
      verifier.toBuffer(),
      u16le(round),
    ],
    program.programId
  )[0];
}

function roundResolutionPda(fragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [
      Buffer.from("fragment_resolution"),
      fragment.toBuffer(),
      u16le(round),
    ],
    program.programId
  )[0];
}

function reputationToNumber(value: any): number {
  return Number(value.toString());
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
      workerAccount: workerAccount,
      systemProgram: SystemProgram.programId,
    })
    .signers([workerKeypair])
    .rpc();

  return workerAccount;
}

async function createAndFundWorkerToken(
  owner: PublicKey,
  amount = 10_000_000
): Promise<PublicKey> {
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const authority = provider.wallet.publicKey;

  const token = await createAssociatedTokenAccount(
    provider.connection,
    payer,
    sharedMint,
    owner
  );

  await mintTo(
    provider.connection,
    payer,
    sharedMint,
    token,
    authority,
    amount
  );

  return token;
}

async function stakeRegisteredWorker(
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
      workerAccount: workerAccount,
      mint: sharedMint,
      workerToken: workerToken,
      stakeAuth: stakeAuth,
      stakeVault: stakeVault,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([workerKeypair])
    .rpc();

  return { stakeAuth, stakeVault };
}

function stakingPoolPda(mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("staking_pool"), mint.toBuffer()],
    program.programId
  )[0];
}

function stakingPoolAuthPda(mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("staking_pool_auth"), mint.toBuffer()],
    program.programId
  )[0];
}

function networkStakerPda(owner: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [
      Buffer.from("network_staker"),
      owner.toBuffer(),
      mint.toBuffer(),
    ],
    program.programId
  )[0];
}

async function createTestJob(
  jobId: anchor.BN,
  expectedFragments = 1,
  fragmentQuorum = 2,
  rewardPerFragment = new anchor.BN(1_000_000),
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
    sharedMint,
    sharedWorkerToken,
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
      client: client,
      mint: sharedMint,
      job: job,
      escrowAuth: escrowAuth,
      escrow: escrow.publicKey,
      clientToken: sharedWorkerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([escrow])
    .rpc();

  return {
    job,
    escrow: escrow.publicKey,
    escrowAuth,
  };
}

async function expectTxToFail(
  fn: () => Promise<any>,
  expectedMessage: string
) {
  try {
    await fn();
    assert.fail(`Expected transaction to fail with ${expectedMessage}`);
  } catch (e: any) {
    const msg = String(e);
    assert.include(
      msg,
      expectedMessage,
      `Expected error to include "${expectedMessage}", got: ${msg}`
    );
  }
}

async function createReadyWorker(amount = 1_000_000) {
  const worker = anchor.web3.Keypair.generate();

  await airdrop(worker.publicKey);

  const workerAccount = await registerWorker(worker);
  const workerToken = await createAndFundWorkerToken(worker.publicKey);

  const stake = await stakeRegisteredWorker(
    worker,
    workerAccount,
    workerToken,
    amount
  );

  return {
    keypair: worker,
    workerAccount,
    workerToken,
    stakeAuth: stake.stakeAuth,
    stakeVault: stake.stakeVault,
  };
}

async function claimAndSubmitFragment(
  worker: anchor.web3.Keypair,
  workerAccount: PublicKey,
  workerToken: PublicKey,
  job: PublicKey,
  fragmentIndex: number,
  resultByte = 1,
  proofByte = 2
) {
  const fragment = fragmentPda(job, fragmentIndex);

  await program.methods
    .claimFragment(fragmentIndex)
    .accounts({
      worker: worker.publicKey,
      workerAccount: workerAccount,
      job: job,
      fragment: fragment,
      workerToken: workerToken,
      systemProgram: SystemProgram.programId,
    })
    .signers([worker])
    .rpc();

  await program.methods
    .submitFragmentResult(
      fragmentIndex,
      Array(32).fill(resultByte),
      Array(32).fill(proofByte)
    )
    .accounts({
      worker: worker.publicKey,
      workerAccount: workerAccount,
      job: job,
      fragment: fragment,
      workerToken: workerToken,
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

  const vote = votePda(
    fragment,
    verifier.publicKey,
    fragmentBefore.round
  );

  const roundResolution = roundResolutionPda(
    fragment,
    fragmentBefore.round
  );

  const computeWorker = workerPda(fragmentBefore.worker);
  const escrowAuth = escrowAuthPda(job);

  await program.methods
    .voteFragment(choice)
    .accounts({
      verifier: verifier.publicKey,
      job: job,
      fragment: fragment,
      verifierWorker: verifierWorker,
      computeWorker: computeWorker,
      vote: vote,
      roundResolution: roundResolution,
      escrowAuth: escrowAuth,
      escrow: escrow,
      workerToken: workerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier])
    .rpc();

  return {
    vote,
    roundResolution,
  };
}

describe("silicium", () => {
  it("registers a worker", async () => {
    const worker = provider.wallet.publicKey;
    const workerAccount = workerPda(worker);

    await program.methods
      .registerWorker()
      .accounts({
        worker: worker,
        workerAccount: workerAccount,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const account = await program.account.worker.fetch(workerAccount);
    assert.equal(account.owner.toBase58(), worker.toBase58());
  });

  it("stakes SPL tokens for a worker", async () => {
    const worker = provider.wallet.publicKey;
    const workerAccount = workerPda(worker);

    const mint = await createMint(
      provider.connection,
      provider.wallet.payer,
      worker,
      null,
      6
    );
    sharedMint = mint;

    const workerToken = await createAssociatedTokenAccount(
      provider.connection,
      provider.wallet.payer,
      mint,
      worker
    );
    sharedWorkerToken = workerToken;

    await mintTo(
      provider.connection,
      provider.wallet.payer,
      mint,
      workerToken,
      worker,
      1_000_000_000
    );

    const stakeAuth = stakeAuthPda(workerAccount);
    const stakeVault = stakeVaultPda(worker);
    const amount = new anchor.BN(1_000_000);

    await program.methods
      .stakeWorker(amount)
      .accounts({
        worker: worker,
        workerAccount: workerAccount,
        mint: mint,
        workerToken: workerToken,
        stakeAuth: stakeAuth,
        stakeVault: stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .rpc();

    const account = await program.account.worker.fetch(workerAccount);

    assert.equal(account.stakeAmount.toString(), amount.toString());
    assert.equal(account.stakeMint.toBase58(), mint.toBase58());
    assert.equal(account.stakeVault.toBase58(), stakeVault.toBase58());
  });

  it("creates a job and funds escrow", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const jobId = new anchor.BN(1);
    const expectedFragments = 3;
    const rewardPerFragment = new anchor.BN(1_000_000);
    const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
    const fragmentQuorum = 2;

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
        rewardPerFragment,
        VERIFIER_REWARD_PER_VOTE,
        VERIFIER_REWARD_BUDGET,
        deadlineUnix,
        fragmentQuorum
      )
      .accounts({
        client: client,
        mint: sharedMint,
        job: job,
        escrowAuth: escrowAuth,
        escrow: escrow.publicKey,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const jobAccount = await program.account.job.fetch(job);

    assert.equal(jobAccount.jobId.toString(), jobId.toString());
    assert.equal(jobAccount.client.toBase58(), client.toBase58());
    assert.equal(jobAccount.mint.toBase58(), sharedMint.toBase58());
    assert.equal(jobAccount.escrow.toBase58(), escrow.publicKey.toBase58());
    assert.equal(jobAccount.expectedFragments, expectedFragments);
    assert.equal(jobAccount.verifiedFragments, 0);
    assert.equal(jobAccount.rewardPerFragment.toString(), rewardPerFragment.toString());
    assert.equal(
      jobAccount.depositedAmount.toString(),
      rewardPerFragment.mul(new anchor.BN(expectedFragments)).add(VERIFIER_REWARD_BUDGET).toString()
    );
    assert.equal(jobAccount.paidAmount.toString(), "0");
    assert.equal(jobAccount.fragmentQuorum, fragmentQuorum);
    assert.deepEqual(jobAccount.status, { open: {} });
  });

  it("claims a fragment", async () => {
    const worker = provider.wallet.publicKey;
    const workerAccount = workerPda(worker);
    const job = jobPda(worker, new anchor.BN(1));
    const fragmentIndex = 0;
    const fragment = fragmentPda(job, fragmentIndex);

    await program.methods
      .claimFragment(fragmentIndex)
      .accounts({
        worker: worker,
        workerAccount: workerAccount,
        job: job,
        fragment: fragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const fragmentAccount = await program.account.fragment.fetch(fragment);

    assert.equal(fragmentAccount.job.toBase58(), job.toBase58());
    assert.equal(fragmentAccount.fragmentIndex, fragmentIndex);
    assert.equal(fragmentAccount.assignedWorker.toBase58(), worker.toBase58());
    assert.deepEqual(fragmentAccount.status, { claimed: {} });

    assert.isAbove(
      Number(fragmentAccount.claimDeadlineUnix.toString()),
      0
    );
  });

  it("submits a claimed fragment result", async () => {
    const worker = provider.wallet.publicKey;
    const workerAccount = workerPda(worker);
    const job = jobPda(worker, new anchor.BN(1));
    const fragmentIndex = 0;
    const fragment = fragmentPda(job, fragmentIndex);

    const resultHash = Array(32).fill(1);
    const proofRef = Array(32).fill(2);

    await program.methods
      .submitFragmentResult(fragmentIndex, resultHash, proofRef)
      .accounts({
        worker: worker,
        workerAccount: workerAccount,
        job: job,
        fragment: fragment,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const fragmentAccount = await program.account.fragment.fetch(fragment);
    const workerAccountData = await program.account.worker.fetch(workerAccount);

    assert.equal(fragmentAccount.job.toBase58(), job.toBase58());
    assert.equal(fragmentAccount.fragmentIndex, fragmentIndex);
    assert.equal(fragmentAccount.worker.toBase58(), worker.toBase58());
    assert.deepEqual(fragmentAccount.status, { submitted: {} });
    assert.equal(workerAccountData.totalSubmitted, 1);
  });

  it("registers and stakes a verifier", async () => {
    verifierKeypair = anchor.web3.Keypair.generate();

    await airdrop(verifierKeypair.publicKey);

    const verifierWorker = await registerWorker(verifierKeypair);
    const verifierToken = await createAndFundWorkerToken(verifierKeypair.publicKey);
    await stakeRegisteredWorker(verifierKeypair, verifierWorker, verifierToken);

    const verifierAccount = await program.account.worker.fetch(verifierWorker);
    assert.equal(verifierAccount.stakeAmount.toString(), "1000000");
  });

  it("votes yes on a fragment and keeps it submitted before quorum", async () => {
    const client = provider.wallet.publicKey;
    const job = jobPda(client, new anchor.BN(1));
    const fragment = fragmentPda(job, 0);
    const verifierWorker = workerPda(verifierKeypair.publicKey);

    const fragmentAccountBefore = await program.account.fragment.fetch(fragment);
    const vote = votePda(fragment, verifierKeypair.publicKey, fragmentAccountBefore.round);
    const roundResolution = roundResolutionPda(fragment, fragmentAccountBefore.round);
    const computeWorker = workerPda(fragmentAccountBefore.worker);
    const escrowAuth = escrowAuthPda(job);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: verifierKeypair.publicKey,
        job: job,
        fragment: fragment,
        verifierWorker: verifierWorker,
        computeWorker: computeWorker,
        vote: vote,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: sharedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([verifierKeypair])
      .rpc();

    const fragmentAccount = await program.account.fragment.fetch(fragment);
    const jobAccount = await program.account.job.fetch(job);
    const verifierAccount = await program.account.worker.fetch(verifierWorker);
    const voteAccount = await program.account.fragmentVote.fetch(vote);

    assert.equal(voteAccount.choice, true);
    assert.equal(fragmentAccount.yesVotes, 1);
    assert.deepEqual(fragmentAccount.status, { submitted: {} });
    assert.equal(jobAccount.verifiedFragments, 0);
    assert.equal(verifierAccount.totalVerified, 0);
  });

  it("reaches quorum and pays worker", async () => {
    const client = provider.wallet.publicKey;
    const job = jobPda(client, new anchor.BN(1));
    const fragment = fragmentPda(job, 0);

    const verifier2 = anchor.web3.Keypair.generate();
    await airdrop(verifier2.publicKey);

    const verifierWorker2 = await registerWorker(verifier2);
    const verifierToken2 = await createAndFundWorkerToken(verifier2.publicKey);
    await stakeRegisteredWorker(verifier2, verifierWorker2, verifierToken2);

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const vote2 = votePda(fragment, verifier2.publicKey, fragmentBefore.round);
    const roundResolution = roundResolutionPda(fragment, fragmentBefore.round);
    const computeWorker = workerPda(fragmentBefore.worker);
    const escrowAuth = escrowAuthPda(job);

    const workerTokenBefore = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: verifier2.publicKey,
        job: job,
        fragment: fragment,
        verifierWorker: verifierWorker2,
        computeWorker: computeWorker,
        vote: vote2,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: sharedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([verifier2])
      .rpc();

    const fragmentAfter = await program.account.fragment.fetch(fragment);
    const jobAfter = await program.account.job.fetch(job);
    const workerTokenAfter = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

    assert.deepEqual(fragmentAfter.status, { verified: {} });
    assert.equal(jobAfter.verifiedFragments, 1);

    const before = Number(workerTokenBefore.value.amount);
    const after = Number(workerTokenAfter.value.amount);
    assert.equal(after - before, 1_000_000);
  });

  it("creates a rejected fragment", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const expectedFragments = 2;
    const rewardPerFragment = new anchor.BN(1_000_000);
    const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
    const fragmentQuorum = 2;

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
      3_000_000
    );

    await program.methods
      .createJob(
        rejectedJobId,
        expectedFragments,
        rewardPerFragment,
        VERIFIER_REWARD_PER_VOTE,
        VERIFIER_REWARD_BUDGET,
        deadlineUnix,
        fragmentQuorum
      )
      .accounts({
        client: client,
        mint: sharedMint,
        job: rejectedJob,
        escrowAuth: escrowAuth,
        escrow: rejectedEscrow,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const fragmentIndex = 0;
    rejectedFragment = fragmentPda(rejectedJob, fragmentIndex);
    const workerAccount = workerPda(client);

    await program.methods
      .claimFragment(fragmentIndex)
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    await program.methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(7), Array(32).fill(8))
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const rejectVerifier1 = anchor.web3.Keypair.generate();
    await airdrop(rejectVerifier1.publicKey);
    const rejectVerifierWorker1 = await registerWorker(rejectVerifier1);
    const rejectVerifierToken1 = await createAndFundWorkerToken(rejectVerifier1.publicKey);
    await stakeRegisteredWorker(rejectVerifier1, rejectVerifierWorker1, rejectVerifierToken1);

    const rejectVerifier2 = anchor.web3.Keypair.generate();
    await airdrop(rejectVerifier2.publicKey);
    const rejectVerifierWorker2 = await registerWorker(rejectVerifier2);
    const rejectVerifierToken2 = await createAndFundWorkerToken(rejectVerifier2.publicKey);
    await stakeRegisteredWorker(rejectVerifier2, rejectVerifierWorker2, rejectVerifierToken2);

    const fragmentBefore = await program.account.fragment.fetch(rejectedFragment);
    const vote1 = votePda(rejectedFragment, rejectVerifier1.publicKey, fragmentBefore.round);
    const vote2 = votePda(rejectedFragment, rejectVerifier2.publicKey, fragmentBefore.round);
    const roundResolution = roundResolutionPda(rejectedFragment, fragmentBefore.round);
    const computeWorker = workerPda(fragmentBefore.worker);

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: rejectVerifier1.publicKey,
        job: rejectedJob,
        fragment: rejectedFragment,
        verifierWorker: rejectVerifierWorker1,
        computeWorker: computeWorker,
        vote: vote1,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
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
        computeWorker: computeWorker,
        vote: vote2,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: rejectedEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([rejectVerifier2])
      .rpc();

    const fragmentAfter = await program.account.fragment.fetch(rejectedFragment);
    assert.deepEqual(fragmentAfter.status, { rejected: {} });
  });

  it("claims a rejected fragment again and submits again", async () => {
    const worker = provider.wallet.publicKey;
    const workerAccount = workerPda(worker);
    const fragmentIndex = 0;

    const before = await program.account.fragment.fetch(rejectedFragment);
    const oldRound = before.round;

    await program.methods
      .claimFragment(fragmentIndex)
      .accounts({
        worker: worker,
        workerAccount: workerAccount,
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const afterClaim = await program.account.fragment.fetch(rejectedFragment);
    assert.deepEqual(afterClaim.status, { claimed: {} });
    assert.equal(afterClaim.round, oldRound + 1);
    assert.equal(afterClaim.assignedWorker.toBase58(), worker.toBase58());

    await program.methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(9), Array(32).fill(10))
      .accounts({
        worker: worker,
        workerAccount: workerAccount,
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const afterSubmit = await program.account.fragment.fetch(rejectedFragment);
    const workerAfter = await program.account.worker.fetch(workerAccount);

    assert.deepEqual(afterSubmit.status, { submitted: {} });
    assert.deepEqual(afterSubmit.resultHash, Array(32).fill(9));
    assert.deepEqual(afterSubmit.proofRef, Array(32).fill(10));
    assert.equal(workerAfter.totalSubmitted, 3);
  });

  it("creates, verifies, and finalizes a job", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const expectedFragments = 2;
    const rewardPerFragment = new anchor.BN(1_000_000);
    const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
    const fragmentQuorum = 2;
    const workerAccount = workerPda(client);

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
      4_000_000
    );

    await program.methods
      .createJob(
        finalizeJobId,
        expectedFragments,
        rewardPerFragment,
        VERIFIER_REWARD_PER_VOTE,
        VERIFIER_REWARD_BUDGET,
        deadlineUnix,
        fragmentQuorum
      )
      .accounts({
        client: client,
        mint: sharedMint,
        job: finalizeJob,
        escrowAuth: escrowAuth,
        escrow: finalizeEscrow,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const fragment0 = fragmentPda(finalizeJob, 0);
    const fragment1 = fragmentPda(finalizeJob, 1);

    await program.methods
      .claimFragment(0)
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: finalizeJob,
        fragment: fragment0,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    await program.methods
      .submitFragmentResult(0, Array(32).fill(11), Array(32).fill(12))
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: finalizeJob,
        fragment: fragment0,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const finalizeVerifier1 = anchor.web3.Keypair.generate();
    await airdrop(finalizeVerifier1.publicKey);
    const verifierWorker1 = await registerWorker(finalizeVerifier1);
    const verifierToken1 = await createAndFundWorkerToken(finalizeVerifier1.publicKey);
    await stakeRegisteredWorker(finalizeVerifier1, verifierWorker1, verifierToken1);

    const finalizeVerifier2 = anchor.web3.Keypair.generate();
    await airdrop(finalizeVerifier2.publicKey);
    const verifierWorker2 = await registerWorker(finalizeVerifier2);
    const verifierToken2 = await createAndFundWorkerToken(finalizeVerifier2.publicKey);
    await stakeRegisteredWorker(finalizeVerifier2, verifierWorker2, verifierToken2);

    let fragmentBefore = await program.account.fragment.fetch(fragment0);
    let vote1 = votePda(fragment0, finalizeVerifier1.publicKey, fragmentBefore.round);
    let roundResolution = roundResolutionPda(fragment0, fragmentBefore.round);
    let computeWorker = workerPda(fragmentBefore.worker);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: finalizeVerifier1.publicKey,
        job: finalizeJob,
        fragment: fragment0,
        verifierWorker: verifierWorker1,
        computeWorker: computeWorker,
        vote: vote1,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: finalizeEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([finalizeVerifier1])
      .rpc();

    fragmentBefore = await program.account.fragment.fetch(fragment0);
    let vote2 = votePda(fragment0, finalizeVerifier2.publicKey, fragmentBefore.round);
    roundResolution = roundResolutionPda(fragment0, fragmentBefore.round);
    computeWorker = workerPda(fragmentBefore.worker);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: finalizeVerifier2.publicKey,
        job: finalizeJob,
        fragment: fragment0,
        verifierWorker: verifierWorker2,
        computeWorker: computeWorker,
        vote: vote2,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: finalizeEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([finalizeVerifier2])
      .rpc();

    await program.methods
      .claimFragment(1)
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: finalizeJob,
        fragment: fragment1,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    await program.methods
      .submitFragmentResult(1, Array(32).fill(21), Array(32).fill(22))
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: finalizeJob,
        fragment: fragment1,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    fragmentBefore = await program.account.fragment.fetch(fragment1);
    vote1 = votePda(fragment1, finalizeVerifier1.publicKey, fragmentBefore.round);
    roundResolution = roundResolutionPda(fragment1, fragmentBefore.round);
    computeWorker = workerPda(fragmentBefore.worker);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: finalizeVerifier1.publicKey,
        job: finalizeJob,
        fragment: fragment1,
        verifierWorker: verifierWorker1,
        computeWorker: computeWorker,
        vote: vote1,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: finalizeEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([finalizeVerifier1])
      .rpc();

    fragmentBefore = await program.account.fragment.fetch(fragment1);
    vote2 = votePda(fragment1, finalizeVerifier2.publicKey, fragmentBefore.round);
    roundResolution = roundResolutionPda(fragment1, fragmentBefore.round);
    computeWorker = workerPda(fragmentBefore.worker);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: finalizeVerifier2.publicKey,
        job: finalizeJob,
        fragment: fragment1,
        verifierWorker: verifierWorker2,
        computeWorker: computeWorker,
        vote: vote2,
        roundResolution: roundResolution,
        escrowAuth: escrowAuth,
        escrow: finalizeEscrow,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([finalizeVerifier2])
      .rpc();

    const [result] = PublicKey.findProgramAddressSync(
      [Buffer.from("result"), finalizeJob.toBuffer()],
      program.programId
    );

    const finalHash = Array(32).fill(42);
    const outputUri = Buffer.from("ipfs://silicium-result-3");

    const verifierToken1Claim = verifierToken1;
const verifierToken2Claim = verifierToken2;

// ---------- fragment 0 reward claims ----------
const fragment0State = await program.account.fragment.fetch(fragment0);
const round0 = fragment0State.round;

const [roundResolution0] = PublicKey.findProgramAddressSync(
  [
    Buffer.from("fragment_resolution"),
    fragment0.toBuffer(),
    u16le(round0),
  ],
  program.programId
);

const vote1Frag0 = votePda(fragment0, finalizeVerifier1.publicKey, round0);
const vote2Frag0 = votePda(fragment0, finalizeVerifier2.publicKey, round0);

await program.methods
  .claimVerifierReward()
  .accounts({
    verifier: finalizeVerifier1.publicKey,
    job: finalizeJob,
    fragment: fragment0,
    roundResolution: roundResolution0,
    vote: vote1Frag0,
    verifierWorker: verifierWorker1,
    escrowAuth: escrowAuth,
    escrow: finalizeEscrow,
    verifierToken: verifierToken1Claim,
    tokenProgram: TOKEN_PROGRAM_ID,
  })
  .signers([finalizeVerifier1])
  .rpc();

await program.methods
  .claimVerifierReward()
  .accounts({
    verifier: finalizeVerifier2.publicKey,
    job: finalizeJob,
    fragment: fragment0,
    roundResolution: roundResolution0,
    vote: vote2Frag0,
    verifierWorker: verifierWorker2,
    escrowAuth: escrowAuth,
    escrow: finalizeEscrow,
    verifierToken: verifierToken2Claim,
    tokenProgram: TOKEN_PROGRAM_ID,
  })
  .signers([finalizeVerifier2])
  .rpc();

  // ---------- fragment 1 reward claims ----------
  const fragment1State = await program.account.fragment.fetch(fragment1);
  const round1 = fragment1State.round;

  const [roundResolution1] = PublicKey.findProgramAddressSync(
    [
      Buffer.from("fragment_resolution"),
      fragment1.toBuffer(),
      u16le(round1),
    ],
    program.programId
  );

  const vote1Frag1 = votePda(fragment1, finalizeVerifier1.publicKey, round1);
  const vote2Frag1 = votePda(fragment1, finalizeVerifier2.publicKey, round1);

  await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: finalizeVerifier1.publicKey,
      job: finalizeJob,
      fragment: fragment1,
      roundResolution: roundResolution1,
      vote: vote1Frag1,
      verifierWorker: verifierWorker1,
      escrowAuth: escrowAuth,
      escrow: finalizeEscrow,
      verifierToken: verifierToken1Claim,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([finalizeVerifier1])
    .rpc();

  await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: finalizeVerifier2.publicKey,
      job: finalizeJob,
      fragment: fragment1,
      roundResolution: roundResolution1,
      vote: vote2Frag1,
      verifierWorker: verifierWorker2,
      escrowAuth: escrowAuth,
      escrow: finalizeEscrow,
      verifierToken: verifierToken2Claim,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([finalizeVerifier2])
    .rpc();

    await program.methods
      .finalizeJob(finalHash, outputUri)
      .accounts({
        client: client,
        job: finalizeJob,
        result: result,
        escrowAuth: escrowAuth,
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

  it("reclaims an expired fragment claim", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;
    const fragmentIndex = 0;

    reclaimJob = jobPda(client, reclaimJobId);
    const escrowAuth = escrowAuthPda(reclaimJob);

    const escrow = anchor.web3.Keypair.generate();
    reclaimEscrow = escrow.publicKey;

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      3_000_000
    );

    await program.methods
      .createJob(
        reclaimJobId,
        2,
        new anchor.BN(1_000_000),
        VERIFIER_REWARD_PER_VOTE,
        VERIFIER_REWARD_BUDGET,
        new anchor.BN(Math.floor(Date.now() / 1000) + 3600),
        2
      )
      .accounts({
        client: client,
        mint: sharedMint,
        job: reclaimJob,
        escrowAuth: escrowAuth,
        escrow: reclaimEscrow,
        clientToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    reclaimFragment = fragmentPda(reclaimJob, fragmentIndex);
    const workerAccount = workerPda(client);

    await program.methods
      .claimFragment(fragmentIndex)
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: reclaimJob,
        fragment: reclaimFragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const claimed = await program.account.fragment.fetch(reclaimFragment);
    assert.deepEqual(claimed.status, { claimed: {} });

    let reclaimed = false;

    for (let i = 0; i < 30; i++) {
      try {
        await program.methods
          .reclaimFragment(fragmentIndex)
          .accounts({
            caller: client,
            job: reclaimJob,
            fragment: reclaimFragment,
            previousWorkerAccount: workerAccount,
          })
          .rpc();

        reclaimed = true;
        break;
      } catch (e: any) {
        const msg = String(e);

        if (!msg.includes("ClaimStillActive")) {
          throw e;
        }

        await sleep(1000);
      }
    }

    assert.equal(reclaimed, true);

    const afterReclaim = await program.account.fragment.fetch(reclaimFragment);

    assert.deepEqual(afterReclaim.status, { available: {} });
    assert.equal(
      afterReclaim.assignedWorker.toBase58(),
      ZERO_PUBKEY.toBase58()
    );
  });


  it("initializes worker reputation at 5000", async () => {
    const worker = anchor.web3.Keypair.generate();

    await airdrop(worker.publicKey);

    const workerAccount = await registerWorker(worker);
    const account = await program.account.worker.fetch(workerAccount);

    assert.equal(reputationToNumber(account.reputation), 5000);
    assert.deepEqual(account.status, { active: {} });
    assert.equal(account.totalSubmitted, 0);
    assert.equal(account.totalVerified, 0);
    assert.equal(account.totalRejected, 0);
  });

  it("increases compute worker reputation when a fragment is verified", async () => {
    const computeWorker = await createReadyWorker();
    const verifier1 = await createReadyWorker();
    const verifier2 = await createReadyWorker();

    const jobId = new anchor.BN(100);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const before = await program.account.worker.fetch(computeWorker.workerAccount);
    assert.equal(reputationToNumber(before.reputation), 5000);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      31,
      32
    );

    await voteOnFragment(
      verifier1.keypair,
      verifier1.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    const mid = await program.account.worker.fetch(computeWorker.workerAccount);
    assert.equal(reputationToNumber(mid.reputation), 5000);

    await voteOnFragment(
      verifier2.keypair,
      verifier2.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    const after = await program.account.worker.fetch(computeWorker.workerAccount);
    const fragmentAfter = await program.account.fragment.fetch(fragment);

    assert.deepEqual(fragmentAfter.status, { verified: {} });
    assert.equal(reputationToNumber(after.reputation), 5080);
    assert.equal(after.totalVerified, 1);
  });

  it("decreases compute worker reputation when a fragment is rejected", async () => {
    const computeWorker = await createReadyWorker();
    const verifier1 = await createReadyWorker();
    const verifier2 = await createReadyWorker();

    const jobId = new anchor.BN(101);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const before = await program.account.worker.fetch(computeWorker.workerAccount);
    assert.equal(reputationToNumber(before.reputation), 5000);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      41,
      42
    );

    await voteOnFragment(
      verifier1.keypair,
      verifier1.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      false
    );

    const mid = await program.account.worker.fetch(computeWorker.workerAccount);
    assert.equal(reputationToNumber(mid.reputation), 5000);

    await voteOnFragment(
      verifier2.keypair,
      verifier2.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      false
    );

    const after = await program.account.worker.fetch(computeWorker.workerAccount);
    const fragmentAfter = await program.account.fragment.fetch(fragment);

    assert.deepEqual(fragmentAfter.status, { rejected: {} });
    assert.equal(reputationToNumber(after.reputation), 4750);
    assert.equal(after.totalRejected, 1);
  });

  it("increases verifier reputation when claiming a correct vote reward", async () => {
    const computeWorker = await createReadyWorker();
    const verifier1 = await createReadyWorker();
    const verifier2 = await createReadyWorker();

    const jobId = new anchor.BN(102);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      51,
      52
    );

    const voteResult1 = await voteOnFragment(
      verifier1.keypair,
      verifier1.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    await voteOnFragment(
      verifier2.keypair,
      verifier2.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    const beforeClaim = await program.account.worker.fetch(verifier1.workerAccount);
    assert.equal(reputationToNumber(beforeClaim.reputation), 5000);

    const fragmentAfter = await program.account.fragment.fetch(fragment);
    const roundResolution = roundResolutionPda(fragment, fragmentAfter.round);

    await program.methods
      .claimVerifierReward()
      .accounts({
        verifier: verifier1.keypair.publicKey,
        job: job,
        fragment: fragment,
        roundResolution: roundResolution,
        vote: voteResult1.vote,
        verifierWorker: verifier1.workerAccount,
        escrowAuth: escrowAuthPda(job),
        escrow: escrow,
        verifierToken: verifier1.workerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .signers([verifier1.keypair])
      .rpc();

    const afterClaim = await program.account.worker.fetch(verifier1.workerAccount);

    assert.equal(reputationToNumber(afterClaim.reputation), 5040);
    assert.equal(afterClaim.totalVerified, 1);
  });

  it("decreases reputation when a worker lets a claimed fragment expire", async () => {
    const computeWorker = await createReadyWorker();

    const jobId = new anchor.BN(103);
    const { job } = await createTestJob(jobId, 1, 2);

    const fragmentIndex = 0;
    const fragment = fragmentPda(job, fragmentIndex);

    const before = await program.account.worker.fetch(computeWorker.workerAccount);
    assert.equal(reputationToNumber(before.reputation), 5000);

    await program.methods
      .claimFragment(fragmentIndex)
      .accounts({
        worker: computeWorker.keypair.publicKey,
        workerAccount: computeWorker.workerAccount,
        job: job,
        fragment: fragment,
        workerToken: computeWorker.workerToken,
        systemProgram: SystemProgram.programId,
      })
      .signers([computeWorker.keypair])
      .rpc();

    let reclaimed = false;

    for (let i = 0; i < 30; i++) {
      try {
        await program.methods
          .reclaimFragment(fragmentIndex)
          .accounts({
            caller: provider.wallet.publicKey,
            job: job,
            fragment: fragment,
            previousWorkerAccount: computeWorker.workerAccount,
          })
          .rpc();

        reclaimed = true;
        break;
      } catch (e: any) {
        const msg = String(e);

        if (!msg.includes("ClaimStillActive")) {
          throw e;
        }

        await sleep(1000);
      }
    }

    assert.equal(reclaimed, true);

    const after = await program.account.worker.fetch(computeWorker.workerAccount);
    const fragmentAfter = await program.account.fragment.fetch(fragment);

    assert.deepEqual(fragmentAfter.status, { available: {} });
    assert.equal(reputationToNumber(after.reputation), 4880);
  });

  it("slashes a wrong vote", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;
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
        treasuryState: treasuryState,
        treasuryAuth: treasuryAuth,
        treasury: treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([treasury])
      .rpc();

    const job = jobPda(client, slashJobId);
    const escrowAuth = escrowAuthPda(job);
    const escrow = anchor.web3.Keypair.generate();

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      3_500_000
    );

    await program.methods
      .createJob(
        slashJobId,
        2,
        new anchor.BN(1_000_000),
        VERIFIER_REWARD_PER_VOTE,
        VERIFIER_REWARD_BUDGET,
        new anchor.BN(Math.floor(Date.now() / 1000) + 3600),
        2
      )
      .accounts({
        client: client,
        mint: sharedMint,
        job: job,
        escrowAuth: escrowAuth,
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
      .claimFragment(fragmentIndex)
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: job,
        fragment: fragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    await program.methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: client,
        workerAccount: workerAccount,
        job: job,
        fragment: fragment,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const badVerifier = anchor.web3.Keypair.generate();
    await airdrop(badVerifier.publicKey);

    const badVerifierWorker = await registerWorker(badVerifier);
    const badVerifierToken = await createAndFundWorkerToken(badVerifier.publicKey);
    const { stakeAuth, stakeVault } = await stakeRegisteredWorker(
      badVerifier,
      badVerifierWorker,
      badVerifierToken
    );

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const badVote = votePda(fragment, badVerifier.publicKey, fragmentBefore.round);
    const badVoteRoundResolution = roundResolutionPda(fragment, fragmentBefore.round);
    const badVoteComputeWorker = workerPda(fragmentBefore.worker);

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: badVerifier.publicKey,
        job: job,
        fragment: fragment,
        verifierWorker: badVerifierWorker,
        computeWorker: badVoteComputeWorker,
        vote: badVote,
        roundResolution: badVoteRoundResolution,
        escrowAuth: escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([badVerifier])
      .rpc();

    const goodVerifier1 = anchor.web3.Keypair.generate();
    await airdrop(goodVerifier1.publicKey);
    const goodVerifierWorker1 = await registerWorker(goodVerifier1);
    const goodVerifierToken1 = await createAndFundWorkerToken(goodVerifier1.publicKey);
    await stakeRegisteredWorker(goodVerifier1, goodVerifierWorker1, goodVerifierToken1);

    let fragmentState = await program.account.fragment.fetch(fragment);
    const goodVote1 = votePda(fragment, goodVerifier1.publicKey, fragmentState.round);
    const goodVote1RoundResolution = roundResolutionPda(fragment, fragmentState.round);
    const goodVote1ComputeWorker = workerPda(fragmentState.worker);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: goodVerifier1.publicKey,
        job: job,
        fragment: fragment,
        verifierWorker: goodVerifierWorker1,
        computeWorker: goodVote1ComputeWorker,
        vote: goodVote1,
        roundResolution: goodVote1RoundResolution,
        escrowAuth: escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier1])
      .rpc();

    const goodVerifier2 = anchor.web3.Keypair.generate();
    await airdrop(goodVerifier2.publicKey);
    const goodVerifierWorker2 = await registerWorker(goodVerifier2);
    const goodVerifierToken2 = await createAndFundWorkerToken(goodVerifier2.publicKey);
    await stakeRegisteredWorker(goodVerifier2, goodVerifierWorker2, goodVerifierToken2);

    fragmentState = await program.account.fragment.fetch(fragment);
    const goodVote2 = votePda(fragment, goodVerifier2.publicKey, fragmentState.round);
    const goodVote2RoundResolution = roundResolutionPda(fragment, fragmentState.round);
    const goodVote2ComputeWorker = workerPda(fragmentState.worker);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: goodVerifier2.publicKey,
        job: job,
        fragment: fragment,
        verifierWorker: goodVerifierWorker2,
        computeWorker: goodVote2ComputeWorker,
        vote: goodVote2,
        roundResolution: goodVote2RoundResolution,
        escrowAuth: escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier2])
      .rpc();

    const stakeBefore = await provider.connection.getTokenAccountBalance(stakeVault);
    const treasuryBefore = await provider.connection.getTokenAccountBalance(treasury.publicKey);

    const fragmentResolved = await program.account.fragment.fetch(fragment);
    const slashRoundResolution = roundResolutionPda(fragment, fragmentResolved.round);

    await program.methods
      .slashVote()
      .accounts({
        slasher: client,
        job: job,
        fragment: fragment,
        roundResolution: slashRoundResolution,
        vote: badVote,
        verifierWorker: badVerifierWorker,
        treasuryState: treasuryState,
        stakeAuth: stakeAuth,
        stakeVault: stakeVault,
        treasuryAuth: treasuryAuth,
        treasury: treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();

    const voteAfter = await program.account.fragmentVote.fetch(badVote);
    const workerAfter = await program.account.worker.fetch(badVerifierWorker);
    const stakeAfter = await provider.connection.getTokenAccountBalance(stakeVault);
    const treasuryAfter = await provider.connection.getTokenAccountBalance(treasury.publicKey);

    assert.equal(voteAfter.slashed, true);
    assert.equal(workerAfter.stakeAmount.toString(), "900000");
    assert.equal(reputationToNumber(workerAfter.reputation), 4520);
    assert.equal(workerAfter.totalRejected, 1);

    assert.equal(
      Number(stakeBefore.value.amount) - Number(stakeAfter.value.amount),
      100000
    );

    assert.equal(
      Number(treasuryAfter.value.amount) - Number(treasuryBefore.value.amount),
      100000
    );
  });


  it("rejects a job with too many fragments", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const jobId = new anchor.BN(200);
    const job = jobPda(client, jobId);
    const escrowAuth = escrowAuthPda(job);
    const escrow = anchor.web3.Keypair.generate();

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      10_000_000
    );

    await expectTxToFail(
      async () => {
        await program.methods
          .createJob(
            jobId,
            1001,
            new anchor.BN(1_000_000),
            VERIFIER_REWARD_PER_VOTE,
            new anchor.BN(300_000_000),
            new anchor.BN(Math.floor(Date.now() / 1000) + 3600),
            2
          )
          .accounts({
            client: client,
            mint: sharedMint,
            job: job,
            escrowAuth: escrowAuth,
            escrow: escrow.publicKey,
            clientToken: sharedWorkerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
            rent: SYSVAR_RENT_PUBKEY,
          })
          .signers([escrow])
          .rpc();
      },
      "TooManyFragments"
    );
  });


    it("rejects a job with an invalid short deadline", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const jobId = new anchor.BN(201);
    const job = jobPda(client, jobId);
    const escrowAuth = escrowAuthPda(job);
    const escrow = anchor.web3.Keypair.generate();

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      10_000_000
    );

    await expectTxToFail(
      async () => {
        await program.methods
          .createJob(
            jobId,
            1,
            new anchor.BN(1_000_000),
            VERIFIER_REWARD_PER_VOTE,
            VERIFIER_REWARD_BUDGET,
            new anchor.BN(Math.floor(Date.now() / 1000) + 10),
            2
          )
          .accounts({
            client: client,
            mint: sharedMint,
            job: job,
            escrowAuth: escrowAuth,
            escrow: escrow.publicKey,
            clientToken: sharedWorkerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
            rent: SYSVAR_RENT_PUBKEY,
          })
          .signers([escrow])
          .rpc();
      },
      "InvalidDeadline"
    );
  });
  
  
  it("rejects claim from an unstaked worker", async () => {
    const unstakedWorker = anchor.web3.Keypair.generate();
    await airdrop(unstakedWorker.publicKey);

    const unstakedWorkerAccount = await registerWorker(unstakedWorker);
    const unstakedWorkerToken = await createAndFundWorkerToken(unstakedWorker.publicKey);

    const jobId = new anchor.BN(202);
    const { job } = await createTestJob(jobId, 1, 2);

    const fragmentIndex = 0;
    const fragment = fragmentPda(job, fragmentIndex);

    await expectTxToFail(
      async () => {
        await program.methods
          .claimFragment(fragmentIndex)
          .accounts({
            worker: unstakedWorker.publicKey,
            workerAccount: unstakedWorkerAccount,
            job: job,
            fragment: fragment,
            workerToken: unstakedWorkerToken,
            systemProgram: SystemProgram.programId,
          })
          .signers([unstakedWorker])
          .rpc();
      },
      "NotAuthorized"
    );
  });


  it("rejects vote from an unstaked verifier", async () => {
    const computeWorker = await createReadyWorker();

    const unstakedVerifier = anchor.web3.Keypair.generate();
    await airdrop(unstakedVerifier.publicKey);

    const unstakedVerifierWorker = await registerWorker(unstakedVerifier);

    const jobId = new anchor.BN(203);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      61,
      62
    );

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const vote = votePda(fragment, unstakedVerifier.publicKey, fragmentBefore.round);
    const roundResolution = roundResolutionPda(fragment, fragmentBefore.round);
    const computeWorkerPda = workerPda(fragmentBefore.worker);

    await expectTxToFail(
      async () => {
        await program.methods
          .voteFragment(true)
          .accounts({
            verifier: unstakedVerifier.publicKey,
            job: job,
            fragment: fragment,
            verifierWorker: unstakedVerifierWorker,
            computeWorker: computeWorkerPda,
            vote: vote,
            roundResolution: roundResolution,
            escrowAuth: escrowAuthPda(job),
            escrow: escrow,
            workerToken: computeWorker.workerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
          })
          .signers([unstakedVerifier])
          .rpc();
      },
      "NotAuthorized"
    );
  });


  it("rejects vote from the job client", async () => {
    const computeWorker = await createReadyWorker();

    const jobId = new anchor.BN(204);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      71,
      72
    );

    const client = provider.wallet.publicKey;
    const clientWorker = workerPda(client);

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const vote = votePda(fragment, client, fragmentBefore.round);
    const roundResolution = roundResolutionPda(fragment, fragmentBefore.round);
    const computeWorkerPda = workerPda(fragmentBefore.worker);

    await expectTxToFail(
      async () => {
        await program.methods
          .voteFragment(true)
          .accounts({
            verifier: client,
            job: job,
            fragment: fragment,
            verifierWorker: clientWorker,
            computeWorker: computeWorkerPda,
            vote: vote,
            roundResolution: roundResolution,
            escrowAuth: escrowAuthPda(job),
            escrow: escrow,
            workerToken: computeWorker.workerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
          })
          .rpc();
      },
      "ClientCannotVerifyOwnJob"
    );
  });


  it("rejects self vote from the compute worker", async () => {
    const computeWorker = await createReadyWorker();

    const jobId = new anchor.BN(205);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      81,
      82
    );

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const vote = votePda(fragment, computeWorker.keypair.publicKey, fragmentBefore.round);
    const roundResolution = roundResolutionPda(fragment, fragmentBefore.round);

    await expectTxToFail(
      async () => {
        await program.methods
          .voteFragment(true)
          .accounts({
            verifier: computeWorker.keypair.publicKey,
            job: job,
            fragment: fragment,
            verifierWorker: computeWorker.workerAccount,
            computeWorker: computeWorker.workerAccount,
            vote: vote,
            roundResolution: roundResolution,
            escrowAuth: escrowAuthPda(job),
            escrow: escrow,
            workerToken: computeWorker.workerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
          })
          .signers([computeWorker.keypair])
          .rpc();
      },
      "SelfVoteForbidden"
    );
  });


  it("rejects double slashing the same wrong vote", async () => {
    const client = provider.wallet.publicKey;

    const [treasuryState] = PublicKey.findProgramAddressSync(
      [Buffer.from("treasury"), sharedMint.toBuffer()],
      program.programId
    );

    const [treasuryAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("treasury_auth"), sharedMint.toBuffer()],
      program.programId
    );

    let treasuryAccount: PublicKey;

    try {
      const existingTreasury = await program.account.treasury.fetch(treasuryState);
      treasuryAccount = existingTreasury.treasuryTokenAccount;
    } catch {
      const treasury = anchor.web3.Keypair.generate();
      treasuryAccount = treasury.publicKey;

      await program.methods
        .initTreasury()
        .accounts({
          payer: client,
          mint: sharedMint,
          treasuryState: treasuryState,
          treasuryAuth: treasuryAuth,
          treasury: treasury.publicKey,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
          rent: SYSVAR_RENT_PUBKEY,
        })
        .signers([treasury])
        .rpc();
    }

    const computeWorker = await createReadyWorker();
    const badVerifier = await createReadyWorker();
    const goodVerifier1 = await createReadyWorker();
    const goodVerifier2 = await createReadyWorker();

    const jobId = new anchor.BN(208);
    const { job, escrow } = await createTestJob(jobId, 1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      101,
      102
    );

    const badVoteResult = await voteOnFragment(
      badVerifier.keypair,
      badVerifier.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      false
    );

    await voteOnFragment(
      goodVerifier1.keypair,
      goodVerifier1.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    await voteOnFragment(
      goodVerifier2.keypair,
      goodVerifier2.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    const fragmentResolved = await program.account.fragment.fetch(fragment);
    const slashRoundResolution = roundResolutionPda(fragment, fragmentResolved.round);

    await program.methods
      .slashVote()
      .accounts({
        slasher: client,
        job: job,
        fragment: fragment,
        roundResolution: slashRoundResolution,
        vote: badVoteResult.vote,
        verifierWorker: badVerifier.workerAccount,
        treasuryState: treasuryState,
        stakeAuth: badVerifier.stakeAuth,
        stakeVault: badVerifier.stakeVault,
        treasuryAuth: treasuryAuth,
        treasury: treasuryAccount,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();

    await expectTxToFail(
      async () => {
        await program.methods
          .slashVote()
          .accounts({
            slasher: client,
            job: job,
            fragment: fragment,
            roundResolution: slashRoundResolution,
            vote: badVoteResult.vote,
            verifierWorker: badVerifier.workerAccount,
            treasuryState: treasuryState,
            stakeAuth: badVerifier.stakeAuth,
            stakeVault: badVerifier.stakeVault,
            treasuryAuth: treasuryAuth,
            treasury: treasuryAccount,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .rpc();
      },
      "VoteAlreadySlashed"
    );
  });


    it("initializes a network staking pool", async () => {
    const payer = provider.wallet.publicKey;

    stakingPool = stakingPoolPda(sharedMint);
    stakingPoolAuth = stakingPoolAuthPda(sharedMint);

    const stakeVault = anchor.web3.Keypair.generate();
    const rewardVault = anchor.web3.Keypair.generate();

    stakingStakeVault = stakeVault.publicKey;
    stakingRewardVault = rewardVault.publicKey;

    await program.methods
      .initStakingPool()
      .accounts({
        payer: payer,
        mint: sharedMint,
        pool: stakingPool,
        poolAuth: stakingPoolAuth,
        stakeVault: stakingStakeVault,
        rewardVault: stakingRewardVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([stakeVault, rewardVault])
      .rpc();

    const poolAccount = await program.account.stakingPool.fetch(stakingPool);

    assert.equal(poolAccount.mint.toBase58(), sharedMint.toBase58());
    assert.equal(poolAccount.authority.toBase58(), stakingPoolAuth.toBase58());
    assert.equal(poolAccount.stakeVault.toBase58(), stakingStakeVault.toBase58());
    assert.equal(poolAccount.rewardVault.toBase58(), stakingRewardVault.toBase58());
    assert.equal(poolAccount.totalStaked.toString(), "0");
    assert.equal(poolAccount.accRewardPerShare.toString(), "0");
  });

  it("allows a passive user to stake on the network", async () => {
    const staker = anchor.web3.Keypair.generate();
    await airdrop(staker.publicKey);

    const stakerToken = await createAndFundWorkerToken(staker.publicKey, 10_000_000);
    const stakerAccount = networkStakerPda(staker.publicKey, sharedMint);

    await program.methods
      .stakeNetwork(new anchor.BN(2_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
        ownerToken: stakerToken,
        stakeVault: stakingStakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([staker])
      .rpc();

    const poolAccount = await program.account.stakingPool.fetch(stakingPool);
    const stakerAccountData = await program.account.networkStaker.fetch(stakerAccount);
    const vaultBalance = await provider.connection.getTokenAccountBalance(stakingStakeVault);

    assert.equal(poolAccount.totalStaked.toString(), "2000000");
    assert.equal(stakerAccountData.owner.toBase58(), staker.publicKey.toBase58());
    assert.equal(stakerAccountData.mint.toBase58(), sharedMint.toBase58());
    assert.equal(stakerAccountData.stakeAmount.toString(), "2000000");
    assert.equal(stakerAccountData.pendingRewards.toString(), "0");
    assert.equal(Number(vaultBalance.value.amount), 2_000_000);
  });

  it("rejects funding staking rewards when there are no stakers", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const isolatedMint = await createMint(
      provider.connection,
      payer,
      client,
      null,
      6
    );

    const isolatedPool = stakingPoolPda(isolatedMint);
    const isolatedPoolAuth = stakingPoolAuthPda(isolatedMint);

    const isolatedStakeVault = anchor.web3.Keypair.generate();
    const isolatedRewardVault = anchor.web3.Keypair.generate();

    const funderToken = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      isolatedMint,
      client
    );

    await mintTo(
      provider.connection,
      payer,
      isolatedMint,
      funderToken,
      client,
      10_000_000
    );

    await program.methods
      .initStakingPool()
      .accounts({
        payer: client,
        mint: isolatedMint,
        pool: isolatedPool,
        poolAuth: isolatedPoolAuth,
        stakeVault: isolatedStakeVault.publicKey,
        rewardVault: isolatedRewardVault.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([isolatedStakeVault, isolatedRewardVault])
      .rpc();

    await expectTxToFail(
      async () => {
        await program.methods
          .fundStakingRewards(new anchor.BN(1_000_000))
          .accounts({
            funder: client,
            mint: isolatedMint,
            pool: isolatedPool,
            funderToken: funderToken,
            rewardVault: isolatedRewardVault.publicKey,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .rpc();
      },
      "NoStakers"
    );
  });

  it("funds staking rewards and lets a staker claim them", async () => {
    const staker = anchor.web3.Keypair.generate();
    await airdrop(staker.publicKey);

    const stakerToken = await createAndFundWorkerToken(staker.publicKey, 10_000_000);
    const stakerAccount = networkStakerPda(staker.publicKey, sharedMint);

    await program.methods
      .stakeNetwork(new anchor.BN(2_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
        ownerToken: stakerToken,
        stakeVault: stakingStakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([staker])
      .rpc();

    const funder = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      funder,
      1_000_000
    );

    await program.methods
      .fundStakingRewards(new anchor.BN(1_000_000))
      .accounts({
        funder: funder,
        mint: sharedMint,
        pool: stakingPool,
        funderToken: sharedWorkerToken,
        rewardVault: stakingRewardVault,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();

    const beforeClaim = await provider.connection.getTokenAccountBalance(stakerToken);

    await program.methods
      .claimStakingReward()
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        poolAuth: stakingPoolAuth,
        staker: stakerAccount,
        rewardVault: stakingRewardVault,
        ownerRewardToken: stakerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .signers([staker])
      .rpc();

    const afterClaim = await provider.connection.getTokenAccountBalance(stakerToken);
    const stakerAfter = await program.account.networkStaker.fetch(stakerAccount);

    const before = Number(beforeClaim.value.amount);
    const after = Number(afterClaim.value.amount);

    assert.isAbove(after - before, 0);
    assert.equal(stakerAfter.pendingRewards.toString(), "0");
  });

  it("rejects claiming staking rewards when there are no rewards", async () => {
    const staker = anchor.web3.Keypair.generate();
    await airdrop(staker.publicKey);

    const stakerToken = await createAndFundWorkerToken(staker.publicKey, 10_000_000);
    const stakerAccount = networkStakerPda(staker.publicKey, sharedMint);

    await program.methods
      .stakeNetwork(new anchor.BN(1_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
        ownerToken: stakerToken,
        stakeVault: stakingStakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([staker])
      .rpc();

    await expectTxToFail(
      async () => {
        await program.methods
          .claimStakingReward()
          .accounts({
            owner: staker.publicKey,
            mint: sharedMint,
            pool: stakingPool,
            poolAuth: stakingPoolAuth,
            staker: stakerAccount,
            rewardVault: stakingRewardVault,
            ownerRewardToken: stakerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .signers([staker])
          .rpc();
      },
      "NoStakingRewards"
    );
  });

  it("requests unstake and rejects withdraw before cooldown", async () => {
    const staker = anchor.web3.Keypair.generate();
    await airdrop(staker.publicKey);

    const stakerToken = await createAndFundWorkerToken(staker.publicKey, 10_000_000);
    const stakerAccount = networkStakerPda(staker.publicKey, sharedMint);

    await program.methods
      .stakeNetwork(new anchor.BN(2_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
        ownerToken: stakerToken,
        stakeVault: stakingStakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([staker])
      .rpc();

    await program.methods
      .requestUnstake(new anchor.BN(1_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
      })
      .signers([staker])
      .rpc();

    const stakerAfterRequest = await program.account.networkStaker.fetch(stakerAccount);

    assert.equal(stakerAfterRequest.stakeAmount.toString(), "1000000");
    assert.equal(stakerAfterRequest.unstakeRequestedAmount.toString(), "1000000");
    assert.isAbove(Number(stakerAfterRequest.unstakeAvailableAt.toString()), 0);

    await expectTxToFail(
      async () => {
        await program.methods
          .withdrawUnstaked()
          .accounts({
            owner: staker.publicKey,
            mint: sharedMint,
            pool: stakingPool,
            poolAuth: stakingPoolAuth,
            staker: stakerAccount,
            stakeVault: stakingStakeVault,
            ownerToken: stakerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .signers([staker])
          .rpc();
      },
      "UnstakeCooldownActive"
    );
  });

  it("withdraws unstaked tokens after cooldown", async () => {
    const staker = anchor.web3.Keypair.generate();
    await airdrop(staker.publicKey);

    const stakerToken = await createAndFundWorkerToken(staker.publicKey, 10_000_000);
    const stakerAccount = networkStakerPda(staker.publicKey, sharedMint);

    await program.methods
      .stakeNetwork(new anchor.BN(2_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
        ownerToken: stakerToken,
        stakeVault: stakingStakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([staker])
      .rpc();

    const beforeRequest = await provider.connection.getTokenAccountBalance(stakerToken);

    await program.methods
      .requestUnstake(new anchor.BN(1_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
      })
      .signers([staker])
      .rpc();

    let withdrawn = false;

    for (let i = 0; i < 20; i++) {
      try {
        await program.methods
          .withdrawUnstaked()
          .accounts({
            owner: staker.publicKey,
            mint: sharedMint,
            pool: stakingPool,
            poolAuth: stakingPoolAuth,
            staker: stakerAccount,
            stakeVault: stakingStakeVault,
            ownerToken: stakerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .signers([staker])
          .rpc();

        withdrawn = true;
        break;
      } catch (e: any) {
        const msg = String(e);

        if (!msg.includes("UnstakeCooldownActive")) {
          throw e;
        }

        await sleep(1000);
      }
    }

    assert.equal(withdrawn, true);

    const afterWithdraw = await provider.connection.getTokenAccountBalance(stakerToken);
    const stakerAfter = await program.account.networkStaker.fetch(stakerAccount);

    const before = Number(beforeRequest.value.amount);
    const after = Number(afterWithdraw.value.amount);

    assert.equal(after - before, 1_000_000);

    assert.equal(stakerAfter.unstakeRequestedAmount.toString(), "0");
    assert.equal(stakerAfter.unstakeAvailableAt.toString(), "0");
  });

  it("rejects withdrawing when there is nothing to withdraw", async () => {
    const staker = anchor.web3.Keypair.generate();
    await airdrop(staker.publicKey);

    const stakerToken = await createAndFundWorkerToken(staker.publicKey, 10_000_000);
    const stakerAccount = networkStakerPda(staker.publicKey, sharedMint);

    await program.methods
      .stakeNetwork(new anchor.BN(1_000_000))
      .accounts({
        owner: staker.publicKey,
        mint: sharedMint,
        pool: stakingPool,
        staker: stakerAccount,
        ownerToken: stakerToken,
        stakeVault: stakingStakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([staker])
      .rpc();

    await expectTxToFail(
      async () => {
        await program.methods
          .withdrawUnstaked()
          .accounts({
            owner: staker.publicKey,
            mint: sharedMint,
            pool: stakingPool,
            poolAuth: stakingPoolAuth,
            staker: stakerAccount,
            stakeVault: stakingStakeVault,
            ownerToken: stakerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
          })
          .signers([staker])
          .rpc();
      },
      "NothingToWithdraw"
    );
  });
});
