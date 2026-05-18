/**
 * Silicium Solana Layer — Devnet minimal V2.5 write flow
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
 * - creates a fresh test SPL mint
 * - creates a fresh compute worker and two fresh verifiers
 * - registers/stakes all active participants
 * - creates a 1-fragment job with quorum = 2
 * - compute worker claims/submits fragment 0
 * - both verifiers vote YES
 * - both verifiers claim rewards
 * - prints V2.5 compute/verify/global reputation state
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
import crypto from "crypto";
import os from "os";
import path from "path";

const DEVNET_RPC = process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
const PROGRAM_ID = new PublicKey(
  process.env.SOLANA_LAYER_PROGRAM_ID ?? "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2",
);

const STAKE_AMOUNT = new anchor.BN(1_000_000);
const REWARD_PER_FRAGMENT = new anchor.BN(1_000_000);
const VERIFIER_REWARD_PER_VOTE = new anchor.BN(100_000);
const VERIFIER_REWARD_BUDGET = new anchor.BN(200_000);
const FRAGMENT_QUORUM = 2;

function logStep(title: string) {
  console.log(`\n=== ${title} ===`);
}

function readKeypair(filePath: string): Keypair {
  const resolved = filePath.startsWith("~")
    ? path.join(os.homedir(), filePath.slice(1))
    : filePath;

  return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(resolved, "utf8"))));
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

function rep(value: any): number {
  return Number(value?.toString?.() ?? value ?? 0);
}

function stableStringify(value: any): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    .join(",")}}`;
}

function hash32(value: any): number[] {
  return Array.from(crypto.createHash("sha256").update(stableStringify(value)).digest());
}

function workerSummary(state: any) {
  return {
    computeReputation: rep(state.computeReputation),
    verifyReputation: rep(state.verifyReputation),
    globalReputation: rep(state.globalReputation),
    stakeAmount: rep(state.stakeAmount),
    totalSubmitted: rep(state.totalSubmitted),
    totalVerified: rep(state.totalVerified),
    totalRejected: rep(state.totalRejected),
    activeClaims: rep(state.activeClaims),
    status: state.status,
  };
}

async function fundParticipant(provider: anchor.AnchorProvider, to: PublicKey, label: string) {
  const tx = new anchor.web3.Transaction().add(
    SystemProgram.transfer({
      fromPubkey: provider.wallet.publicKey,
      toPubkey: to,
      lamports: 80_000_000,
    }),
  );
  const sig = await provider.sendAndConfirm(tx, []);
  console.log(`${label} fund tx:`, sig);
}

async function ensureWorkerRegistered(program: any, owner: Keypair, label: string): Promise<PublicKey> {
  const workerAccount = workerPda(owner.publicKey);
  const info = await program.provider.connection.getAccountInfo(workerAccount, "confirmed");

  if (info) {
    const state = await program.account.worker.fetch(workerAccount);
    console.log(`${label} worker already registered:`, {
      workerAccount: workerAccount.toBase58(),
      ...workerSummary(state),
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

  const taskPayload = JSON.parse(process.env.SILICIUM_CHAIN_TASK_JSON ?? '{"kind":"compute","payload":"hello-chain"}');
  const resultPayload = {
    task: taskPayload,
    result: {
      mode: "deterministic-devnet-flow",
      ok: true,
    },
  };
  const resultHash = hash32(resultPayload);
  const proofRef = hash32({
    script: "devnet_minimal_job_flow.ts",
    resultHash,
  });
  console.log("task:", stableStringify(taskPayload));

  const programInfo = await connection.getAccountInfo(PROGRAM_ID, "confirmed");
  if (!programInfo?.executable) {
    throw new Error(`Program not found or not executable on Devnet: ${PROGRAM_ID.toBase58()}`);
  }

  if ((await connection.getBalance(wallet.publicKey)) < 0.5 * LAMPORTS_PER_SOL) {
    throw new Error("Wallet balance is low. Add Devnet SOL before running this write flow.");
  }

  logStep("Create test SPL mint and token accounts");
  const mint = await createMint(connection, payer, wallet.publicKey, null, 6);
  console.log("mint:", mint.toBase58());

  const clientToken = await createAssociatedTokenAccount(connection, payer, mint, wallet.publicKey);
  await mintTo(connection, payer, mint, clientToken, wallet.publicKey, 30_000_000);
  console.log("client token:", clientToken.toBase58());
  console.log("minted 30 tokens to client token account");

  const computeWorker = Keypair.generate();
  const verifier1 = Keypair.generate();
  const verifier2 = Keypair.generate();

  await fundParticipant(provider, computeWorker.publicKey, "compute worker");
  await fundParticipant(provider, verifier1.publicKey, "verifier 1");
  await fundParticipant(provider, verifier2.publicKey, "verifier 2");

  const computeToken = await createAssociatedTokenAccount(connection, payer, mint, computeWorker.publicKey);
  const verifier1Token = await createAssociatedTokenAccount(connection, payer, mint, verifier1.publicKey);
  const verifier2Token = await createAssociatedTokenAccount(connection, payer, mint, verifier2.publicKey);

  await mintTo(connection, payer, mint, computeToken, wallet.publicKey, 5_000_000);
  await mintTo(connection, payer, mint, verifier1Token, wallet.publicKey, 5_000_000);
  await mintTo(connection, payer, mint, verifier2Token, wallet.publicKey, 5_000_000);

  console.log("compute worker:", computeWorker.publicKey.toBase58());
  console.log("compute token:", computeToken.toBase58());
  console.log("verifier 1:", verifier1.publicKey.toBase58());
  console.log("verifier 1 token:", verifier1Token.toBase58());
  console.log("verifier 2:", verifier2.publicKey.toBase58());
  console.log("verifier 2 token:", verifier2Token.toBase58());

  logStep("Register and stake compute worker + two verifiers");
  const computeWorkerAccount = await ensureWorkerRegistered(program, computeWorker, "compute");
  await stakeWorker(program, computeWorker, computeWorkerAccount, mint, computeToken, "compute");

  const verifier1WorkerAccount = await ensureWorkerRegistered(program, verifier1, "verifier 1");
  await stakeWorker(program, verifier1, verifier1WorkerAccount, mint, verifier1Token, "verifier 1");

  const verifier2WorkerAccount = await ensureWorkerRegistered(program, verifier2, "verifier 2");
  await stakeWorker(program, verifier2, verifier2WorkerAccount, mint, verifier2Token, "verifier 2");

  logStep("Create one-fragment job with quorum = 2");
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
      FRAGMENT_QUORUM,
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
      workerToken: computeToken,
      systemProgram: SystemProgram.programId,
    })
    .signers([computeWorker])
    .rpc();

  console.log("claimFragment tx:", claimSig);

  const submitSig = await program.methods
    .submitFragmentResult(0, resultHash, proofRef)
    .accounts({
      worker: computeWorker.publicKey,
      workerAccount: computeWorkerAccount,
      job,
      fragment,
      workerToken: computeToken,
    })
    .signers([computeWorker])
    .rpc();

  console.log("submitFragmentResult tx:", submitSig);

  logStep("Two verifiers vote YES");
  const fragmentBeforeVote = await program.account.fragment.fetch(fragment);
  const round = Number(fragmentBeforeVote.round?.toString?.() ?? fragmentBeforeVote.round);
  const resolution = roundResolutionPda(fragment, round);

  const vote1 = votePda(fragment, verifier1.publicKey, round);
  const vote1Sig = await program.methods
    .voteFragment(true)
    .accounts({
      verifier: verifier1.publicKey,
      job,
      fragment,
      verifierWorker: verifier1WorkerAccount,
      computeWorker: computeWorkerAccount,
      vote: vote1,
      roundResolution: resolution,
      escrowAuth,
      escrow: escrow.publicKey,
      workerToken: computeToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier1])
    .rpc();

  console.log("verifier 1 vote YES tx:", vote1Sig);

  const vote2 = votePda(fragment, verifier2.publicKey, round);
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
      workerToken: computeToken,
      tokenProgram: TOKEN_PROGRAM_ID,
      systemProgram: SystemProgram.programId,
    })
    .signers([verifier2])
    .rpc();

  console.log("verifier 2 vote YES tx:", vote2Sig);

  logStep("Claim verifier rewards");
  const claimReward1Sig = await program.methods
    .claimVerifierReward()
    .accounts({
      verifier: verifier1.publicKey,
      job,
      fragment,
      roundResolution: resolution,
      vote: vote1,
      verifierWorker: verifier1WorkerAccount,
      escrowAuth,
      escrow: escrow.publicKey,
      verifierToken: verifier1Token,
      tokenProgram: TOKEN_PROGRAM_ID,
    })
    .signers([verifier1])
    .rpc();

  console.log("verifier 1 claimVerifierReward tx:", claimReward1Sig);

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

  console.log("verifier 2 claimVerifierReward tx:", claimReward2Sig);

  logStep("Final state");
  const jobState = await program.account.job.fetch(job);
  const fragmentState = await program.account.fragment.fetch(fragment);
  const computeState = await program.account.worker.fetch(computeWorkerAccount);
  const verifier1State = await program.account.worker.fetch(verifier1WorkerAccount);
  const verifier2State = await program.account.worker.fetch(verifier2WorkerAccount);
  const clientTokenAfter = await getAccount(connection, clientToken);
  const computeTokenAfter = await getAccount(connection, computeToken);
  const verifier1TokenAfter = await getAccount(connection, verifier1Token);
  const verifier2TokenAfter = await getAccount(connection, verifier2Token);

  console.log("job:", {
    expectedFragments: rep(jobState.expectedFragments),
    verifiedFragments: rep(jobState.verifiedFragments),
    status: jobState.status,
  });
  console.log("fragment:", {
    status: fragmentState.status,
    yesVotes: rep(fragmentState.yesVotes),
    noVotes: rep(fragmentState.noVotes),
  });
  console.log("compute worker:", workerSummary(computeState));
  console.log("verifier 1 worker:", workerSummary(verifier1State));
  console.log("verifier 2 worker:", workerSummary(verifier2State));
  console.log("client token amount:", clientTokenAfter.amount.toString());
  console.log("compute token amount:", computeTokenAfter.amount.toString());
  console.log("verifier 1 token amount:", verifier1TokenAfter.amount.toString());
  console.log("verifier 2 token amount:", verifier2TokenAfter.amount.toString());

  console.log("\n✅ Devnet minimal V2.5 job flow passed");
}

main().catch((error) => {
  console.error("\n❌ Devnet minimal V2.5 job flow failed");
  console.error(error);
  process.exit(1);
});
