import { setupTestEnv, createJobOnce } from "./helpers/setup";
import { expectFail } from "./helpers/utils";
import * as anchor from "@coral-xyz/anchor";
import { Keypair, PublicKey } from "@solana/web3.js";
import {
  getOrCreateAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";
import { assert } from "chai";

describe("fragment_vote.test", () => {
  it("vote_fragment reaches quorum and pays worker, blocks double vote", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    // --- Verifiers ---
    const verifier1 = Keypair.generate();
    const verifier2 = Keypair.generate();
    const badVerifier = Keypair.generate();

    // Airdrops
    for (const kp of [verifier1, verifier2, badVerifier]) {
      const sig = await env.provider.connection.requestAirdrop(
        kp.publicKey,
        2e9
      );
      await env.provider.connection.confirmTransaction(sig, "confirmed");
    }

    // --- Worker PDAs ---
    const workerPda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), env.worker.publicKey.toBuffer()],
      env.program.programId
    )[0];

    const verifier1Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier1.publicKey.toBuffer()],
      env.program.programId
    )[0];

    const verifier2Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier2.publicKey.toBuffer()],
      env.program.programId
    )[0];

    const badVerifierPda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), badVerifier.publicKey.toBuffer()],
      env.program.programId
    )[0];

    // --- Register workers ---
    await (env.program as any).methods
      .registerWorker()
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();

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

      // --- Create ATA + mint stake token ---
      const ata = await getOrCreateAssociatedTokenAccount(
        env.provider.connection,
        (env.client as any).payer,
        env.mint,
        v.kp.publicKey
      );

      await mintTo(
        env.provider.connection,
        (env.client as any).payer,
        env.mint,
        ata.address,
        env.client.publicKey,
        1
      );

      // --- Stake worker (MIN_VERIFIER_STAKE = 1) ---
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

    // --- Submit fragment ---
    await (env.program as any).methods
      .submitFragmentResult(
        0,
        Array(32).fill(1),
        Array(32).fill(2)
      )
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();

    const balBefore =
      await env.provider.connection.getTokenAccountBalance(
        env.workerToken
      );

    // --- Vote helper ---
    const votePda = (fragmentPk: PublicKey, verifierPk: PublicKey) =>
      PublicKey.findProgramAddressSync(
        [
          Buffer.from("fragment_vote"),
          fragmentPk.toBuffer(),
          verifierPk.toBuffer(),
        ],
        env.program.programId
      )[0];

    // --- Vote 1 ---
    await (env.program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: verifier1.publicKey,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        verifierWorker: verifier1Pda,
        vote: votePda(env.fragment0Pda, verifier1.publicKey),
        escrowAuth: env.escrowAuthPda,
        escrow: env.escrowKp.publicKey,
        workerToken: env.workerToken,
        tokenProgram: env.tokenProgram,
        systemProgram: env.systemProgram,
      })
      .signers([verifier1])
      .rpc();

    // --- Vote 2 (quorum reached) ---
    await (env.program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: verifier2.publicKey,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        verifierWorker: verifier2Pda,
        vote: votePda(env.fragment0Pda, verifier2.publicKey),
        escrowAuth: env.escrowAuthPda,
        escrow: env.escrowKp.publicKey,
        workerToken: env.workerToken,
        tokenProgram: env.tokenProgram,
        systemProgram: env.systemProgram,
      })
      .signers([verifier2])
      .rpc();

    const balAfter =
      await env.provider.connection.getTokenAccountBalance(
        env.workerToken
      );

    assert.isTrue(
      Number(balAfter.value.amount) >
        Number(balBefore.value.amount)
    );

    // --- Fragment status ---
    const frag: any = await (env.program as any).account.fragment.fetch(
      env.fragment0Pda
    );
    assert.notDeepEqual(frag.status, { submitted: {} });

    // --- Double vote should fail ---
    await expectFail(
      (env.program as any).methods
        .voteFragment(true)
        .accounts({
            verifier: verifier1.publicKey,
            job: env.jobPda,
            fragment: env.fragment0Pda,
            verifierWorker: verifier1Pda,
            vote: votePda(env.fragment0Pda, verifier1.publicKey),
            escrowAuth: env.escrowAuthPda,
            escrow: env.escrowKp.publicKey,
            workerToken: env.workerToken,
            tokenProgram: env.tokenProgram,
            systemProgram: env.systemProgram,
          })
        .signers([verifier1])
        .rpc()
    );

    // --- Unregistered verifier should fail ---
    await expectFail(
      (env.program as any).methods
        .voteFragment(true)
        .accounts({
          verifier: badVerifier.publicKey,
          job: env.jobPda,
          fragment: env.fragment0Pda,
          verifierWorker: badVerifierPda,
          vote: votePda(env.fragment0Pda, badVerifier.publicKey),
          escrowAuth: env.escrowAuthPda,
          escrow: env.escrowKp.publicKey,
          workerToken: env.workerToken,
          tokenProgram: env.tokenProgram,
          systemProgram: env.systemProgram,
        })
        .signers([badVerifier])
        .rpc()
    );
  });
});
