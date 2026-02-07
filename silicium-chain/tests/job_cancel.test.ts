import { setupTestEnv } from "./helpers/setup";
import { expectFail } from "./helpers/utils";

describe("job cancellation", () => {
  it("cancel blocked after progress", async () => {
    const env = await setupTestEnv();
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
