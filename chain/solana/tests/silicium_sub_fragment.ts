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

import {
  provider,
  program,
  VERIFIER_REWARD_PER_VOTE,
  DEFAULT_REWARD_PER_FRAGMENT,
  DEFAULT_FRAGMENT_QUORUM,
  u32le,
  u16le,
  jobPda,
  escrowAuthPda,
  fragmentPda,
  splitProposalPda,
  workerPda,
  workerPayoutPda,
  stakeAuthPda,
  stakeVaultPda,
  votePda,
  roundResolutionPda,
  maxLeafFragments,
  minimumVerifierRewardBudget,
  resultPda,
  airdrop,
  assertAnchorError,
  registerWorker,
  createWorkerToken,
  stakeRegisteredWorker,
  createReadyWorker,
  createRegisteredUnstakedWorker,
  createTestJob,
  claimFragment,
  submitFragment,
  voteOnFragment,
  claimVerifierReward,
  verifyFragmentWithTwoVotes,
  proposeSplit,
  approveSplit,
  createSubFragment,
  setupClaimedParent,
} from './support/split-fixtures';

describe('silicium v2 - complete sub-fragment verification', () => {
  let mint: PublicKey;
  let clientToken: PublicKey;

  before(async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    mint = await createMint(provider.connection, payer, client, null, 6);
    clientToken = await createAssociatedTokenAccount(provider.connection, payer, mint, client);

    await mintTo(provider.connection, payer, mint, clientToken, client, 200_000_000);
  });

  it('rejects split with empty manifest hash', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2000);
    const parent = await program.account.fragment.fetch(parentFragment);
    const jobAccount = await program.account.job.fetch(job);
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
          escrow: jobAccount.escrow,
          systemProgram: SystemProgram.programId,
        })
        .signers([splitter.keypair])
        .rpc();
      assert.fail('empty manifest hash should be rejected');
    } catch (e: any) {
      assertAnchorError(e, 'InvalidSplitManifest');
    }
  });

  it('rejects split with less than two children', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2001);
    const parent = await program.account.fragment.fetch(parentFragment);
    const jobAccount = await program.account.job.fetch(job);
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
          escrow: jobAccount.escrow,
          systemProgram: SystemProgram.programId,
        })
        .signers([splitter.keypair])
        .rpc();
      assert.fail('child_count=1 should be rejected');
    } catch (e: any) {
      assertAnchorError(e, 'SplitChildLimitExceeded');
    }
  });

  it('rejects split with too many children', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2002);
    const parent = await program.account.fragment.fetch(parentFragment);
    const jobAccount = await program.account.job.fetch(job);
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
          escrow: jobAccount.escrow,
          systemProgram: SystemProgram.programId,
        })
        .signers([splitter.keypair])
        .rpc();
      assert.fail('child_count > MAX_CHILDREN_PER_SPLIT should be rejected');
    } catch (e: any) {
      assertAnchorError(e, 'SplitChildLimitExceeded');
    }
  });

  it('rejects split from a worker that did not claim the parent', async () => {
    const { job, parentFragment } = await setupClaimedParent(mint, clientToken, 2003);
    const unauthorizedSplitter = await createReadyWorker(mint, 1_000_000);
    const parent = await program.account.fragment.fetch(parentFragment);
    const jobAccount = await program.account.job.fetch(job);
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
          escrow: jobAccount.escrow,
          systemProgram: SystemProgram.programId,
        })
        .signers([unauthorizedSplitter.keypair])
        .rpc();
      assert.fail('non-assigned worker should not split the parent');
    } catch (e: any) {
      assertAnchorError(e, 'NotAuthorized');
    }
  });

  it('does not let an unstaked worker split a parent claimed by another worker', async () => {
    const { job, parentFragment } = await setupClaimedParent(mint, clientToken, 2004);
    const unstaked = await createRegisteredUnstakedWorker(mint);
    const parent = await program.account.fragment.fetch(parentFragment);
    const jobAccount = await program.account.job.fetch(job);
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
          escrow: jobAccount.escrow,
          systemProgram: SystemProgram.programId,
        })
        .signers([unstaked.keypair])
        .rpc();
      assert.fail('unstaked worker should not propose split');
    } catch (e: any) {
      assertAnchorError(e, 'NotAuthorized');
    }
  });

  it('auto-approves a qualifying split for peer-to-peer delegation', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2005);
    const proposal = await proposeSplit(splitter, job, parentFragment, 10, 2);
    const proposalState = await program.account.splitProposal.fetch(proposal);
    const parentAfterProposal = await program.account.fragment.fetch(parentFragment);
    assert.isTrue(proposalState.approved);
    assert.deepEqual(parentAfterProposal.status, { splitApproved: {} });
  });

  it('keeps legacy approval calls idempotent after network auto-approval', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2006);
    const proposal = await proposeSplit(splitter, job, parentFragment, 11, 2);
    await approveSplit(job, parentFragment, proposal, true);
    await approveSplit(job, parentFragment, proposal, true);
  });

  it('rejects an index outside the parent subtree without changing the proposal', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 2007);
    const proposal = await proposeSplit(splitter, job, parentFragment, 12, 2);
    await approveSplit(job, parentFragment, proposal, true);
    await createSubFragment(job, parentFragment, proposal, 1, 1_500, 1, 3_001, 51);
    const before = await program.account.splitProposal.fetch(proposal);
    try {
      await createSubFragment(job, parentFragment, proposal, 3, 1_500, 1, 3_003, 53);
      assert.fail("index 3 is outside parent 0's direct children");
    } catch (e: any) {
      assertAnchorError(e, 'InvalidChildFragmentIndex');
    }
    const after = await program.account.splitProposal.fetch(proposal);
    assert.equal(after.createdChildren, before.createdChildren);
  });

  it('seals the parent after exactly the declared number of children', async () => {
    const { splitter, job, parentFragment } = await setupClaimedParent(mint, clientToken, 20070);
    const proposal = await proposeSplit(splitter, job, parentFragment, 120, 2);
    await approveSplit(job, parentFragment, proposal, true);
    await createSubFragment(job, parentFragment, proposal, 1, 1_500, 1, 3_001, 51);
    const halfway = await program.account.fragment.fetch(parentFragment);
    const one = await program.account.splitProposal.fetch(proposal);
    assert.deepEqual(halfway.status, { splitApproved: {} });
    assert.equal(one.createdChildren, 1);
    await createSubFragment(job, parentFragment, proposal, 2, 1_500, 1, 3_002, 52);
    const parent = await program.account.fragment.fetch(parentFragment);
    const complete = await program.account.splitProposal.fetch(proposal);
    assert.deepEqual(parent.status, { splitParent: {} });
    assert.equal(complete.createdChildren, complete.childCount);
    assert.equal(complete.createdChildren, 2);
  });

  it('rejects claiming a child whose required reputation is too high', async () => {
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
        highRepChildIndex,
      );
      assert.fail('worker with reputation 5000 should not claim child requiring 9001');
    } catch (e: any) {
      assertAnchorError(e, 'ReputationTooLow');
    }
  });

  it('rejects claiming a split parent directly', async () => {
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
      assert.fail('split parent should not be claimable');
    } catch (e: any) {
      assertAnchorError(e, 'BadFragmentState');
    }
  });

  it('finalizes a mixed V1/V2 job after all leaf fragments and verifier rewards are complete', async () => {
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
      minimumVerifierRewardBudget(2, DEFAULT_FRAGMENT_QUORUM),
    );

    const parentFragment = await claimFragment(
      splitter.keypair,
      splitter.workerAccount,
      splitter.workerToken,
      job,
      0,
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
      91,
    );

    await verifyFragmentWithTwoVotes(computeWorker, verifier1, verifier2, job, escrow, 2, 92);

    await verifyFragmentWithTwoVotes(computeWorker, verifier1, verifier2, job, escrow, 3, 93);

    const jobBeforeRewards = await program.account.job.fetch(job);
    assert.equal(jobBeforeRewards.verifiedFragments, 3);
    assert.equal(jobBeforeRewards.expectedFragments, 3);
    assert.deepEqual(jobBeforeRewards.status, { open: {} });

    try {
      await program.methods
        .finalizeJob(Array(32).fill(99), Buffer.from('ipfs://should-fail-before-rewards'))
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
      assert.fail('finalization should fail while verifier rewards are unclaimed');
    } catch (e: any) {
      assertAnchorError(e, 'OutstandingVerifierClaims');
    }

    for (const fragment of [normalLeaf, child2, child3]) {
      await claimVerifierReward(
        verifier1.keypair,
        verifier1.workerAccount,
        verifier1.workerToken,
        job,
        fragment,
        escrow,
      );
      await claimVerifierReward(
        verifier2.keypair,
        verifier2.workerAccount,
        verifier2.workerToken,
        job,
        fragment,
        escrow,
      );
    }

    await program.methods
      .finalizeJob(Array(32).fill(100), Buffer.from('ipfs://mixed-v2-final-result'))
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
