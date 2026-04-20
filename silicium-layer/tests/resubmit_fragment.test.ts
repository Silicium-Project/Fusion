import { setupTestEnv, createJobOnce } from "./helpers/setup";
import { expectFail, u16LE } from "./helpers/utils";
import * as anchor from "@coral-xyz/anchor";
import { Keypair, PublicKey } from "@solana/web3.js";
import { getOrCreateAssociatedTokenAccount } from "@solana/spl-token";
import { assert } from "chai";

describe("resubmit_fragment_result.test", () => {
  it("reject -> resubmit increments round -> can revote and pay new worker", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    // --- Verifiers ---
    const verifier1 = Keypair.generate();
    const verifier2 = Keypair.generate();

    for (const kp of [verifier1, verifier2]) {
      const sig = await env.provider.connection.requestAirdrop(kp.publicKey, 2e9);
      await env.provider.connection.confirmTransaction(sig, "confirmed");
    }

    // --- Create PDAs for verifier workers ---
    const verifier1Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier1.publicKey.toBuffer()],
      env.program.programId
    )[0];

    const verifier2Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier2.publicKey.toBuffer()],
      env.program.programId
    )[0];

    // --- Register verifier workers ---
    for (const v of [
      { kp: verifier1, pda: verifier1Pda },
      { kp: verifier2, pda: verifier2Pda },
    ]) {
      await (env.program as any).methods
        .registerWorker()
        .accounts({
          worker: v.kp.publicKey,
          workerAccount: v.pda,
          systemProgram: env.systemProgram,
        })
        .signers([v.kp])
        .rpc();

      // Stake (MIN_VERIFIER_STAKE = 1)
      const ata = await getOrCreateAssociatedTokenAccount(
        env.provider.connection,
        (env.client as any).payer,
        env.mint,
        v.kp.publicKey
      );

      // mint 1 token to them (enough for stake)
      // (setup env has mint authority = client)
      const { mintTo } = await import("@solana/spl-token");
      await mintTo(
        env.provider.connection,
        (env.client as any).payer,
        env.mint,
        ata.address,
        env.client.publicKey,
        1
      );

      const stakeAuth = PublicKey.findProgramAddressSync(
        [Buffer.from("stake_auth"), v.pda.toBuffer()],
        env.program.programId
      )[0];

      const stakeVault = PublicKey.findProgramAddressSync(
        [Buffer.from("stake_vault"), v.kp.publicKey.toBuffer()],
        env.program.programId
      )[0];

      await (env.program as any).methods
        .stakeWorker(new anchor.BN(1))
        .accounts({
          worker: v.kp.publicKey,
          workerAccount: v.pda,
          mint: env.mint,
          workerToken: ata.address,
          stakeAuth,
          stakeVault,
          tokenProgram: env.tokenProgram,
          systemProgram: env.systemProgram,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .signers([v.kp])
        .rpc();
    }

    // --- Register compute worker (env.worker) ---
    const workerPda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), env.worker.publicKey.toBuffer()],
      env.program.programId
    )[0];

    await (env.program as any).methods
      .registerWorker()
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();

    // --- Submit fragment round 0 ---
    await (env.program as any).methods
      .submitFragmentResult(0, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        workerToken: env.workerToken, // ✅ required now
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();

    // vote PDA helper with round
    const votePda = (fragmentPk: PublicKey, verifierPk: PublicKey, round: number) =>
      PublicKey.findProgramAddressSync(
        [
          Buffer.from("fragment_vote"),
          fragmentPk.toBuffer(),
          verifierPk.toBuffer(),
          u16LE(round),
        ],
        env.program.programId
      )[0];

    // --- Reject fragment (2 NO votes) at round 0 ---
    const round0 = 0;

    await (env.program as any).methods
      .voteFragment(false)
      .accounts({
        verifier: verifier1.publicKey,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        verifierWorker: verifier1Pda,
        vote: votePda(env.fragment0Pda, verifier1.publicKey, round0),
        escrowAuth: env.escrowAuthPda,
        escrow: env.escrowKp.publicKey,
        workerToken: env.workerToken,
        tokenProgram: env.tokenProgram,
        systemProgram: env.systemProgram,
      })
      .signers([verifier1])
      .rpc();

    await (env.program as any).methods
      .voteFragment(false)
      .accounts({
        verifier: verifier2.publicKey,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        verifierWorker: verifier2Pda,
        vote: votePda(env.fragment0Pda, verifier2.publicKey, round0),
        escrowAuth: env.escrowAuthPda,
        escrow: env.escrowKp.publicKey,
        workerToken: env.workerToken,
        tokenProgram: env.tokenProgram,
        systemProgram: env.systemProgram,
      })
      .signers([verifier2])
      .rpc();

    // fragment should be rejected now
    let frag: any = await (env.program as any).account.fragment.fetch(env.fragment0Pda);
    assert.notDeepEqual(frag.status, { submitted: {} });

    // --- New compute worker to resubmit ---
    const worker2 = Keypair.generate();
    const sig2 = await env.provider.connection.requestAirdrop(worker2.publicKey, 2e9);
    await env.provider.connection.confirmTransaction(sig2, "confirmed");

    const worker2Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), worker2.publicKey.toBuffer()],
      env.program.programId
    )[0];

    await (env.program as any).methods
      .registerWorker()
      .accounts({
        worker: worker2.publicKey,
        workerAccount: worker2Pda,
        systemProgram: env.systemProgram,
      })
      .signers([worker2])
      .rpc();

    const worker2Ata = await getOrCreateAssociatedTokenAccount(
      env.provider.connection,
      (env.client as any).payer,
      env.mint,
      worker2.publicKey
    );

    const balBefore = await env.provider.connection.getTokenAccountBalance(worker2Ata.address);

    // --- Resubmit fragment (round becomes 1) ---
    // ⚠️ Si ton handler resubmit prend fragment_index en argument, utilise :
    await (env.program as any).methods
      .resubmitFragmentResult(0, Array(32).fill(9), Array(32).fill(8))
      .accounts({
        worker: worker2.publicKey,
        workerAccount: worker2Pda,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        workerToken: worker2Ata.address,
      })
      .signers([worker2])
      .rpc();

    frag = await (env.program as any).account.fragment.fetch(env.fragment0Pda);
    assert.equal(frag.round, 1);

    // --- Using old vote PDA (round 0) must fail (seed mismatch) ---
    await expectFail(
      (env.program as any).methods
        .voteFragment(true)
        .accounts({
          verifier: verifier1.publicKey,
          job: env.jobPda,
          fragment: env.fragment0Pda,
          verifierWorker: verifier1Pda,
          vote: votePda(env.fragment0Pda, verifier1.publicKey, round0), // wrong round
          escrowAuth: env.escrowAuthPda,
          escrow: env.escrowKp.publicKey,
          workerToken: worker2Ata.address,
          tokenProgram: env.tokenProgram,
          systemProgram: env.systemProgram,
        })
        .signers([verifier1])
        .rpc()
    );

    // --- Vote YES at round 1 should work and pay worker2 ---
    const round1 = 1;

    await (env.program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: verifier1.publicKey,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        verifierWorker: verifier1Pda,
        vote: votePda(env.fragment0Pda, verifier1.publicKey, round1),
        escrowAuth: env.escrowAuthPda,
        escrow: env.escrowKp.publicKey,
        workerToken: worker2Ata.address,
        tokenProgram: env.tokenProgram,
        systemProgram: env.systemProgram,
      })
      .signers([verifier1])
      .rpc();

    await (env.program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: verifier2.publicKey,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        verifierWorker: verifier2Pda,
        vote: votePda(env.fragment0Pda, verifier2.publicKey, round1),
        escrowAuth: env.escrowAuthPda,
        escrow: env.escrowKp.publicKey,
        workerToken: worker2Ata.address,
        tokenProgram: env.tokenProgram,
        systemProgram: env.systemProgram,
      })
      .signers([verifier2])
      .rpc();

    const balAfter = await env.provider.connection.getTokenAccountBalance(worker2Ata.address);

    assert.isTrue(Number(balAfter.value.amount) > Number(balBefore.value.amount));
  });
});
