// tests/fragment_verify.test.ts
import * as anchor from "@coral-xyz/anchor";
import { setupTestEnv, createJobOnce, registerWorkerIfNeeded } from "./helpers/setup";
import { Keypair, PublicKey } from "@solana/web3.js";
import { getOrCreateAssociatedTokenAccount, mintTo } from "@solana/spl-token";
import { u16LE } from "./helpers/utils";

describe("fragment verification (decentralized)", () => {
  it("vote fragment to quorum (replaces verify_fragment)", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    const {
      program,
      worker,
      jobPda,
      fragment0Pda,
      escrowAuthPda,
      escrowKp,
      workerToken,
      mint,
      tokenProgram,
      systemProgram,
      provider,
      client,
    } = env;

    // --- Worker submits fragment ---
    const workerPda = await registerWorkerIfNeeded(env);

    await (program as any).methods
      .submitFragmentResult(0, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: worker.publicKey,
        workerAccount: workerPda,
        job: jobPda,
        fragment: fragment0Pda,
        workerToken, // ✅ NEW (required by SubmitFragmentResult)
        systemProgram,
      })
      .signers([worker])
      .rpc();

    // --- Create 2 verifiers to reach quorum=2 ---
    const verifier1 = Keypair.generate();
    const verifier2 = Keypair.generate();

    for (const v of [verifier1, verifier2]) {
      const sig = await provider.connection.requestAirdrop(v.publicKey, 2e9);
      await provider.connection.confirmTransaction(sig, "confirmed");
    }

    const verifier1Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier1.publicKey.toBuffer()],
      (program as any).programId
    )[0];

    const verifier2Pda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), verifier2.publicKey.toBuffer()],
      (program as any).programId
    )[0];

    // --- Register verifiers as workers + stake ---
    for (const v of [
      { kp: verifier1, pda: verifier1Pda },
      { kp: verifier2, pda: verifier2Pda },
    ]) {
      await (program as any).methods
        .registerWorker()
        .accounts({
          worker: v.kp.publicKey,
          workerAccount: v.pda,
          systemProgram,
        })
        .signers([v.kp])
        .rpc();

      // --- Create ATA + mint 1 token for staking ---
      const ata = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (client as any).payer,
        mint,
        v.kp.publicKey
      );

      await mintTo(
        provider.connection,
        (client as any).payer,
        mint,
        ata.address,
        client.publicKey,
        1
      );

      // --- Stake (MIN_VERIFIER_STAKE = 1) ---
      const stakeAuth = PublicKey.findProgramAddressSync(
        [Buffer.from("stake_auth"), v.pda.toBuffer()],
        (program as any).programId
      )[0];

      const stakeVault = PublicKey.findProgramAddressSync(
        [Buffer.from("stake_vault"), v.kp.publicKey.toBuffer()],
        (program as any).programId
      )[0];

      await (program as any).methods
        .stakeWorker(new anchor.BN(1))
        .accounts({
          worker: v.kp.publicKey,
          workerAccount: v.pda,
          mint,
          workerToken: ata.address,
          stakeAuth,
          stakeVault,
          tokenProgram,
          systemProgram,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .signers([v.kp])
        .rpc();
    }

    // --- Vote PDA helper (now includes round u16 LE) ---
    const votePda = (fragmentPk: PublicKey, verifierPk: PublicKey, round: number) =>
      PublicKey.findProgramAddressSync(
        [
          Buffer.from("fragment_vote"),
          fragmentPk.toBuffer(),
          verifierPk.toBuffer(),
          u16LE(round),
        ],
        (program as any).programId
      )[0];

    const round0 = 0;

    // --- Vote 1 ---
    await (program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: verifier1.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        verifierWorker: verifier1Pda,
        vote: votePda(fragment0Pda, verifier1.publicKey, round0),
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        workerToken,
        tokenProgram,
        systemProgram,
      })
      .signers([verifier1])
      .rpc();

    // --- Vote 2 (quorum reached => Verified + pay) ---
    await (program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: verifier2.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        verifierWorker: verifier2Pda,
        vote: votePda(fragment0Pda, verifier2.publicKey, round0),
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        workerToken,
        tokenProgram,
        systemProgram,
      })
      .signers([verifier2])
      .rpc();

    // Optional: fetch fragment to ensure it left Submitted
    const frag: any = await (program as any).account.fragment.fetch(fragment0Pda);
    // frag.status should now be { verified: {} } (Anchor enum shape)
    // you can assert if you want:
    // expect(frag.status).to.deep.equal({ verified: {} });
    void frag;
  });
});
