import * as anchor from "@coral-xyz/anchor";
import { Keypair, PublicKey } from "@solana/web3.js";
import { assert } from "chai";
import { setupTestEnv } from "./helpers/setup";

describe("treasury init", () => {
  it("init_treasury creates treasury state + token account", async () => {
    const env = await setupTestEnv();
    const { program, provider, mint, tokenProgram, systemProgram } = env;

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

    const state: any = await (program as any).account.treasury.fetch(treasuryStatePda);
    assert.equal(state.mint.toBase58(), mint.toBase58());
    assert.equal(state.authority.toBase58(), treasuryAuthPda.toBase58());

    const treasuryAcc = await env.provider.connection.getParsedAccountInfo(treasuryKp.publicKey);
    assert.isNotNull(treasuryAcc.value, "treasury token account must exist");
  });
});
