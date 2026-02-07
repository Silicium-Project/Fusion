import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { Keypair, PublicKey, SystemProgram } from "@solana/web3.js";
import {
  TOKEN_PROGRAM_ID,
  createMint,
  getOrCreateAssociatedTokenAccount,
  mintTo,
} from "@solana/spl-token";

import { bnToU64LE, u32LE } from "./utils";

export async function setupTestEnv() {
  anchor.setProvider(anchor.AnchorProvider.env());
  const provider = anchor.getProvider() as anchor.AnchorProvider;
  const program = anchor.workspace.SiliciumChain as Program;

  const client = provider.wallet;
  const worker = Keypair.generate();

  // Airdrop to worker
  const sig = await provider.connection.requestAirdrop(worker.publicKey, 2e9);
  await provider.connection.confirmTransaction(sig, "confirmed");

  // Mint
  const mint = await createMint(
    provider.connection,
    (client as any).payer,
    client.publicKey,
    null,
    6
  );

  const clientAta = await getOrCreateAssociatedTokenAccount(
    provider.connection,
    (client as any).payer,
    mint,
    client.publicKey
  );

  const workerAta = await getOrCreateAssociatedTokenAccount(
    provider.connection,
    (client as any).payer,
    mint,
    worker.publicKey
  );

  // Job params (unique jobId to avoid PDA collisions across test files)
  const jobId = new anchor.BN(Date.now());
  const expectedFragments = 2;
  const rewardPerFragment = new anchor.BN(10);
  const deadlineUnix = Math.floor(Date.now() / 1000) + 3600;

  // Mint funds
  const total = rewardPerFragment.mul(new anchor.BN(expectedFragments));
  await mintTo(
    provider.connection,
    (client as any).payer,
    mint,
    clientAta.address,
    client.publicKey,
    total.toNumber()
  );

  // PDAs
  const [jobPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("job"), client.publicKey.toBuffer(), bnToU64LE(jobId)],
    program.programId
  );

  const [escrowAuthPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), jobPda.toBuffer()],
    program.programId
  );

  const fragment0Pda = PublicKey.findProgramAddressSync(
    [Buffer.from("fragment"), jobPda.toBuffer(), u32LE(0)],
    program.programId
  )[0];

  const fragment1Pda = PublicKey.findProgramAddressSync(
    [Buffer.from("fragment"), jobPda.toBuffer(), u32LE(1)],
    program.programId
  )[0];

  const resultPda = PublicKey.findProgramAddressSync(
    [Buffer.from("result"), jobPda.toBuffer()],
    program.programId
  )[0];

  const escrowKp = Keypair.generate();

  return {
    provider,
    program,
    client,
    worker,
    mint,
    clientToken: clientAta.address,
    workerToken: workerAta.address,
    jobId,
    expectedFragments,
    rewardPerFragment,
    deadlineUnix,
    jobPda,
    escrowAuthPda,
    fragment0Pda,
    fragment1Pda,
    resultPda,
    escrowKp,
    systemProgram: SystemProgram.programId,
    tokenProgram: TOKEN_PROGRAM_ID,
    __jobCreated: false,
  };
}

export async function createJobOnce(env: any) {
  if (env.__jobCreated) return;
  env.__jobCreated = true;

  await (env.program as any).methods
    .createJob(
      env.jobId,
      env.expectedFragments,
      env.rewardPerFragment,
      new anchor.BN(env.deadlineUnix)
    )
    .accounts({
      client: env.client.publicKey,
      mint: env.mint,
      job: env.jobPda,
      escrowAuth: env.escrowAuthPda,
      escrow: env.escrowKp.publicKey,
      clientToken: env.clientToken,
      tokenProgram: env.tokenProgram,
      systemProgram: env.systemProgram,
      rent: anchor.web3.SYSVAR_RENT_PUBKEY,
    })
    .signers([env.escrowKp])
    .rpc();
}

export async function registerWorkerIfNeeded(env: any) {
  const [workerPda] = PublicKey.findProgramAddressSync(
    [Buffer.from("worker"), env.worker.publicKey.toBuffer()],
    env.program.programId
  );

  // tente register (si déjà fait dans ce test, ça fail => ignore)
  try {
    await (env.program as any).methods
      .registerWorker()
      .accounts({
        worker: env.worker.publicKey,
        workerAccount: workerPda,
        systemProgram: env.systemProgram,
      })
      .signers([env.worker])
      .rpc();
  } catch (_) {}

  return workerPda;
}
