/**
 * Silicium Solana Layer — Devnet minimal write flow
 *
 * Put this file in:
 *   solana-layer/scripts/devnet_minimal_job_flow.ts
 *
 * Run from solana-layer/:
 *   npx ts-node scripts/devnet_minimal_job_flow.ts
 *
 * What it does on Devnet:
 * - loads local IDL
 * - checks deployed program
 * - creates a test SPL mint
 * - creates/mints token accounts
 * - creates/registers/stakes a fresh compute worker keypair
 * - creates/registers/stakes two verifier keypairs
 * - creates a 1-fragment job
 * - claims fragment 0
 * - submits a result
 * - verifier votes YES
 * - verifier claims reward
 *
 * It intentionally does not finalize the job, to keep the flow light.
 */

import * as anchor from "@coral-xyz/anchor";
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  SYSVAR_RENT_PUBKEY,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import {
  TOKEN_PROGRAM_ID,
  createAssociatedTokenAccount,
  createMint,
  getAccount,
  mintTo,
} from "@solana/spl-token";
import fs from "fs";
import os from "os";
import path from "path";

const DEVNET_RPC = process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
const PROGRAM_ID = new PublicKey(
  process.env.SOLANA_LAYER_PROGRAM_ID ?? "4FPGViycNEGCtwnNs3NN2pPQu9ziTch8o9zkVc2VnKVP",
);

const STAKE_AMOUNT = new anchor.BN(1_000_000);
const REWARD_PER_FRAGMENT = new anchor.BN(1_000_000);
const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);
const VERIFIER_REWARD_BUDGET = new anchor.BN(200_000);

function logStep(title: string) {
  console.log(`\n=== ${title} ===`);
}

function readKeypair(filePath: string): Keypair {
  const resolved = filePath.startsWith("~")
    ? path.join(os.homedir(), filePath.slice(1))
    : filePath;

  const raw = fs.readFileSync(resolved, "utf8");
  return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(raw)));
}

function loadIdl(): any {
  const candidates = [
    path.resolve(process.cwd(), "target/idl/solana_layer.json"),
    path.resolve(process.cwd(), "solana-layer/target/idl/solana_layer.json"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      const idl = JSON.parse(fs.readFileSync(candidate, "utf8"));
      idl.address = PROGRAM_ID.toBase58();
      return idl;
    }
  }

  throw new Error("IDL not found. Run `anchor build` from solana-layer/ first.");
}

function u32le(n: number): Buffer {
  const buf = Buffer.alloc(4);
  buf.writeUInt32LE(n, 0);
  return buf;
}

function u16le(n: number): Buffer {
  const buf = Buffer.alloc(2);
  buf.writeUInt16LE(n, 0);
  return buf;
}

function jobPda(client: PublicKey, jobId: anchor.BN): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
    PROGRAM_ID,
  )[0];
}

function fragmentPda(job: PublicKey, fragmentIndex: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment"), job.toBuffer(), u32le(fragmentIndex)],
    PROGRAM_ID,
  )[0];
}

function workerPda(owner: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("worker"), owner.toBuffer()],
    PROGRAM_ID,
  )[0];
}

function stakeAuthPda(workerAccount: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_auth"), workerAccount.toBuffer()],
    PROGRAM_ID,
  )[0];
}

function stakeVaultPda(owner: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("stake_vault"), owner.toBuffer()],
    PROGRAM_ID,
  )[0];
}

function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), job.toBuffer()],
    PROGRAM_ID,
  )[0];
}

function votePda(fragment: PublicKey, verifier: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment_vote"), fragment.toBuffer(), verifier.toBuffer(), u16le(round)],
    PROGRAM_ID,
  )[0];
}

function roundResolutionPda(fragment: PublicKey, round: number): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("fragment_resolution"), fragment.toBuffer(), u16le(round)],
    PROGRAM_ID,
  )[0];
}

async function ensureWorkerRegistered(program: any, owner: Keypair, label: string): Promise<PublicKey> {
  const workerAccount = workerPda(owner.publicKey);
  const info = await program.provider.connection.getAccountInfo(workerAccount, "confirmed");

  if (info) {
    const state = await program.account.worker.fetch(workerAccount);
    console.log(`${label} worker already registered:`, {
      workerAccount: workerAccount.toBase58(),
      reputation: Number(state.reputation?.toString?.() ?? state.reputation),
      stakeAmount: Number(state.stakeAmount?.toString?.() ?? state.stakeAmount),
    });
    return workerAccount;
  }

  const sig = await program.methods
    .registerWorker()
    .accounts({
      worker: owner.publicKey,
      workerAccount,
      systemProgram: SystemProgram.programId,
    })
    .signers([owner])
    .rpc();

  console.log(`${label} registerWorker tx:`, sig);
  return workerAccount;
}

async function stakeWorker(
  program: any,
  owner: Keypair,
  workerAccount: PublicKey,
  mint: PublicKey,
  workerToken: PublicKey,
  label: string,
) {
  const sig = await program.methods
    .stakeWorker(STAKE_AMOUNT)
    .accounts({
      worker: owner.publicKey,
      workerAccount,
      mint,
      workerToken,
      stakeAuth: stakeAuthPda(workerAccount),
      stakeVault: stakeVaultPda(owner.publicKey),
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([owner])
    .rpc();

  console.log(`${label} stakeWorker tx:`, sig);
}

async function main() {
  logStep("Setup");
  const connection = new Connection(DEVNET_RPC, "confirmed");
  const walletPath = process.env.ANCHOR_WALLET ?? "~/.config/solana/id.json";
  const payer = readKeypair(walletPath);
  const wallet = new anchor.Wallet(payer);
  const provider = new anchor.AnchorProvider(connection, wallet, {
    commitment: "confirmed",
    preflightCommitment: "confirmed",
  });
  anchor.setProvider(provider);

  const idl = loadIdl();
  const program = new (anchor as any).Program(idl, provider) as any;

  console.log("rpc:", DEVNET_RPC);
  console.log("program:", PROGRAM_ID.toBase58());
  console.log("wallet:", wallet.publicKey.toBase58());
  console.log("balance:", (await connection.getBalance(wallet.publicKey)) / LAMPORTS_PER_SOL, "SOL");

  const programInfo = await connection.getAccountInfo(PROGRAM_ID, "confirmed");
  if (!programInfo?.executable) {
    throw new Error(`Program not found or not executable on Devnet: ${PROGRAM_ID.toBase58()}`);
  }

  if ((await connection.getBalance(wallet.publicKey)) < 0.25 * LAMPORTS_PER_SOL) {
    throw new Error("Wallet balance is low. Add Devnet SOL before running this write flow.");
  }

  logStep("Create test SPL mint and token accounts");
  const mint = await createMint(connection, payer, wallet.publicKey, null, 6);
  console.log("mint:", mint.toBase58());

  const clientToken = await createAssociatedTokenAccount(
    connection,
    payer,
    mint,
    wallet.publicKey,
  );
  console.log("client token:", clientToken.toBase58());

  await mintTo(connection, payer, mint, clientToken, wallet.publicKey, 20_000_000);
  console.log("minted 20 tokens to client token account");

  const computeWorker = Keypair.generate();
  const verifier = Keypair.generate();
  const verifier2 = Keypair.generate();

  async function fundParticipant(label: string, recipient: PublicKey) {
    const lamports = 80_000_000;
    const tx = new anchor.web3.Transaction().add(
      SystemProgram.transfer({
        fromPubkey: wallet.publicKey,
        toPubkey: recipient,
        lamports,
      }),
    );
    const sig = await provider.sendAndConfirm(tx, []);
    console.log(`${label} SOL fund tx:`, sig);
  }

  await fundParticipant("compute worker", computeWorker.publicKey);
  await fundParticipant("verifier 1", verifier.publicKey);
  await fundParticipant("verifier 2", verifier2.publicKey);

  const computeWorkerToken = await createAssociatedTokenAccount(
    connection,
    payer,
    mint,
    computeWorker.publicKey,
  );
  await mintTo(connection, payer, mint, computeWorkerToken, wallet.publicKey, 5_000_000);

  const verifierToken = await createAssociatedTokenAccount(
    connection,
    payer,
    mint,
    verifier.publicKey,
  );
  await mintTo(connection, payer, mint, verifierToken, wallet.publicKey, 5_000_000);

  const verifier2Token = await createAssociatedTokenAccount(
    connection,
    payer,
    mint,
    verifier2.publicKey,
  );
  await mintTo(connection, payer, mint, verifier2Token, wallet.publicKey, 5_000_000);

  console.log("compute worker:", computeWorker.publicKey.toBase58());
  console.log("compute worker token:", computeWorkerToken.toBase58());
  console.log("verifier 1:", verifier.publicKey.toBase58());
  console.log("verifier 1 token:", verifierToken.toBase58());
  console.log("verifier 2:", verifier2.publicKey.toBase58());
  console.log("verifier 2 token:", verifier2Token.toBase58());

  logStep("Register and stake compute worker + verifiers");
  const computeWorkerAccount = await ensureWorkerRegistered(program, computeWorker, "compute worker");
  await stakeWorker(program, computeWorker, computeWorkerAccount, mint, computeWorkerToken, "compute worker");

  const verifierWorkerAccount = await ensureWorkerRegistered(program, verifier, "verifier 1");
  await stakeWorker(program, verifier, verifierWorkerAccount, mint, verifierToken, "verifier 1");

  const verifier2WorkerAccount = await ensureWorkerRegistered(program, verifier2, "verifier 2");
  await stakeWorker(program, verifier2, verifier2WorkerAccount, mint, verifier2Token, "verifier 2");

  logStep("Create one-fragment job");
  const jobId = new anchor.BN(Date.now());
  const job = jobPda(wallet.publicKey, jobId);
  const escrowAuth = escrowAuthPda(job);
  const escrow = Keypair.generate();
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);

  const createJobSig = await program.methods
    .createJob(
      jobId,
      1,
      REWARD_PER_FRAGMENT,
      VERIFIER_REWARD_PER_VOTE,
      VERIFIER_REWARD_BUDGET,
      deadlineUnix,
      2,
    )
    .accounts({
      client: wallet.publicKey,
      mint,
      job,
      escrowAuth,
      escrow: escrow.publicKey,
      clientToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
      rent: SYSVAR_RENT_PUBKEY,
    })
    .signers([escrow])
    .rpc();

  console.log("createJob tx:", createJobSig);
  console.log("job:", job.toBase58());
  console.log("escrow:", escrow.publicKey.toBase58());

  logStep("Claim and submit fragment 0");
  const fragment = fragmentPda(job, 0);

  const claimSig = await program.methods
    .claimFragment(0)
    .accounts({
      worker: computeWorker.publicKey,
      workerAccount: computeWorkerAccount,
      job,
      fragment,
      workerToken: computeWorkerToken,
      systemProgram: SystemProgram.programId,
    })
    .signers([computeWorker])
    .rpc();

  console.log("claimFragment tx:", claimSig);

  const submitSig = await program.methods
    .submitFragmentResult(0, Array(32).fill(7), Array(32).fill(8))
    .accounts({
      worker: computeWorker.publicKey,
      workerAccount: computeWorkerAccount,
      job,
      fragment,
      workerToken: computeWorkerToken,
    })
    .signers([computeWorker])
    .rpc();

  console.log("submitFragmentResult tx:", submitSig);

  logStep("Verifiers vote YES until quorum 2");
  const fragmentBeforeVote = await program.account.fragment.fetch(fragment);
  const round = Number(fragmentBeforeVote.round?.toString?.() ?? fragmentBeforeVote.round);
  const vote = votePda(fragment, verifier.publicKey, round);
  const vote2 = votePda(fragment, verifier2.publicKey, round);
  const resolution = roundResolutionPda(fragment, round);

  const voteSig = await program.methods
    .voteFragment(true)
    .accounts({
      verifier: verifier.publicKey,
      job,
      fragment,
      verifierWorker: verifierWorkerAccount,
      computeWorker: computeWorkerAccount,
      vote,
      roundResolution: resolution,
      escrowAuth,
      escrow: escrow.publicKey,
      workerToken: computeWorkerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier])
    .rpc();

  console.log("voteFragment YES verifier 1 tx:", voteSig);

  const vote2Sig = await program.methods
    .voteFragment(true)
    .accounts({
      verifier: verifier2.publicKey,
      job,
      fragment,
      verifierWorker: verifier2WorkerAccount,
      computeWorker: computeWorkerAccount,
      vote: vote2,
      roundResolution: resolution,
      escrowAuth,
      escrow: escrow.publicKey,
      workerToken: computeWorkerToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier2])
    .rpc();

  console.log("voteFragment YES verifier 2 tx:", vote2Sig);

  logStep("Claim verifier rewards");
  const claimRewardSig = await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: verifier.publicKey,
      job,
      fragment,
      roundResolution: resolution,
      vote,
      verifierWorker: verifierWorkerAccount,
      escrowAuth,
      escrow: escrow.publicKey,
      verifierToken,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier])
    .rpc();

  console.log("claimVerifierReward verifier 1 tx:", claimRewardSig);

  const claimReward2Sig = await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: verifier2.publicKey,
      job,
      fragment,
      roundResolution: resolution,
      vote: vote2,
      verifierWorker: verifier2WorkerAccount,
      escrowAuth,
      escrow: escrow.publicKey,
      verifierToken: verifier2Token,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier2])
    .rpc();

  console.log("claimVerifierReward verifier 2 tx:", claimReward2Sig);

  logStep("Final state");
  const jobState = await program.account.job.fetch(job);
  const fragmentState = await program.account.fragment.fetch(fragment);
  const computeState = await program.account.worker.fetch(computeWorkerAccount);
  const verifierState = await program.account.worker.fetch(verifierWorkerAccount);
  const verifier2State = await program.account.worker.fetch(verifier2WorkerAccount);
  const computeTokenAfter = await getAccount(connection, computeWorkerToken);
  const verifierTokenAfter = await getAccount(connection, verifierToken);
  const verifier2TokenAfter = await getAccount(connection, verifier2Token);

  console.log("job:", {
    expectedFragments: Number(jobState.expectedFragments?.toString?.() ?? jobState.expectedFragments),
    verifiedFragments: Number(jobState.verifiedFragments?.toString?.() ?? jobState.verifiedFragments),
    status: jobState.status,
  });
  console.log("fragment:", {
    status: fragmentState.status,
    yesVotes: Number(fragmentState.yesVotes?.toString?.() ?? fragmentState.yesVotes),
    noVotes: Number(fragmentState.noVotes?.toString?.() ?? fragmentState.noVotes),
  });
  console.log("compute worker:", {
    reputation: Number(computeState.reputation?.toString?.() ?? computeState.reputation),
    stakeAmount: Number(computeState.stakeAmount?.toString?.() ?? computeState.stakeAmount),
  });
  console.log("verifier 1 worker:", {
    reputation: Number(verifierState.reputation?.toString?.() ?? verifierState.reputation),
    stakeAmount: Number(verifierState.stakeAmount?.toString?.() ?? verifierState.stakeAmount),
  });
  console.log("verifier 2 worker:", {
    reputation: Number(verifier2State.reputation?.toString?.() ?? verifier2State.reputation),
    stakeAmount: Number(verifier2State.stakeAmount?.toString?.() ?? verifier2State.stakeAmount),
  });
  console.log("compute token amount:", computeTokenAfter.amount.toString());
  console.log("verifier 1 token amount:", verifierTokenAfter.amount.toString());
  console.log("verifier 2 token amount:", verifier2TokenAfter.amount.toString());

  console.log("\n✅ Devnet minimal job flow passed");
}

main().catch((error) => {
  console.error("\n❌ Devnet minimal job flow failed");
  console.error(error);
  process.exit(1);
});
