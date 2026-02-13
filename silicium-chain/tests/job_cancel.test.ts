// job_cancellation.test.ts
import { setupTestEnv, createJobOnce } from "./helpers/setup";
import { expectFail } from "./helpers/utils";

describe("job cancellation", () => {
  it("cancel blocked after progress", async () => {
    const env = await setupTestEnv();

    // ✅ NEW: ensure the job account exists (otherwise test is meaningless)
    await createJobOnce(env);

    const {
      program,
      client,
      jobPda,
      escrowAuthPda,
      escrowKp,
      clientToken,
      tokenProgram,
    } = env;

    await expectFail(
      (program as any).methods
        .cancelJob()
        .accounts({
          client: client.publicKey,
          job: jobPda,
          escrowAuth: escrowAuthPda,
          escrow: escrowKp.publicKey,
          clientToken,
          tokenProgram,
        })
        .rpc()
    );
  });
});

