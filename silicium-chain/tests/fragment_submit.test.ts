import { setupTestEnv, createJobOnce, registerWorkerIfNeeded } from "./helpers/setup";

describe("fragment submission", () => {
  it("submit once", async () => {
    const env = await setupTestEnv();
    await createJobOnce(env);

    const {
      program,
      worker,
      jobPda,
      fragment0Pda,
      systemProgram,
      workerToken,
    } = env;

    const workerPda = await registerWorkerIfNeeded(env);

    await (program as any).methods
      .submitFragmentResult(0, Array(32).fill(1), Array(32).fill(2))
      .accounts({
        worker: worker.publicKey,
        workerAccount: workerPda,
        job: jobPda,
        fragment: fragment0Pda,
        workerToken,
        systemProgram,
      })
      .signers([worker])
      .rpc();
  });
});
