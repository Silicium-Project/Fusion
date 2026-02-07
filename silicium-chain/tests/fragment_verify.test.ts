import { setupTestEnv, createJobOnce } from "./helpers/setup";

describe("fragment verification", () => {
  it("verify fragment once", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    const {
      program,
      client,
      worker,
      jobPda,
      fragment0Pda,
      escrowAuthPda,
      escrowKp,
      workerToken,
      tokenProgram,
      systemProgram,
    } = env;

    await (program as any).methods
      .submitFragmentResult(0, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: worker.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        systemProgram,
      })
      .signers([worker])
      .rpc();

    await (program as any).methods
      .verifyFragment(true)
      .accounts({
        verifier: client.publicKey,
        job: jobPda,
        fragment: fragment0Pda,
        escrowAuth: escrowAuthPda,
        escrow: escrowKp.publicKey,
        workerToken,
        tokenProgram,
      })
      .rpc();
  });
});
