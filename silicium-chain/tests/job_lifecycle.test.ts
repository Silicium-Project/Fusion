import * as anchor from "@coral-xyz/anchor";
import { assert } from "chai";
import { setupTestEnv } from "./helpers/setup";
import { expectFail } from "./helpers/utils";

describe("job lifecycle", () => {
  it("create_job + finalize_job constraints", async () => {
    const env = await setupTestEnv();

    const {
      program,
      client,
      mint,
      jobPda,
      escrowAuthPda,
      escrowKp,
      clientToken,
      jobId,
      expectedFragments,
      rewardPerFragment,
      deadlineUnix,
      tokenProgram,
      systemProgram,
      resultPda,
    } = env;

    await (program as any).methods
      .createJob(jobId, expectedFragments, rewardPerFragment, new anchor.BN(deadlineUnix))
      .accounts({
        client: client.publicKey,
        mint,
        job: jobPda,
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        clientToken,
        tokenProgram,
        systemProgram,
        rent: anchor.web3.SYSVAR_RENT_PUBKEY,
      })
      .signers([escrowKp])
      .rpc();

    await expectFail(
      (program as any).methods
        .finalizeJob(Array(32).fill(1), Buffer.from("ipfs://x"))
        .accounts({
          client: client.publicKey,
          job: jobPda,
          result: resultPda,
          escrowAuth: escrowAuthPda,
          escrow: escrowKp.publicKey,
          clientToken,
          tokenProgram,
          systemProgram,
        })
        .rpc()
    );

    const job = await (program as any).account.job.fetch(jobPda);
    assert.equal(job.verifiedFragments, 0);
  });
});
