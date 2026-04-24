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

let slashJobId = new anchor.BN(4);

describe("silicium", () => {
  it("registers a worker", async () => {
    const worker = provider.wallet.publicKey;

    const [workerAccount] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), worker.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker,
        workerAccount,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const account = await program.account.worker.fetch(workerAccount);
    assert.equal(account.owner.toBase58(), worker.toBase58());
  });

  it("stakes SPL tokens for a worker", async () => {
    const worker = provider.wallet.publicKey;

    const [workerAccount] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), worker.toBuffer()],
      program.programId
    );

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

    const [stakeAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), workerAccount.toBuffer()],
      program.programId
    );

    const [stakeVault] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), worker.toBuffer()],
      program.programId
    );

    const amount = new anchor.BN(1_000_000);

    await program.methods
      .stakeWorker(amount)
      .accounts({
        worker,
        workerAccount,
        mint,
        workerToken,
        stakeAuth,
        stakeVault,
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

    const mint = sharedMint;
    const clientToken = sharedWorkerToken;

    await mintTo(
      provider.connection,
      payer,
      mint,
      clientToken,
      client,
      10_000_000
    );

    const [job] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const [escrowAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), job.toBuffer()],
      program.programId
    );

    const escrow = anchor.web3.Keypair.generate();
    sharedEscrow = escrow.publicKey;

    await program.methods
      .createJob(jobId, expectedFragments, rewardPerFragment, deadlineUnix, fragmentQuorum)
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

    const jobAccount = await program.account.job.fetch(job);

    assert.equal(jobAccount.jobId.toString(), jobId.toString());
    assert.equal(jobAccount.client.toBase58(), client.toBase58());
    assert.equal(jobAccount.mint.toBase58(), mint.toBase58());
    assert.equal(jobAccount.escrow.toBase58(), escrow.publicKey.toBase58());
    assert.equal(jobAccount.expectedFragments, expectedFragments);
    assert.equal(jobAccount.verifiedFragments, 0);
    assert.equal(jobAccount.rewardPerFragment.toString(), rewardPerFragment.toString());
    assert.equal(jobAccount.depositedAmount.toString(), "3000000");
    assert.equal(jobAccount.paidAmount.toString(), "0");
    assert.equal(jobAccount.fragmentQuorum, fragmentQuorum);
    assert.isAbove(Number(jobAccount.createdAtUnix.toString()), 0);
    assert.deepEqual(jobAccount.status, { open: {} });
  });

  it("submits a fragment result", async () => {
    const worker = provider.wallet.publicKey;
    const jobId = new anchor.BN(1);

    const [workerAccount] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), worker.toBuffer()],
      program.programId
    );

    const [job] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), worker.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const fragmentIndex = 0;

    const [fragment] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment"),
        job.toBuffer(),
        Buffer.from(new Uint8Array(new Uint32Array([fragmentIndex]).buffer)),
      ],
      program.programId
    );

    const workerToken = sharedWorkerToken;
    const resultHash = Array(32).fill(1);
    const proofRef = Array(32).fill(2);

    await program.methods
      .submitFragmentResult(fragmentIndex, resultHash, proofRef)
      .accounts({
        worker,
        workerAccount,
        job,
        fragment,
        workerToken,
        systemProgram: SystemProgram.programId,
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

    await provider.connection.requestAirdrop(verifierKeypair.publicKey, 2_000_000_000);
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const [verifierWorker] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifierKeypair.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: verifierKeypair.publicKey,
        workerAccount: verifierWorker,
        systemProgram: SystemProgram.programId,
      })
      .signers([verifierKeypair])
      .rpc();

    const verifierToken = await createAssociatedTokenAccount(
      provider.connection,
      provider.wallet.payer as anchor.web3.Keypair,
      sharedMint,
      verifierKeypair.publicKey
    );

    await mintTo(
      provider.connection,
      provider.wallet.payer as anchor.web3.Keypair,
      sharedMint,
      verifierToken,
      provider.wallet.publicKey,
      10_000_000
    );

    const [stakeAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), verifierWorker.toBuffer()],
      program.programId
    );

    const [stakeVault] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), verifierKeypair.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: verifierKeypair.publicKey,
        workerAccount: verifierWorker,
        mint: sharedMint,
        workerToken: verifierToken,
        stakeAuth,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([verifierKeypair])
      .rpc();

    const verifierAccount = await program.account.worker.fetch(verifierWorker);
    assert.equal(verifierAccount.stakeAmount.toString(), "1000000");
  });

  it("votes yes on a fragment and verifies it", async () => {
    const client = provider.wallet.publicKey;
    const jobId = new anchor.BN(1);
    const fragmentIndex = 0;

    const [job] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const [fragment] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment"),
        job.toBuffer(),
        Buffer.from(new Uint8Array(new Uint32Array([fragmentIndex]).buffer)),
      ],
      program.programId
    );

    const [verifierWorker] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifierKeypair.publicKey.toBuffer()],
      program.programId
    );

    const fragmentAccountBefore = await program.account.fragment.fetch(fragment);

    const roundBuffer = Buffer.alloc(2);
    roundBuffer.writeUInt16LE(fragmentAccountBefore.round, 0);

    const [vote] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        fragment.toBuffer(),
        verifierKeypair.publicKey.toBuffer(),
        roundBuffer,
      ],
      program.programId
    );

    const [escrowAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), job.toBuffer()],
      program.programId
    );

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: verifierKeypair.publicKey,
        job,
        fragment,
        verifierWorker,
        vote,
        escrowAuth,
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
    assert.equal(voteAccount.verifier.toBase58(), verifierKeypair.publicKey.toBase58());

    assert.equal(fragmentAccount.yesVotes, 1);
    assert.deepEqual(fragmentAccount.status, { submitted: {} });

    assert.equal(jobAccount.verifiedFragments, 0);
    assert.equal(verifierAccount.totalVerified, 0);
  });

  it("reaches quorum and pays worker", async () => {
    const client = provider.wallet.publicKey;
    const jobId = new anchor.BN(1);
    const fragmentIndex = 0;

    const verifier2 = anchor.web3.Keypair.generate();

    await provider.connection.requestAirdrop(verifier2.publicKey, 2_000_000_000);
    await new Promise((r) => setTimeout(r, 1000));

    const [verifierWorker2] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: verifier2.publicKey,
        workerAccount: verifierWorker2,
        systemProgram: SystemProgram.programId,
      })
      .signers([verifier2])
      .rpc();

    const verifierToken2 = await createAssociatedTokenAccount(
      provider.connection,
      provider.wallet.payer as anchor.web3.Keypair,
      sharedMint,
      verifier2.publicKey
    );

    await mintTo(
      provider.connection,
      provider.wallet.payer as anchor.web3.Keypair,
      sharedMint,
      verifierToken2,
      provider.wallet.publicKey,
      10_000_000
    );

    const [stakeAuth2] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), verifierWorker2.toBuffer()],
      program.programId
    );

    const [stakeVault2] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), verifier2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: verifier2.publicKey,
        workerAccount: verifierWorker2,
        mint: sharedMint,
        workerToken: verifierToken2,
        stakeAuth: stakeAuth2,
        stakeVault: stakeVault2,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([verifier2])
      .rpc();

    const [job] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const indexBuffer = Buffer.alloc(4);
    indexBuffer.writeUInt32LE(fragmentIndex, 0);

    const [fragment] = PublicKey.findProgramAddressSync(
      [Buffer.from("fragment"), job.toBuffer(), indexBuffer],
      program.programId
    );

    const fragmentBefore = await program.account.fragment.fetch(fragment);

    const roundBuffer = Buffer.alloc(2);
    roundBuffer.writeUInt16LE(fragmentBefore.round, 0);

    const [vote2] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        fragment.toBuffer(),
        verifier2.publicKey.toBuffer(),
        roundBuffer,
      ],
      program.programId
    );

    const [escrowAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), job.toBuffer()],
      program.programId
    );

    const workerTokenBefore = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: verifier2.publicKey,
        job,
        fragment,
        verifierWorker: verifierWorker2,
        vote: vote2,
        escrowAuth,
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

    const clientToken = sharedWorkerToken;

    [rejectedJob] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), rejectedJobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const [escrowAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), rejectedJob.toBuffer()],
      program.programId
    );

    const escrow = anchor.web3.Keypair.generate();
    rejectedEscrow = escrow.publicKey;

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      clientToken,
      client,
      2_000_000
    );

    await program.methods
      .createJob(
        rejectedJobId,
        expectedFragments,
        rewardPerFragment,
        deadlineUnix,
        fragmentQuorum
      )
      .accounts({
        client,
        mint: sharedMint,
        job: rejectedJob,
        escrowAuth,
        escrow: rejectedEscrow,
        clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    const fragmentIndex = 0;
    const indexBuffer = Buffer.alloc(4);
    indexBuffer.writeUInt32LE(fragmentIndex, 0);

    [rejectedFragment] = PublicKey.findProgramAddressSync(
      [Buffer.from("fragment"), rejectedJob.toBuffer(), indexBuffer],
      program.programId
    );

    await program.methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(7), Array(32).fill(8))
      .accounts({
        worker: client,
        workerAccount: PublicKey.findProgramAddressSync(
          [Buffer.from("worker"), client.toBuffer()],
          program.programId
        )[0],
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const rejectVerifier1 = anchor.web3.Keypair.generate();

    await provider.connection.requestAirdrop(rejectVerifier1.publicKey, 2_000_000_000);
    await new Promise((r) => setTimeout(r, 1000));

    const [rejectVerifierWorker1] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), rejectVerifier1.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: rejectVerifier1.publicKey,
        workerAccount: rejectVerifierWorker1,
        systemProgram: SystemProgram.programId,
      })
      .signers([rejectVerifier1])
      .rpc();

    const rejectVerifierToken1 = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      sharedMint,
      rejectVerifier1.publicKey
    );

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      rejectVerifierToken1,
      client,
      10_000_000
    );

    const [stakeAuth1] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), rejectVerifierWorker1.toBuffer()],
      program.programId
    );

    const [stakeVault1] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), rejectVerifier1.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: rejectVerifier1.publicKey,
        workerAccount: rejectVerifierWorker1,
        mint: sharedMint,
        workerToken: rejectVerifierToken1,
        stakeAuth: stakeAuth1,
        stakeVault: stakeVault1,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([rejectVerifier1])
      .rpc();

    const rejectVerifier2 = anchor.web3.Keypair.generate();

    await provider.connection.requestAirdrop(rejectVerifier2.publicKey, 2_000_000_000);
    await new Promise((r) => setTimeout(r, 1000));

    const [rejectVerifierWorker2] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), rejectVerifier2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: rejectVerifier2.publicKey,
        workerAccount: rejectVerifierWorker2,
        systemProgram: SystemProgram.programId,
      })
      .signers([rejectVerifier2])
      .rpc();

    const rejectVerifierToken2 = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      sharedMint,
      rejectVerifier2.publicKey
    );

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      rejectVerifierToken2,
      client,
      10_000_000
    );

    const [stakeAuth2] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), rejectVerifierWorker2.toBuffer()],
      program.programId
    );

    const [stakeVault2] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), rejectVerifier2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: rejectVerifier2.publicKey,
        workerAccount: rejectVerifierWorker2,
        mint: sharedMint,
        workerToken: rejectVerifierToken2,
        stakeAuth: stakeAuth2,
        stakeVault: stakeVault2,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([rejectVerifier2])
      .rpc();

    const fragmentBefore = await program.account.fragment.fetch(rejectedFragment);

    const roundBuffer = Buffer.alloc(2);
    roundBuffer.writeUInt16LE(fragmentBefore.round, 0);

    const [vote1] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        rejectedFragment.toBuffer(),
        rejectVerifier1.publicKey.toBuffer(),
        roundBuffer,
      ],
      program.programId
    );

    const [vote2] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        rejectedFragment.toBuffer(),
        rejectVerifier2.publicKey.toBuffer(),
        roundBuffer,
      ],
      program.programId
    );

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: rejectVerifier1.publicKey,
        job: rejectedJob,
        fragment: rejectedFragment,
        verifierWorker: rejectVerifierWorker1,
        vote: vote1,
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
        escrowAuth,
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

  it("resubmits a rejected fragment", async () => {
    const worker = provider.wallet.publicKey;
    const fragmentIndex = 0;

    const [workerAccount] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), worker.toBuffer()],
      program.programId
    );

    const before = await program.account.fragment.fetch(rejectedFragment);

    await program.methods
      .resubmitFragmentResult(fragmentIndex, Array(32).fill(9), Array(32).fill(10))
      .accounts({
        worker,
        workerAccount,
        job: rejectedJob,
        fragment: rejectedFragment,
        workerToken: sharedWorkerToken,
      })
      .rpc();

    const after = await program.account.fragment.fetch(rejectedFragment);
    const workerAfter = await program.account.worker.fetch(workerAccount);

    assert.equal(after.round, before.round + 1);
    assert.equal(after.yesVotes, 0);
    assert.equal(after.noVotes, 0);
    assert.deepEqual(after.status, { submitted: {} });
    assert.deepEqual(after.resultHash, Array(32).fill(9));
    assert.deepEqual(after.proofRef, Array(32).fill(10));
    assert.equal(workerAfter.totalSubmitted, 3);
  });

  it("creates, verifies, and finalizes a job", async () => {
    const client = provider.wallet.publicKey;
    const payer = provider.wallet.payer as anchor.web3.Keypair;

    const expectedFragments = 2;
    const rewardPerFragment = new anchor.BN(1_000_000);
    const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
    const fragmentQuorum = 2;

    [finalizeJob] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), finalizeJobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const [escrowAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), finalizeJob.toBuffer()],
      program.programId
    );

    const escrow = anchor.web3.Keypair.generate();
    finalizeEscrow = escrow.publicKey;

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      2_000_000
    );

    await program.methods
      .createJob(
        finalizeJobId,
        expectedFragments,
        rewardPerFragment,
        deadlineUnix,
        fragmentQuorum
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

    const [workerAccount] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), client.toBuffer()],
      program.programId
    );

    const submitAndVerifyFragment = async (fragmentIndex: number) => {
      const indexBuffer = Buffer.alloc(4);
      indexBuffer.writeUInt32LE(fragmentIndex, 0);

      const [fragment] = PublicKey.findProgramAddressSync(
        [Buffer.from("fragment"), finalizeJob.toBuffer(), indexBuffer],
        program.programId
      );

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

      const voteYesWithNewVerifier = async () => {
        const verifier = anchor.web3.Keypair.generate();

        await provider.connection.requestAirdrop(verifier.publicKey, 2_000_000_000);
        await new Promise((r) => setTimeout(r, 1000));

        const [verifierWorker] = PublicKey.findProgramAddressSync(
          [Buffer.from("worker"), verifier.publicKey.toBuffer()],
          program.programId
        );

        await program.methods
          .registerWorker()
          .accounts({
            worker: verifier.publicKey,
            workerAccount: verifierWorker,
            systemProgram: SystemProgram.programId,
          })
          .signers([verifier])
          .rpc();

        const verifierToken = await createAssociatedTokenAccount(
          provider.connection,
          payer,
          sharedMint,
          verifier.publicKey
        );

        await mintTo(
          provider.connection,
          payer,
          sharedMint,
          verifierToken,
          client,
          10_000_000
        );

        const [stakeAuth] = PublicKey.findProgramAddressSync(
          [Buffer.from("stake_auth"), verifierWorker.toBuffer()],
          program.programId
        );

        const [stakeVault] = PublicKey.findProgramAddressSync(
          [Buffer.from("stake_vault"), verifier.publicKey.toBuffer()],
          program.programId
        );

        await program.methods
          .stakeWorker(new anchor.BN(1_000_000))
          .accounts({
            worker: verifier.publicKey,
            workerAccount: verifierWorker,
            mint: sharedMint,
            workerToken: verifierToken,
            stakeAuth,
            stakeVault,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
            rent: SYSVAR_RENT_PUBKEY,
          })
          .signers([verifier])
          .rpc();

        const fragmentBefore = await program.account.fragment.fetch(fragment);

        const roundBuffer = Buffer.alloc(2);
        roundBuffer.writeUInt16LE(fragmentBefore.round, 0);

        const [vote] = PublicKey.findProgramAddressSync(
          [
            Buffer.from("fragment_vote"),
            fragment.toBuffer(),
            verifier.publicKey.toBuffer(),
            roundBuffer,
          ],
          program.programId
        );

        await program.methods
          .voteFragment(true)
          .accounts({
            verifier: verifier.publicKey,
            job: finalizeJob,
            fragment,
            verifierWorker,
            vote,
            escrowAuth,
            escrow: finalizeEscrow,
            workerToken: sharedWorkerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
          })
          .signers([verifier])
          .rpc();
      };

      await voteYesWithNewVerifier();
      await voteYesWithNewVerifier();

      const fragmentAfter = await program.account.fragment.fetch(fragment);
      assert.deepEqual(fragmentAfter.status, { verified: {} });
    };

    await submitAndVerifyFragment(0);
    await submitAndVerifyFragment(1);

    const jobAfterVotes = await program.account.job.fetch(finalizeJob);
    assert.equal(jobAfterVotes.verifiedFragments, 2);

    const [result] = PublicKey.findProgramAddressSync(
      [Buffer.from("result"), finalizeJob.toBuffer()],
      program.programId
    );

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
        treasuryState,
        treasuryAuth,
        treasury: treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([treasury])
      .rpc();

    const [job] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), slashJobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const [escrowAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), job.toBuffer()],
      program.programId
    );

    const escrow = anchor.web3.Keypair.generate();

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      sharedWorkerToken,
      client,
      2_000_000
    );

    await program.methods
      .createJob(
        slashJobId,
        2,
        new anchor.BN(1_000_000),
        new anchor.BN(Math.floor(Date.now() / 1000) + 3600),
        2
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

    const indexBuffer = Buffer.alloc(4);
    indexBuffer.writeUInt32LE(fragmentIndex, 0);

    const [fragment] = PublicKey.findProgramAddressSync(
      [Buffer.from("fragment"), job.toBuffer(), indexBuffer],
      program.programId
    );

    const [workerAccount] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), client.toBuffer()],
      program.programId
    );

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

    await provider.connection.requestAirdrop(badVerifier.publicKey, 2_000_000_000);
    await new Promise((r) => setTimeout(r, 1000));

    const [badVerifierWorker] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), badVerifier.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: badVerifier.publicKey,
        workerAccount: badVerifierWorker,
        systemProgram: SystemProgram.programId,
      })
      .signers([badVerifier])
      .rpc();

    const badVerifierToken = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      sharedMint,
      badVerifier.publicKey
    );

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      badVerifierToken,
      client,
      10_000_000
    );

    const [stakeAuth] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), badVerifierWorker.toBuffer()],
      program.programId
    );

    const [stakeVault] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), badVerifier.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: badVerifier.publicKey,
        workerAccount: badVerifierWorker,
        mint: sharedMint,
        workerToken: badVerifierToken,
        stakeAuth,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([badVerifier])
      .rpc();

    const fragmentBefore = await program.account.fragment.fetch(fragment);
    const roundBuffer = Buffer.alloc(2);
    roundBuffer.writeUInt16LE(fragmentBefore.round, 0);

    const [badVote] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        fragment.toBuffer(),
        badVerifier.publicKey.toBuffer(),
        roundBuffer,
      ],
      program.programId
    );

    await program.methods
      .voteFragment(false)
      .accounts({
        verifier: badVerifier.publicKey,
        job,
        fragment,
        verifierWorker: badVerifierWorker,
        vote: badVote,
        escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([badVerifier])
      .rpc();

    const goodVerifier1 = anchor.web3.Keypair.generate();
    await provider.connection.requestAirdrop(goodVerifier1.publicKey, 2_000_000_000);
    await new Promise((r) => setTimeout(r, 1000));

    const [goodVerifierWorker1] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), goodVerifier1.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: goodVerifier1.publicKey,
        workerAccount: goodVerifierWorker1,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier1])
      .rpc();

    const goodVerifierToken1 = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      sharedMint,
      goodVerifier1.publicKey
    );

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      goodVerifierToken1,
      client,
      10_000_000
    );

    const [goodStakeAuth1] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), goodVerifierWorker1.toBuffer()],
      program.programId
    );

    const [goodStakeVault1] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), goodVerifier1.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: goodVerifier1.publicKey,
        workerAccount: goodVerifierWorker1,
        mint: sharedMint,
        workerToken: goodVerifierToken1,
        stakeAuth: goodStakeAuth1,
        stakeVault: goodStakeVault1,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([goodVerifier1])
      .rpc();

    let fragmentState = await program.account.fragment.fetch(fragment);
    let roundBufferYes1 = Buffer.alloc(2);
    roundBufferYes1.writeUInt16LE(fragmentState.round, 0);

    const [goodVote1] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        fragment.toBuffer(),
        goodVerifier1.publicKey.toBuffer(),
        roundBufferYes1,
      ],
      program.programId
    );

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: goodVerifier1.publicKey,
        job,
        fragment,
        verifierWorker: goodVerifierWorker1,
        vote: goodVote1,
        escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier1])
      .rpc();

    const goodVerifier2 = anchor.web3.Keypair.generate();
    await provider.connection.requestAirdrop(goodVerifier2.publicKey, 2_000_000_000);
    await new Promise((r) => setTimeout(r, 1000));

    const [goodVerifierWorker2] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), goodVerifier2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .registerWorker()
      .accounts({
        worker: goodVerifier2.publicKey,
        workerAccount: goodVerifierWorker2,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier2])
      .rpc();

    const goodVerifierToken2 = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      sharedMint,
      goodVerifier2.publicKey
    );

    await mintTo(
      provider.connection,
      payer,
      sharedMint,
      goodVerifierToken2,
      client,
      10_000_000
    );

    const [goodStakeAuth2] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), goodVerifierWorker2.toBuffer()],
      program.programId
    );

    const [goodStakeVault2] = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), goodVerifier2.publicKey.toBuffer()],
      program.programId
    );

    await program.methods
      .stakeWorker(new anchor.BN(1_000_000))
      .accounts({
        worker: goodVerifier2.publicKey,
        workerAccount: goodVerifierWorker2,
        mint: sharedMint,
        workerToken: goodVerifierToken2,
        stakeAuth: goodStakeAuth2,
        stakeVault: goodStakeVault2,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([goodVerifier2])
      .rpc();

    fragmentState = await program.account.fragment.fetch(fragment);
    let roundBufferYes2 = Buffer.alloc(2);
    roundBufferYes2.writeUInt16LE(fragmentState.round, 0);

    const [goodVote2] = PublicKey.findProgramAddressSync(
      [
        Buffer.from("fragment_vote"),
        fragment.toBuffer(),
        goodVerifier2.publicKey.toBuffer(),
        roundBufferYes2,
      ],
      program.programId
    );

    await program.methods
      .voteFragment(true)
      .accounts({
        verifier: goodVerifier2.publicKey,
        job,
        fragment,
        verifierWorker: goodVerifierWorker2,
        vote: goodVote2,
        escrowAuth,
        escrow: escrow.publicKey,
        workerToken: sharedWorkerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .signers([goodVerifier2])
      .rpc();

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
    assert.equal(workerAfter.stakeAmount.toString(), "900000");

    assert.equal(
      Number(stakeBefore.value.amount) - Number(stakeAfter.value.amount),
      100000
    );

    assert.equal(
      Number(treasuryAfter.value.amount) - Number(treasuryBefore.value.amount),
      100000
    );
  });
});
