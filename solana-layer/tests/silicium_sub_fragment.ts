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

const program = anchor.workspace.SolanaLayer as Program<any>;

const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);
const VERIFIER_REWARD_BUDGET = new anchor.BN(2_000_000);
const DEFAULT_REWARD_PER_FRAGMENT = new anchor.BN(100_000);
const DEFAULT_FRAGMENT_QUORUM = 2;

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

function resultPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("result"), job.toBuffer()],
    program.programId
  )[0];
}

async function airdrop(pubkey: PublicKey, lamports = 2_000_000_000) {
  const signature = await provider.connection.requestAirdrop(pubkey, lamports);
  await provider.connection.confirmTransaction(signature, "confirmed");
}

function assertAnchorError(error: any, expectedCode: string) {
  const text = String(error);
  if (!text.includes(expectedCode)) {
    console.error("Unexpected Anchor error:", text);
  }
  assert.include(text, expectedCode);
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

  await mintTo(provider.connection, payer, mint, token, authority, amount);
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

async function createRegisteredUnstakedWorker(mint: PublicKey) {
  const keypair = anchor.web3.Keypair.generate();
  await airdrop(keypair.publicKey);
  const workerAccount = await registerWorker(keypair);
  const workerToken = await createWorkerToken(mint, keypair.publicKey);
  return { keypair, workerAccount, workerToken };
}

async function createTestJob(
  mint: PublicKey,
  clientToken: PublicKey,
  jobId: anchor.BN,
  expectedFragments = 1,
  fragmentQuorum = DEFAULT_FRAGMENT_QUORUM,
  rewardPerFragment = DEFAULT_REWARD_PER_FRAGMENT,
  verifierRewardPerVote = VERIFIER_REWARD_PER_VOTE,
  verifierRewardBudget = VERIFIER_REWARD_BUDGET
) {
  const client = provider.wallet.publicKey;
  const payer = provider.wallet.payer as anchor.web3.Keypair;
  const job = jobPda(client, jobId);
  const escrowAuth = escrowAuthPda(job);
  const escrow = anchor.web3.Keypair.generate();
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);

  const topUp = rewardPerFragment
    .mul(new anchor.BN(expectedFragments))
    .add(verifierRewardBudget)
    .add(new anchor.BN(1_000_000));

  await mintTo(
    provider.connection,
    payer,
    mint,
    clientToken,
    client,
    Number(topUp.toString())
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

async function claimVerifierReward(
  verifier: anchor.web3.Keypair,
  verifierWorker: PublicKey,
  verifierToken: PublicKey,
  job: PublicKey,
  fragment: PublicKey,
  escrow: PublicKey
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
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier])
    .rpc();
}

async function verifyFragmentWithTwoVotes(
  computeWorker: Awaited<ReturnType<typeof createReadyWorker>>,
  verifier1: Awaited<ReturnType<typeof createReadyWorker>>,
  verifier2: Awaited<ReturnType<typeof createReadyWorker>>,
  job: PublicKey,
  escrow: PublicKey,
  fragmentIndex: number,
  resultByte: number
): Promise<PublicKey> {
  const fragment = await claimFragment(
    computeWorker.keypair,
    computeWorker.workerAccount,
    computeWorker.workerToken,
    job,
    fragmentIndex
  );

  await submitFragment(
    computeWorker.keypair,
    computeWorker.workerAccount,
    computeWorker.workerToken,
    job,
    fragmentIndex,
    resultByte,
    resultByte + 1
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

  const fragmentAfter = await program.account.fragment.fetch(fragment);
  assert.deepEqual(fragmentAfter.status, { verified: {} });

  return fragment;
}

async function proposeSplit(
  splitter: Awaited<ReturnType<typeof createReadyWorker>>,
  job: PublicKey,
  parentFragment: PublicKey,
  manifestByte = 7,
  childCount = 2
): Promise<PublicKey> {
  const parentBefore = await program.account.fragment.fetch(parentFragment);
  const proposal = splitProposalPda(parentFragment, parentBefore.round);

  await program.methods
    .proposeFragmentSplit(Array(32).fill(manifestByte), childCount)
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

  return proposal;
}

async function approveSplit(job: PublicKey, parentFragment: PublicKey, proposal: PublicKey, approve = true) {
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

async function createSubFragment(
  job: PublicKey,
  parentFragment: PublicKey,
  proposal: PublicKey,
  childIndex: number,
  requiredReputation = 1_500,
  requiredStake = 1,
  complexityScore = 3_000,
  inputByte = 44
): Promise<PublicKey> {
  const child = fragmentPda(job, childIndex);

  await program.methods
    .createSubFragment(
      childIndex,
      new anchor.BN(requiredReputation),
      new anchor.BN(requiredStake),
      complexityScore,
      Array(32).fill(inputByte)
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

async function setupClaimedParent(mint: PublicKey, clientToken: PublicKey, jobIdNumber: number, expectedFragments = 1) {
  const splitter = await createReadyWorker(mint, 1_000_000);
  const { job, escrow } = await createTestJob(
    mint,
    clientToken,
    new anchor.BN(jobIdNumber),
    expectedFragments,
    DEFAULT_FRAGMENT_QUORUM
  );

  const parentFragment = await claimFragment(
    splitter.keypair,
    splitter.workerAccount,
    splitter.workerToken,
    job,
    0
  );

  return { splitter, job, escrow, parentFragment };
}

describe("silicium v2 - complete sub-fragment verification", () => {
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

    await mintTo(provider.connection, payer, mint, clientToken, client, 200_000_000);
  });

  it("rejects split with empty manifest hash", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2000);
    const parent = await program.account.fragment.fetch(parentFragment);
    const proposal = splitProposalPda(parentFragment, parent.round);

    try {
      await program.methods
        .proposeFragmentSplit(Array(32).fill(0), 2)
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
      assert.fail("empty manifest hash should be rejected");
    } catch (e: any) {
      assertAnchorError(e, "InvalidSplitManifest");
    }
  });

  it("rejects split with less than two children", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2001);
    const parent = await program.account.fragment.fetch(parentFragment);
    const proposal = splitProposalPda(parentFragment, parent.round);

    try {
      await program.methods
        .proposeFragmentSplit(Array(32).fill(8), 1)
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
      assert.fail("child_count=1 should be rejected");
    } catch (e: any) {
      assertAnchorError(e, "SplitChildLimitExceeded");
    }
  });

  it("rejects split with too many children", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2002);
    const parent = await program.account.fragment.fetch(parentFragment);
    const proposal = splitProposalPda(parentFragment, parent.round);

    try {
      await program.methods
        .proposeFragmentSplit(Array(32).fill(8), 9)
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
      assert.fail("child_count > MAX_CHILDREN_PER_SPLIT should be rejected");
    } catch (e: any) {
      assertAnchorError(e, "SplitChildLimitExceeded");
    }
  });

  it("rejects split from a worker that did not claim the parent", async () => {
    const { job, parentFragment } = await setupClaimedParent(mint, clientToken, 2003);
    const unauthorizedSplitter = await createReadyWorker(mint, 1_000_000);
    const parent = await program.account.fragment.fetch(parentFragment);
    const proposal = splitProposalPda(parentFragment, parent.round);

    try {
      await program.methods
        .proposeFragmentSplit(Array(32).fill(9), 2)
        .accounts({
          splitter: unauthorizedSplitter.keypair.publicKey,
          splitterWorker: unauthorizedSplitter.workerAccount,
          job,
          parentFragment,
          splitProposal: proposal,
          systemProgram: SystemProgram.programId,
        })
        .signers([unauthorizedSplitter.keypair])
        .rpc();
      assert.fail("non-assigned worker should not split the parent");
    } catch (e: any) {
      assertAnchorError(e, "NotAuthorized");
    }
  });

  it("rejects split from an unstaked worker account", async () => {
    const { job, parentFragment } = await setupClaimedParent(mint, clientToken, 2004);
    const unstaked = await createRegisteredUnstakedWorker(mint);
    const parent = await program.account.fragment.fetch(parentFragment);
    const proposal = splitProposalPda(parentFragment, parent.round);

    try {
      await program.methods
        .proposeFragmentSplit(Array(32).fill(9), 2)
        .accounts({
          splitter: unstaked.keypair.publicKey,
          splitterWorker: unstaked.workerAccount,
          job,
          parentFragment,
          splitProposal: proposal,
          systemProgram: SystemProgram.programId,
        })
        .signers([unstaked.keypair])
        .rpc();
      assert.fail("unstaked worker should not propose split");
    } catch (e: any) {
      assertAnchorError(e, "StakeTooLow");
    }
  });

  it("rejects creating sub-fragments before split approval", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2005);
    const proposal = await proposeSplit(splitter, job, parentFragment, 10, 2);

    try {
      await createSubFragment(job, parentFragment, proposal, 1);
      assert.fail("create_sub_fragment should require approved split");
    } catch (e: any) {
      assertAnchorError(e, "SplitNotApproved");
    }
  });

  it("rejects approving the same split twice", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2006);
    const proposal = await proposeSplit(splitter, job, parentFragment, 11, 2);
    await approveSplit(job, parentFragment, proposal, true);

    try {
      await approveSplit(job, parentFragment, proposal, true);
      assert.fail("second approval should be rejected");
    } catch (e: any) {
      const text = String(e);
      assert.isTrue(
        text.includes("BadFragmentState") || text.includes("SplitAlreadyResolved"),
        `unexpected error: ${text}`
      );
    }
  });

  it("rejects creating more children than declared", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2007);
    const proposal = await proposeSplit(splitter, job, parentFragment, 12, 2);
    await approveSplit(job, parentFragment, proposal, true);

    await createSubFragment(job, parentFragment, proposal, 1, 1_500, 1, 3_001, 51);
    await createSubFragment(job, parentFragment, proposal, 2, 1_500, 1, 3_002, 52);

    const parentAfterTwo = await program.account.fragment.fetch(parentFragment);
    assert.deepEqual(parentAfterTwo.status, { splitParent: {} });

    try {
      await createSubFragment(job, parentFragment, proposal, 3, 1_500, 1, 3_003, 53);
      assert.fail("third child should be rejected when child_count=2");
    } catch (e: any) {
      const text = String(e);
      assert.isTrue(
        text.includes("ParentNotSplitApproved") || text.includes("SplitChildLimitExceeded"),
        `unexpected error: ${text}`
      );
    }
  });

  it("rejects claiming a child whose required reputation is too high", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2008);
    const lowRepWorker = await createReadyWorker(mint, 1_000_000);
    const proposal = await proposeSplit(splitter, job, parentFragment, 13, 2);
    await approveSplit(job, parentFragment, proposal, true);

    const highRepChildIndex = 1;
    await createSubFragment(job, parentFragment, proposal, highRepChildIndex, 9_001, 1, 4_000, 61);
    await createSubFragment(job, parentFragment, proposal, 2, 1_500, 1, 4_001, 62);

    try {
      await claimFragment(
        lowRepWorker.keypair,
        lowRepWorker.workerAccount,
        lowRepWorker.workerToken,
        job,
        highRepChildIndex
      );
      assert.fail("worker with reputation 5000 should not claim child requiring 9001");
    } catch (e: any) {
      assertAnchorError(e, "ReputationTooLow");
    }
  });

  it("rejects claiming a split parent directly", async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2009);
    const otherWorker = await createReadyWorker(mint, 1_000_000);
    const proposal = await proposeSplit(splitter, job, parentFragment, 14, 2);
    await approveSplit(job, parentFragment, proposal, true);
    await createSubFragment(job, parentFragment, proposal, 1, 1_500, 1, 3_001, 71);
    await createSubFragment(job, parentFragment, proposal, 2, 1_500, 1, 3_002, 72);

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
      assert.fail("split parent should not be claimable");
    } catch (e: any) {
      assertAnchorError(e, "BadFragmentState");
    }
  });

  it("finalizes a mixed V1/V2 job after all leaf fragments and verifier rewards are complete", async () => {
    const splitter = await createReadyWorker(mint, 1_000_000);
    const computeWorker = await createReadyWorker(mint, 1_000_000);
    const verifier1 = await createReadyWorker(mint, 1_000_000);
    const verifier2 = await createReadyWorker(mint, 1_000_000);

    const { job, escrow } = await createTestJob(
      mint,
      clientToken,
      new anchor.BN(2010),
      2,
      DEFAULT_FRAGMENT_QUORUM,
      DEFAULT_REWARD_PER_FRAGMENT,
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

    const proposal = await proposeSplit(splitter, job, parentFragment, 15, 2);
    await approveSplit(job, parentFragment, proposal, true);

    const child2 = await createSubFragment(job, parentFragment, proposal, 2, 1_500, 1, 3_002, 82);
    const child3 = await createSubFragment(job, parentFragment, proposal, 3, 1_500, 1, 3_003, 83);

    const parentAfterSplit = await program.account.fragment.fetch(parentFragment);
    const jobAfterSplit = await program.account.job.fetch(job);
    assert.deepEqual(parentAfterSplit.status, { splitParent: {} });
    assert.equal(jobAfterSplit.expectedFragments, 3);
    assert.equal(jobAfterSplit.verifiedFragments, 0);

    const normalLeaf = await verifyFragmentWithTwoVotes(
      computeWorker,
      verifier1,
      verifier2,
      job,
      escrow,
      1,
      91
    );

    await verifyFragmentWithTwoVotes(
      computeWorker,
      verifier1,
      verifier2,
      job,
      escrow,
      2,
      92
    );

    await verifyFragmentWithTwoVotes(
      computeWorker,
      verifier1,
      verifier2,
      job,
      escrow,
      3,
      93
    );

    const jobBeforeRewards = await program.account.job.fetch(job);
    assert.equal(jobBeforeRewards.verifiedFragments, 3);
    assert.equal(jobBeforeRewards.expectedFragments, 3);
    assert.deepEqual(jobBeforeRewards.status, { open: {} });

    try {
      await program.methods
        .finalizeJob(Array(32).fill(99), Buffer.from("ipfs://should-fail-before-rewards"))
        .accounts({
          client: provider.wallet.publicKey,
          job,
          result: resultPda(job),
          escrowAuth: escrowAuthPda(job),
          escrow,
          clientToken,
          tokenProgram: TOKEN_PROGRAM_ID,
          systemProgram: SystemProgram.programId,
        })
        .rpc();
      assert.fail("finalization should fail while verifier rewards are unclaimed");
    } catch (e: any) {
      assertAnchorError(e, "OutstandingVerifierClaims");
    }

    for (const fragment of [normalLeaf, child2, child3]) {
      await claimVerifierReward(
        verifier1.keypair,
        verifier1.workerAccount,
        verifier1.workerToken,
        job,
        fragment,
        escrow
      );
      await claimVerifierReward(
        verifier2.keypair,
        verifier2.workerAccount,
        verifier2.workerToken,
        job,
        fragment,
        escrow
      );
    }

    await program.methods
      .finalizeJob(Array(32).fill(100), Buffer.from("ipfs://mixed-v2-final-result"))
      .accounts({
        client: provider.wallet.publicKey,
        job,
        result: resultPda(job),
        escrowAuth: escrowAuthPda(job),
        escrow,
        clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const finalizedJob = await program.account.job.fetch(job);
    const result = await program.account.jobResult.fetch(resultPda(job));

    assert.deepEqual(finalizedJob.status, { finalized: {} });
    assert.equal(finalizedJob.verifiedFragments, 3);
    assert.equal(finalizedJob.expectedFragments, 3);
    assert.deepEqual(result.finalHash, Array(32).fill(100));
  });
});
