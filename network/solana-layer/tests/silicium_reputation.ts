import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import {
  LAMPORTS_PER_SOL,
  PublicKey,
  SystemProgram,
  SYSVAR_RENT_PUBKEY,
  Transaction,
} from "@solana/web3.js";
import { assert } from "chai";
import {
  TOKEN_PROGRAM_ID,
  createAssociatedTokenAccount,
  createMint,
  mintTo,
} from "@solana/spl-token";

const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer as Program;

const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);

let mint: PublicKey;
let clientToken: PublicKey;
let jobNonce = 50_000 + Math.floor(Math.random() * 100_000);

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

function nextJobId(): anchor.BN {
  jobNonce += 1;
  return new anchor.BN(jobNonce);
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

function workerPayoutPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("worker_payout"), workerAccount.toBuffer()],
    program.programId
  )[0];
}

function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), job.toBuffer()],
    program.programId
  )[0];
}

function maxLeafFragments(initialFragments: number): number {
  const childSlotsPerRoot = Math.floor((1_000 - initialFragments) / initialFragments);
  return Math.min(initialFragments * 16, initialFragments * (1 + Math.floor(childSlotsPerRoot / 2)), 1_000);
}

function minimumVerifierRewardBudget(initialFragments: number, fragmentQuorum: number): anchor.BN {
  return new anchor.BN(maxLeafFragments(initialFragments))
    .mul(new anchor.BN(fragmentQuorum))
    .mul(VERIFIER_REWARD_PER_VOTE);
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
    [Buffer.from("fragment_resolution"), fragment.toBuffer(), u16le(round)],
    program.programId
  )[0];
}

function treasuryPda(mintPk: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("treasury"), mintPk.toBuffer()],
    program.programId
  )[0];
}

function treasuryAuthPda(mintPk: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("treasury_auth"), mintPk.toBuffer()],
    program.programId
  )[0];
}

function rep(value: any): number {
  if (value === undefined || value === null) {
    throw new Error("Missing reputation value. Did you rebuild the IDL?");
  }

  return Number(value.toString());
}

function workerRep(
  account: any,
  field: "computeReputation" | "verifyReputation" | "globalReputation"
): number {
  if (account[field] === undefined || account[field] === null) {
    throw new Error(`Missing worker field ${field}. Did you rebuild the IDL after V2.5?`);
  }

  return rep(account[field]);
}

function assertComputeUnchanged(before: any, after: any) {
  assert.equal(
    workerRep(after, "computeReputation"),
    workerRep(before, "computeReputation")
  );
}

function assertVerifyUnchanged(before: any, after: any) {
  assert.equal(
    workerRep(after, "verifyReputation"),
    workerRep(before, "verifyReputation")
  );
}

/**
 * Important for CI:
 * Generated Keypairs have 0 SOL.
 * registerWorker creates the Worker PDA with `worker` as payer, so the worker keypair
 * must have lamports before calling registerWorker.
 */
async function fundKeypair(
  keypair: anchor.web3.Keypair,
  solAmount = 0.1
): Promise<void> {
  const currentBalance = await provider.connection.getBalance(keypair.publicKey);

  if (currentBalance >= 0.02 * LAMPORTS_PER_SOL) {
    return;
  }

  const tx = new Transaction().add(
    SystemProgram.transfer({
      fromPubkey: provider.wallet.publicKey,
      toPubkey: keypair.publicKey,
      lamports: Math.floor(solAmount * LAMPORTS_PER_SOL),
    })
  );

  await provider.sendAndConfirm(tx, []);
}

async function registerWorker(workerKeypair: anchor.web3.Keypair): Promise<PublicKey> {
  await fundKeypair(workerKeypair);

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

async function createAndFundWorkerToken(
  owner: PublicKey,
  amount = 10_000_000
): Promise<PublicKey> {
  const payer = provider.wallet.payer as anchor.web3.Keypair;
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
    provider.wallet.publicKey,
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

async function createReadyWorker(amount = 1_000_000) {
  const keypair = anchor.web3.Keypair.generate();

  await fundKeypair(keypair);

  const workerAccount = await registerWorker(keypair);
  const workerToken = await createAndFundWorkerToken(keypair.publicKey);
  const stake = await stakeRegisteredWorker(
    keypair,
    workerAccount,
    workerToken,
    amount
  );

  return {
    keypair,
    workerAccount,
    workerToken,
    stakeAuth: stake.stakeAuth,
    stakeVault: stake.stakeVault,
  };
}

async function createTestJob(expectedFragments = 1, fragmentQuorum = 2) {
  const client = provider.wallet.publicKey;
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const jobId = nextJobId();
  const job = jobPda(client, jobId);
  const escrowAuth = escrowAuthPda(job);
  const escrow = anchor.web3.Keypair.generate();
  const rewardPerFragment = new anchor.BN(1_000_000);
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
  const verifierRewardBudget = minimumVerifierRewardBudget(expectedFragments, fragmentQuorum);
  const totalToMint = rewardPerFragment
    .mul(new anchor.BN(maxLeafFragments(expectedFragments)))
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
      VERIFIER_REWARD_PER_VOTE,
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

  return { job, escrow: escrow.publicKey, escrowAuth, jobId };
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
      workerAccount,
      job,
      fragment,
      workerToken,
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
      workerPayout: workerPayoutPda(computeWorker),
      workerPayoutToken: workerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier])
    .rpc();

  return { vote, roundResolution };
}

async function claimVerifierReward(
  verifier: anchor.web3.Keypair,
  verifierWorker: PublicKey,
  verifierToken: PublicKey,
  job: PublicKey,
  fragment: PublicKey,
  escrow: PublicKey,
  vote: PublicKey
) {
  const fragmentState = await program.account.fragment.fetch(fragment);
  const roundResolution = roundResolutionPda(fragment, fragmentState.round);

  await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: verifier.publicKey,
      job,
      fragment,
      roundResolution,
      vote,
      verifierWorker,
      escrowAuth: escrowAuthPda(job),
      escrow,
      verifierToken,
      verifierPayout: workerPayoutPda(verifierWorker),
      verifierPayoutToken: verifierToken,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier])
    .rpc();
}

async function completeVerifiedFragmentAndClaimFirstVerifierReward() {
  const computeWorker = await createReadyWorker();
  const verifier1 = await createReadyWorker();
  const verifier2 = await createReadyWorker();
  const { job, escrow } = await createTestJob(1, 2);

  const fragment = await claimAndSubmitFragment(
    computeWorker.keypair,
    computeWorker.workerAccount,
    computeWorker.workerToken,
    job,
    0,
    11,
    12
  );

  const vote1 = await voteOnFragment(
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

  await claimVerifierReward(
    verifier1.keypair,
    verifier1.workerAccount,
    verifier1.workerToken,
    job,
    fragment,
    escrow,
    vote1.vote
  );

  return { computeWorker, verifier1, verifier2, job, escrow, fragment };
}

async function boostVerifierReputation(
  verifier: Awaited<ReturnType<typeof createReadyWorker>>,
  rounds = 3
) {
  for (let i = 0; i < rounds; i++) {
    const computeWorker = await createReadyWorker();
    const coVerifier = await createReadyWorker();
    const { job, escrow } = await createTestJob(1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      60 + i,
      70 + i
    );

    const boostedVote = await voteOnFragment(
      verifier.keypair,
      verifier.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    await voteOnFragment(
      coVerifier.keypair,
      coVerifier.workerAccount,
      job,
      fragment,
      escrow,
      computeWorker.workerToken,
      true
    );

    await claimVerifierReward(
      verifier.keypair,
      verifier.workerAccount,
      verifier.workerToken,
      job,
      fragment,
      escrow,
      boostedVote.vote
    );
  }
}

describe("silicium v2.5 dual reputation", () => {
  before(async () => {
    const payer = provider.wallet.payer as anchor.web3.Keypair;
    const authority = provider.wallet.publicKey;

    mint = await createMint(provider.connection, payer, authority, null, 6);
    clientToken = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      mint,
      authority
    );

    await mintTo(
      provider.connection,
      payer,
      mint,
      clientToken,
      authority,
      100_000_000
    );
  });

  it("initializes compute, verify and global reputation at 5000", async () => {
    const worker = await createReadyWorker();
    const account = await program.account.worker.fetch(worker.workerAccount);

    assert.equal(workerRep(account, "computeReputation"), 5000);
    assert.equal(workerRep(account, "verifyReputation"), 5000);
    assert.equal(workerRep(account, "globalReputation"), 5000);
    assert.deepEqual(account.status, { active: {} });
  });

  it("compute success increases only compute reputation and keeps verify reputation unchanged", async () => {
    const computeWorker = await createReadyWorker();
    const verifier1 = await createReadyWorker();
    const verifier2 = await createReadyWorker();
    const { job, escrow } = await createTestJob(1, 2);

    const before = await program.account.worker.fetch(computeWorker.workerAccount);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      21,
      22
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

    assert.isAbove(
      workerRep(after, "computeReputation"),
      workerRep(before, "computeReputation")
    );

    assertVerifyUnchanged(before, after);

    assert.isAbove(
      workerRep(after, "globalReputation"),
      workerRep(before, "globalReputation")
    );
  });

  it("compute rejection decreases only compute reputation and keeps verify reputation unchanged", async () => {
    const computeWorker = await createReadyWorker();
    const verifier1 = await createReadyWorker();
    const verifier2 = await createReadyWorker();
    const { job, escrow } = await createTestJob(1, 2);

    const before = await program.account.worker.fetch(computeWorker.workerAccount);

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
      false
    );

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

    assert.isBelow(
      workerRep(after, "computeReputation"),
      workerRep(before, "computeReputation")
    );

    assertVerifyUnchanged(before, after);

    assert.isBelow(
      workerRep(after, "globalReputation"),
      workerRep(before, "globalReputation")
    );
  });

  it("claiming a correct verifier reward increases only verify reputation", async () => {
    const { verifier1 } = await completeVerifiedFragmentAndClaimFirstVerifierReward();
    const after = await program.account.worker.fetch(verifier1.workerAccount);

    assert.equal(workerRep(after, "computeReputation"), 5000);
    assert.isAbove(workerRep(after, "verifyReputation"), 5000);
    assert.isAbove(workerRep(after, "globalReputation"), 5000);
  });

  it("a verifier reward does not improve compute reputation", async () => {
    const computeWorker = await createReadyWorker();
    const verifier1 = await createReadyWorker();
    const verifier2 = await createReadyWorker();
    const { job, escrow } = await createTestJob(1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      41,
      42
    );

    const vote1 = await voteOnFragment(
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

    await claimVerifierReward(
      verifier1.keypair,
      verifier1.workerAccount,
      verifier1.workerToken,
      job,
      fragment,
      escrow,
      vote1.vote
    );

    const afterClaim = await program.account.worker.fetch(verifier1.workerAccount);

    assertComputeUnchanged(beforeClaim, afterClaim);

    assert.isAbove(
      workerRep(afterClaim, "verifyReputation"),
      workerRep(beforeClaim, "verifyReputation")
    );
  });

  it("an expired claim penalizes compute reputation but not verify reputation", async () => {
    const computeWorker = await createReadyWorker();
    const { job } = await createTestJob(1, 2);
    const fragmentIndex = 0;
    const fragment = fragmentPda(job, fragmentIndex);

    const before = await program.account.worker.fetch(computeWorker.workerAccount);

    await program.methods
      .claimFragment(fragmentIndex)
      .accounts({
        worker: computeWorker.keypair.publicKey,
        workerAccount: computeWorker.workerAccount,
        job,
        fragment,
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
            job,
            fragment,
            previousWorkerAccount: computeWorker.workerAccount,
          })
          .rpc();

        reclaimed = true;
        break;
      } catch (e: any) {
        if (!String(e).includes("ClaimStillActive")) {
          throw e;
        }

        await sleep(1000);
      }
    }

    assert.equal(reclaimed, true);

    const after = await program.account.worker.fetch(computeWorker.workerAccount);

    assert.isBelow(
      workerRep(after, "computeReputation"),
      workerRep(before, "computeReputation")
    );

    assertVerifyUnchanged(before, after);
  });

  it("slashing a wrong vote decreases verify reputation but not compute reputation", async () => {
    const client = provider.wallet.publicKey;

    const treasuryState = treasuryPda(mint);
    const treasuryAuth = treasuryAuthPda(mint);
    const treasury = anchor.web3.Keypair.generate();

    try {
      await program.methods
        .initTreasury()
        .accounts({
          payer: client,
          mint,
          treasuryState,
          treasuryAuth,
          treasury: treasury.publicKey,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
          rent: SYSVAR_RENT_PUBKEY,
        })
        .signers([treasury])
        .rpc();
    } catch (e: any) {
      if (
        !String(e).includes("already in use") &&
        !String(e).includes("already been processed")
      ) {
        throw e;
      }
    }

    const computeWorker = await createReadyWorker();
    const badVerifier = await createReadyWorker();
    const goodVerifier1 = await createReadyWorker();
    const goodVerifier2 = await createReadyWorker();
    const { job, escrow } = await createTestJob(1, 2);

    const fragment = await claimAndSubmitFragment(
      computeWorker.keypair,
      computeWorker.workerAccount,
      computeWorker.workerToken,
      job,
      0,
      51,
      52
    );

    const badVote = await voteOnFragment(
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

    const beforeSlash = await program.account.worker.fetch(badVerifier.workerAccount);
    const fragmentResolved = await program.account.fragment.fetch(fragment);
    const roundResolution = roundResolutionPda(fragment, fragmentResolved.round);

    await program.methods
      .slashVote()
      .accounts({
        slasher: client,
        job,
        fragment,
        roundResolution,
        vote: badVote.vote,
        verifierWorker: badVerifier.workerAccount,
        treasuryState,
        stakeAuth: badVerifier.stakeAuth,
        stakeVault: badVerifier.stakeVault,
        treasuryAuth,
        treasury: treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();

    const afterSlash = await program.account.worker.fetch(badVerifier.workerAccount);

    assertComputeUnchanged(beforeSlash, afterSlash);

    assert.isBelow(
      workerRep(afterSlash, "verifyReputation"),
      workerRep(beforeSlash, "verifyReputation")
    );

    assert.isBelow(
      workerRep(afterSlash, "globalReputation"),
      workerRep(beforeSlash, "globalReputation")
    );
  });

  it("a higher verify reputation causes a stronger compute penalty on rejection", async () => {
    const lowVerifier = await createReadyWorker();
    const highVerifier = await createReadyWorker();

    await boostVerifierReputation(highVerifier, 3);

    const highVerifierAfterBoost = await program.account.worker.fetch(
      highVerifier.workerAccount
    );

    assert.isAbove(workerRep(highVerifierAfterBoost, "verifyReputation"), 5000);

    async function rejectedBySecondVerifier(
      secondVerifier: Awaited<ReturnType<typeof createReadyWorker>>,
      resultByte: number
    ) {
      const computeWorker = await createReadyWorker();
      const neutralVerifier = await createReadyWorker();
      const { job, escrow } = await createTestJob(1, 2);
      const before = await program.account.worker.fetch(computeWorker.workerAccount);

      const fragment = await claimAndSubmitFragment(
        computeWorker.keypair,
        computeWorker.workerAccount,
        computeWorker.workerToken,
        job,
        0,
        resultByte,
        resultByte + 1
      );

      await voteOnFragment(
        neutralVerifier.keypair,
        neutralVerifier.workerAccount,
        job,
        fragment,
        escrow,
        computeWorker.workerToken,
        false
      );

      await voteOnFragment(
        secondVerifier.keypair,
        secondVerifier.workerAccount,
        job,
        fragment,
        escrow,
        computeWorker.workerToken,
        false
      );

      const after = await program.account.worker.fetch(computeWorker.workerAccount);

      return workerRep(before, "computeReputation") - workerRep(after, "computeReputation");
    }

    const lowPenalty = await rejectedBySecondVerifier(lowVerifier, 81);
    const highPenalty = await rejectedBySecondVerifier(highVerifier, 91);

    assert.isAbove(
      highPenalty,
      lowPenalty,
      `expected high-reputation verifier penalty (${highPenalty}) to be above low-reputation verifier penalty (${lowPenalty})`
    );
  });
});
