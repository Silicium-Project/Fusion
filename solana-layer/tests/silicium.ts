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
let rejectVerifier: anchor.web3.Keypair;

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
            [
            Buffer.from("job"),
            client.toBuffer(),
            jobId.toArrayLike(Buffer, "le", 8),
            ],
            program.programId
        );

        const [escrowAuth] = PublicKey.findProgramAddressSync(
            [Buffer.from("escrow_auth"), job.toBuffer()],
            program.programId
        );

        const escrow = anchor.web3.Keypair.generate();
        sharedEscrow = escrow.publicKey;
        
        await program.methods
            .createJob(
            jobId,
            expectedFragments,
            rewardPerFragment,
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
            [
            Buffer.from("job"),
            worker.toBuffer(),
            jobId.toArrayLike(Buffer, "le", 8),
            ],
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

        await provider.connection.requestAirdrop(
            verifierKeypair.publicKey,
            2_000_000_000
        );

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
        const worker = provider.wallet.publicKey;
        const jobId = new anchor.BN(1);
        const fragmentIndex = 0;

        const [job] = PublicKey.findProgramAddressSync(
            [
            Buffer.from("job"),
            client.toBuffer(),
            jobId.toArrayLike(Buffer, "le", 8),
            ],
            program.programId
        );

        const indexBuffer = Buffer.alloc(4);
        indexBuffer.writeUInt32LE(fragmentIndex, 0);

        const [fragment] = PublicKey.findProgramAddressSync(
            [Buffer.from("fragment"), job.toBuffer(), indexBuffer],
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
        const worker = provider.wallet.publicKey;
        const jobId = new anchor.BN(1);
        const fragmentIndex = 0;

        // ===== 2e verifier =====
        const verifier2 = anchor.web3.Keypair.generate();

        await provider.connection.requestAirdrop(
            verifier2.publicKey,
            2_000_000_000
        );
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

        // ===== PDA =====
        const [job] = PublicKey.findProgramAddressSync(
            [
            Buffer.from("job"),
            client.toBuffer(),
            jobId.toArrayLike(Buffer, "le", 8),
            ],
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

        // ===== balance AVANT =====
        const workerTokenBefore = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

        // ===== vote 2 =====
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

        // ===== checks =====
        const fragmentAfter = await program.account.fragment.fetch(fragment);
        const jobAfter = await program.account.job.fetch(job);

        const workerTokenAfter = await provider.connection.getTokenAccountBalance(sharedWorkerToken);

        assert.deepEqual(fragmentAfter.status, { verified: {} });

        assert.equal(jobAfter.verifiedFragments, 1);

        // reward = 1_000_000
        const before = Number(workerTokenBefore.value.amount);
        const after = Number(workerTokenAfter.value.amount);

        assert.equal(after - before, 1_000_000);
        });

    
    it("creates a rejected fragment", async () => {
        const client = provider.wallet.publicKey;
        const payer = provider.wallet.payer as anchor.web3.Keypair;

        const expectedFragments = 1;
        const rewardPerFragment = new anchor.BN(1_000_000);
        const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
        const fragmentQuorum = 1;

        const clientToken = sharedWorkerToken;

        [rejectedJob] = PublicKey.findProgramAddressSync(
            [
            Buffer.from("job"),
            client.toBuffer(),
            rejectedJobId.toArrayLike(Buffer, "le", 8),
            ],
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
            .submitFragmentResult(
            fragmentIndex,
            Array(32).fill(7),
            Array(32).fill(8)
            )
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

        rejectVerifier = anchor.web3.Keypair.generate();

        await provider.connection.requestAirdrop(rejectVerifier.publicKey, 2_000_000_000);
        await new Promise((r) => setTimeout(r, 1000));

        const [rejectVerifierWorker] = PublicKey.findProgramAddressSync(
            [Buffer.from("worker"), rejectVerifier.publicKey.toBuffer()],
            program.programId
        );

        await program.methods
            .registerWorker()
            .accounts({
            worker: rejectVerifier.publicKey,
            workerAccount: rejectVerifierWorker,
            systemProgram: SystemProgram.programId,
            })
            .signers([rejectVerifier])
            .rpc();

        const rejectVerifierToken = await createAssociatedTokenAccount(
            provider.connection,
            payer,
            sharedMint,
            rejectVerifier.publicKey
        );

        await mintTo(
            provider.connection,
            payer,
            sharedMint,
            rejectVerifierToken,
            client,
            10_000_000
        );

        const [stakeAuth] = PublicKey.findProgramAddressSync(
            [Buffer.from("stake_auth"), rejectVerifierWorker.toBuffer()],
            program.programId
        );

        const [stakeVault] = PublicKey.findProgramAddressSync(
            [Buffer.from("stake_vault"), rejectVerifier.publicKey.toBuffer()],
            program.programId
        );

        await program.methods
            .stakeWorker(new anchor.BN(1_000_000))
            .accounts({
            worker: rejectVerifier.publicKey,
            workerAccount: rejectVerifierWorker,
            mint: sharedMint,
            workerToken: rejectVerifierToken,
            stakeAuth,
            stakeVault,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
            rent: SYSVAR_RENT_PUBKEY,
            })
            .signers([rejectVerifier])
            .rpc();

        const fragmentBefore = await program.account.fragment.fetch(rejectedFragment);

        const roundBuffer = Buffer.alloc(2);
        roundBuffer.writeUInt16LE(fragmentBefore.round, 0);

        const [vote] = PublicKey.findProgramAddressSync(
            [
            Buffer.from("fragment_vote"),
            rejectedFragment.toBuffer(),
            rejectVerifier.publicKey.toBuffer(),
            roundBuffer,
            ],
            program.programId
        );

        await program.methods
            .voteFragment(false)
            .accounts({
            verifier: rejectVerifier.publicKey,
            job: rejectedJob,
            fragment: rejectedFragment,
            verifierWorker: rejectVerifierWorker,
            vote,
            escrowAuth,
            escrow: rejectedEscrow,
            workerToken: sharedWorkerToken,
            tokenProgram: TOKEN_PROGRAM_ID,
            systemProgram: SystemProgram.programId,
            })
            .signers([rejectVerifier])
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
            .resubmitFragmentResult(
            fragmentIndex,
            Array(32).fill(9),
            Array(32).fill(10)
            )
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
});
