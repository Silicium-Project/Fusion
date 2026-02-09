import { setupTestEnv } from "./helpers/setup";
import * as anchor from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { assert } from "chai";

describe("worker register", () => {
  it("register_worker creates worker account", async () => {
    const env = await setupTestEnv();

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

    const w: any = await (env.program as any).account.worker.fetch(workerPda);
    assert.equal(w.owner.toBase58(), env.worker.publicKey.toBase58());
    assert.deepEqual(w.status, { active: {} });
    assert.equal(Number(w.stakeAmount), 0);
  });
});
