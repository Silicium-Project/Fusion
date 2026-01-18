import * as anchor from "@anchor-lang/core";
import { Program } from "@anchor-lang/core";
import { SiliciumChain } from "../target/types/silicium_chain";

describe("silicium-chain", () => {
  // Configure the client to use the local cluster.
  anchor.setProvider(anchor.AnchorProvider.env());

  const program = anchor.workspace.siliciumChain as Program<SiliciumChain>;

  it("Is initialized!", async () => {
    // Add your test here.
    const tx = await program.methods.initialize().rpc();
    console.log("Your transaction signature", tx);
  });
});
