// tests/slash_vote.test.ts
import * as anchor from "@coral-xyz/anchor";
import { Keypair, PublicKey } from "@solana/web3.js";
import { assert } from "chai";
import { getOrCreateAssociatedTokenAccount, mintTo } from "@solana/spl-token";

import { setupTestEnv, createJobOnce } from "./helpers/setup";
import { expectFail, u16LE } from "./helpers/utils";

describe("slash vote", () => {
  it("slashes wrong-side vote into treasury and prevents double slashing", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    const {
      program,
      provider,
      client,
      mint,
      jobPda,
      fragment0Pda,
      escrowAuthPda,
      escrowKp,
      worker,
      workerToken,
      tokenProgram,
      systemProgram,
    } = env;

    // -----------------------
    // Init Treasury (STATE + TOKEN)
    // -----------------------
    const [treasuryStatePda] = PublicKey.findProgramAddressSync(
      [Buffer.from("treasury"), mint.toBuffer()],
      program.programId
    );

    const [treasuryAuthPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("treasury_auth"), mint.toBuffer()],
      program.programId
    );

    const treasuryKp = Keypair.generate();

    await (program as any).methods
      .initTreasury()
      .accounts({
        payer: (provider.wallet as any).publicKey,
        mint,
        treasuryState: treasuryStatePda,
        treasuryAuth: treasuryAuthPda,
        treasury: treasuryKp.publicKey,
        tokenProgram,
        systemProgram,
        rent: anchor.web3.SYSVAR_RENT_PUBKEY,
      })
      .signers([treasuryKp])
      .rpc();

    // -----------------------
    // Register compute worker + submit fragment
    // -----------------------
    const workerPda = PublicKey.findProgramAddressSync(
      [Buffer.from("worker"), worker.publicKey.toBuffer()],
      program.programId
    )[0];

    await (program as any).methods
      .registerWorker()
      .accounts({
        worker: worker.publicKey,
        workerAccount: workerPda,
        systemProgram,
      })
      .signers([worker])
      .rpc();

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

    // -----------------------
    // Create 3 verifiers
    // -----------------------
    const v1 = Keypair.generate(); // will vote NO (wrong)
    const v2 = Keypair.generate(); // YES
    const v3 = Keypair.generate(); // YES

    for (const v of [v1, v2, v3]) {
      const sig = await provider.connection.requestAirdrop(v.publicKey, 2e9);
      await provider.connection.confirmTransaction(sig, "confirmed");
    }

    const mkWorkerPda = (pk: PublicKey) =>
      PublicKey.findProgramAddressSync([Buffer.from("worker"), pk.toBuffer()], program.programId)[0];

    const v1Pda = mkWorkerPda(v1.publicKey);
    const v2Pda = mkWorkerPda(v2.publicKey);
    const v3Pda = mkWorkerPda(v3.publicKey);

    // Register verifiers + stake
    for (const entry of [
      { kp: v1, pda: v1Pda },
      { kp: v2, pda: v2Pda },
      { kp: v3, pda: v3Pda },
    ]) {
      await (program as any).methods
        .registerWorker()
        .accounts({
          worker: entry.kp.publicKey,
          workerAccount: entry.pda,
          systemProgram,
        })
        .signers([entry.kp])
        .rpc();

      const ata = await getOrCreateAssociatedTokenAccount(
        provider.connection,
        (client as any).payer,
        mint,
        entry.kp.publicKey
      );

      await mintTo(
        provider.connection,
        (client as any).payer,
        mint,
        ata.address,
        client.publicKey,
        1
      );

      const stakeAuth = PublicKey.findProgramAddressSync(
        [Buffer.from("stake_auth"), entry.pda.toBuffer()],
        program.programId
      )[0];

      const stakeVault = PublicKey.findProgramAddressSync(
        [Buffer.from("stake_vault"), entry.kp.publicKey.toBuffer()],
        program.programId
      )[0];

      await (program as any).methods
        .stakeWorker(new anchor.BN(1))
        .accounts({
          worker: entry.kp.publicKey,
          workerAccount: entry.pda,
          mint,
          workerToken: ata.address,
          stakeAuth,
          stakeVault,
          tokenProgram,
          systemProgram,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .signers([entry.kp])
        .rpc();
    }

    // -----------------------
    // Vote (round = 0) => v1 NO (wrong), v2 YES, v3 YES => Verified
    // -----------------------
    const votePda = (fragmentPk: PublicKey, verifierPk: PublicKey, round: number) =>
      PublicKey.findProgramAddressSync(
        [
          Buffer.from("fragment_vote"),
          fragmentPk.toBuffer(),
          verifierPk.toBuffer(),
          u16LE(round),
        ],
        program.programId
      )[0];

    const round0 = 0;

    await (program as any).methods
      .voteFragment(false)
      .accounts({
        verifier: v1.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        verifierWorker: v1Pda,
        vote: votePda(fragment0Pda, v1.publicKey, round0),
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        workerToken,
        tokenProgram,
        systemProgram,
      })
      .signers([v1])
      .rpc();

    await (program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: v2.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        verifierWorker: v2Pda,
        vote: votePda(fragment0Pda, v2.publicKey, round0),
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        workerToken,
        tokenProgram,
        systemProgram,
      })
      .signers([v2])
      .rpc();

    await (program as any).methods
      .voteFragment(true)
      .accounts({
        verifier: v3.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        verifierWorker: v3Pda,
        vote: votePda(fragment0Pda, v3.publicKey, round0),
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        workerToken,
        tokenProgram,
        systemProgram,
      })
      .signers([v3])
      .rpc();

    const frag: any = await (program as any).account.fragment.fetch(fragment0Pda);
    assert.notDeepEqual(frag.status, { submitted: {} });

    // -----------------------
    // Slash v1 vote (wrong side) into treasury
    // -----------------------
    const v1StakeAuth = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_auth"), v1Pda.toBuffer()],
      program.programId
    )[0];

    const v1StakeVault = PublicKey.findProgramAddressSync(
      [Buffer.from("stake_vault"), v1.publicKey.toBuffer()],
      program.programId
    )[0];

    const treasuryBalBefore = await provider.connection.getTokenAccountBalance(treasuryKp.publicKey);
    const v1StakeBalBefore = await provider.connection.getTokenAccountBalance(v1StakeVault);

    await (program as any).methods
      .slashVote()
      .accounts({
        slasher: (provider.wallet as any).publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        vote: votePda(fragment0Pda, v1.publicKey, round0), // ✅ round included
        verifierWorker: v1Pda,
        treasuryState: treasuryStatePda,
        stakeAuth: v1StakeAuth,
        stakeVault: v1StakeVault,
        treasuryAuth: treasuryAuthPda,
        treasury: treasuryKp.publicKey,
        tokenProgram,
      })
      .rpc();

    const treasuryBalAfter = await provider.connection.getTokenAccountBalance(treasuryKp.publicKey);
    const v1StakeBalAfter = await provider.connection.getTokenAccountBalance(v1StakeVault);

    assert.isTrue(
      Number(treasuryBalAfter.value.amount) > Number(treasuryBalBefore.value.amount),
      "treasury should receive slashed tokens"
    );

    assert.isTrue(
      Number(v1StakeBalAfter.value.amount) < Number(v1StakeBalBefore.value.amount),
      "verifier stake vault should decrease"
    );

    const voteAcc: any = await (program as any).account.fragmentVote.fetch(
      votePda(fragment0Pda, v1.publicKey, round0)
    );
    assert.equal(voteAcc.slashed, true);

    // Double slashing must fail
    await expectFail(
      (program as any).methods
        .slashVote()
        .accounts({
          slasher: (provider.wallet as any).publicKey,
          job: jobPda,
          fragment: fragment0Pda,
          vote: votePda(fragment0Pda, v1.publicKey, round0),
          verifierWorker: v1Pda,
          treasuryState: treasuryStatePda,
          stakeAuth: v1StakeAuth,
          stakeVault: v1StakeVault,
          treasuryAuth: treasuryAuthPda,
          treasury: treasuryKp.publicKey,
          tokenProgram,
        })
        .rpc(),
      "double slashing should fail"
    );
  });
});
