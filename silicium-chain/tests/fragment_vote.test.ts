import { setupTestEnv, createJobOnce } from "./helpers/setup";
import { expectFail } from "./helpers/utils";
import * as anchor from "@coral-xyz/anchor";
import { Keypair, PublicKey } from "@solana/web3.js";
import { assert } from "chai";

describe("fragment_vote.test", () => {
  it("vote_fragment reaches quorum and pays worker, blocks double vote", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    // Extra verifiers
    const verifier1 = Keypair.generate();
    const verifier2 = Keypair.generate();
    const badVerifier = Keypair.generate();

    // airdrops
    for (const kp of [verifier1, verifier2, badVerifier]) {
      const sig = await env.provider.connection.requestAirdrop(kp.publicKey, 2e9);
      await env.provider.connection.confirmTransaction(sig, "confirmed");
    }

    // PDAs: worker accounts
    const [workerPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), env.worker.publicKey.toBuffer()],
      env.program.programId
    );
    const [verifier1Pda] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier1.publicKey.toBuffer()],
      env.program.programId
    );
    const [verifier2Pda] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier2.publicKey.toBuffer()],
      env.program.programId
    );
    const [badVerifierPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), badVerifier.publicKey.toBuffer()],
      env.program.programId
    );

    // Register submitter worker (env.worker)
    await (env.program as any).methods
      .registerWorker()
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();

    // Register verifiers
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
    }

    // Submit fragment 0 (needs workerAccount in your accounts)
    const fragmentIndex = 0;

    await (env.program as any).methods
      .submitFragmentResult(fragmentIndex, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        job: env.jobPda,
        fragment: env.fragment0Pda,
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();

    // Balance before
    const balBefore = await env.provider.connection.getTokenAccountBalance(env.workerToken);

    // Vote PDA helper
    const votePda = (fragmentPk: PublicKey, verifierPk: PublicKey) =>
      PublicKey.findProgramAddressSync(
        [Buffer.from("fragment_vote"), fragmentPk.toBuffer(), verifierPk.toBuffer()],
        env.program.programId
      )[0];

    // Vote 1 (verifier1)
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

    // Vote 2 (verifier2) => should hit quorum=2 and pay worker
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

    const balAfter = await env.provider.connection.getTokenAccountBalance(env.workerToken);
    assert.isTrue(Number(balAfter.value.amount) > Number(balBefore.value.amount));

    // Fragment status should no longer be Submitted
    const frag: any = await (env.program as any).account.fragment.fetch(env.fragment0Pda);
    assert.notDeepEqual(frag.status, { submitted: {} });

    // Double vote by verifier1 should fail (vote PDA already exists)
    await expectFail(
      (env.program as any).methods
        .voteFragment(true)
        .accounts({
          verifier: verifier1.publicKey,
          job: env.jobPda,
          fragment: env.fragment0Pda,
          verifierWorker: verifier1Pda,
          vote: votePda(env.fragment0Pda, verifier1.publicKey), // same PDA
          escrowAuth: env.escrowAuthPda,
          escrow: env.escrowKp.publicKey,
          workerToken: env.workerToken,
          tokenProgram: env.tokenProgram,
          systemProgram: env.systemProgram,
        })
        .signers([verifier1])
        .rpc(),
      "Expected double vote to fail"
    );

    // Unregistered verifier should fail (worker PDA doesn't exist)
    await expectFail(
      (env.program as any).methods
        .voteFragment(true)
        .accounts({
          verifier: badVerifier.publicKey,
          job: env.jobPda,
          fragment: env.fragment0Pda,
          verifierWorker: badVerifierPda, // not created on-chain
          vote: votePda(env.fragment0Pda, badVerifier.publicKey),
          escrowAuth: env.escrowAuthPda,
          escrow: env.escrowKp.publicKey,
          workerToken: env.workerToken,
          tokenProgram: env.tokenProgram,
          systemProgram: env.systemProgram,
        })
        .signers([badVerifier])
        .rpc(),
      "Expected unregistered verifier vote to fail"
    );
  });
});
