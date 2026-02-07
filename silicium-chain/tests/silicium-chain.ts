import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { PublicKey, SystemProgram } from "@solana/web3.js";
import BN from "bn.js";
import {
  createMint,
  getAssociatedTokenAddress,
  createAssociatedTokenAccount,
  mintTo,
  getAccount,
  TOKEN_PROGRAM_ID,
} from "@solana/spl-token";

describe("silicium-chain", () => {
  anchor.setProvider(anchor.AnchorProvider.env());
  const provider = anchor.getProvider() as anchor.AnchorProvider;

  const program = anchor.workspace.SiliciumChain as any;

  it("create_job: creates job + escrow and transfers deposit", async () => {
    const client = provider.wallet.publicKey;

    // 1) Create SPL Mint
    const mint = await createMint(
      provider.connection,
      // payer
      (provider.wallet as any).payer,
      // mint authority
      client,
      // freeze authority (optional)
      null,
      // decimals
      6
    );

    // 2) Create client ATA and mint tokens to it
    const clientToken = await getAssociatedTokenAddress(mint, client);
    await createAssociatedTokenAccount(
      provider.connection,
      (provider.wallet as any).payer,
      mint,
      client
    );

    // Mint 10 tokens (10 * 10^6 base units)
    await mintTo(
      provider.connection,
      (provider.wallet as any).payer,
      mint,
      clientToken,
      client,
      10_000_000
    );

    // 3) Params for create_job
    const jobId = new BN(1);
    const expectedFragments = 5;
    const rewardPerFragment = new BN(1_000_000); // 1 token (since decimals=6)
    const totalDeposit = rewardPerFragment.mul(new BN(expectedFragments));

    const now = Math.floor(Date.now() / 1000);
    const deadlineUnix = new BN(now + 3600); // +1 hour

    // 4) Derive PDAs used by program
    const [jobPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
      program.programId
    );

    const [escrowAuthPda] = PublicKey.findProgramAddressSync(
      [Buffer.from("escrow_auth"), jobPda.toBuffer()],
      program.programId
    );

    // 5) Call instruction
    await program.methods
      .createJob(jobId, expectedFragments, rewardPerFragment, deadlineUnix)
      .accounts({
        client,
        mint,
        job: jobPda,
        escrowAuth: escrowAuthPda,
        // escrow is init in instruction -> Anchor will compute it if your IDL has it;
        // BUT we must pass it explicitly if required by IDL.
        // We'll derive it from the job account after fetch if not required.
        clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: anchor.web3.SYSVAR_RENT_PUBKEY,
      })
      .rpc();

    // 6) Fetch Job account and assert fields
    const job = await program.account.job.fetch(jobPda);

    if (!new BN(job.jobId).eq(jobId)) throw new Error("job_id mismatch");
    if (!new PublicKey(job.client).equals(client)) throw new Error("client mismatch");
    if (!new PublicKey(job.mint).equals(mint)) throw new Error("mint mismatch");
    if (job.expectedFragments !== expectedFragments) throw new Error("expected_fragments mismatch");
    if (job.verifiedFragments !== 0) throw new Error("verified_fragments should be 0");
    if (!new BN(job.rewardPerFragment).eq(rewardPerFragment)) throw new Error("reward mismatch");
    if (!new BN(job.depositedAmount).eq(totalDeposit)) throw new Error("deposited_amount mismatch");
    if (!new BN(job.paidAmount).eq(new BN(0))) throw new Error("paid_amount should be 0");
    if (job.isFinalized !== false) throw new Error("is_finalized should be false");

    const escrowPubkey = new PublicKey(job.escrow);

    // 7) Check escrow token account balance == totalDeposit
    const escrowAcc = await getAccount(provider.connection, escrowPubkey);
    if (!new BN(escrowAcc.amount.toString()).eq(totalDeposit)) {
      throw new Error(`escrow amount mismatch: got ${escrowAcc.amount}, expected ${totalDeposit.toString()}`);
    }

    // 8) Check escrow authority == escrowAuth PDA
    if (!escrowAcc.owner.equals(escrowAuthPda)) {
      throw new Error(`escrow owner mismatch: got ${escrowAcc.owner.toBase58()}, expected ${escrowAuthPda.toBase58()}`);
    }
  });
});
