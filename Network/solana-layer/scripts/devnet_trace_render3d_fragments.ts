import * as anchor from "@coral-xyz/anchor";
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  LAMPORTS_PER_SOL,
} from "@solana/web3.js";
import {
  TOKEN_PROGRAM_ID,
  createAssociatedTokenAccount,
  createMint,
  mintTo,
} from "@solana/spl-token";
import crypto from "crypto";
import fs from "fs";
import os from "os";
import path from "path";
import { SiliciumLayerSdk } from "../silicium-sdk/src";

const DEVNET_RPC = process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
const NETWORK_ROOT = path.resolve(__dirname, "..", "..");
const PROGRAM_ID = new PublicKey(
  process.env.SOLANA_LAYER_PROGRAM_ID ?? "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA",
);
const REWARD_PER_FRAGMENT = new anchor.BN(process.env.SILICIUM_DEMO_REWARD_PER_FRAGMENT ?? "1000000");
const VERIFIER_REWARD_PER_VOTE = new anchor.BN(process.env.SILICIUM_DEMO_VERIFIER_REWARD_PER_VOTE ?? "100000");
const FRAGMENT_QUORUM = Number(process.env.SILICIUM_DEMO_FRAGMENT_QUORUM ?? "2");
const TX_DELAY_MS = Number(process.env.SILICIUM_DEVNET_TX_DELAY_MS ?? "1200");

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function throttle() {
  if (TX_DELAY_MS > 0) {
    await sleep(TX_DELAY_MS);
  }
}

function resolveHome(value: string): string {
  return value.startsWith("~") ? path.join(os.homedir(), value.slice(1)) : value;
}

function readKeypair(filePath: string): Keypair {
  const resolved = resolveHome(filePath);
  if (!fs.existsSync(resolved)) {
    throw new Error(
      `solana_wallet_not_found:${resolved}. Create one with ` +
        "`solana-keygen new -o ~/.config/solana/id.json` or set ANCHOR_WALLET.",
    );
  }
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
  throw new Error("IDL not found. Expected solana-layer/target/idl/solana_layer.json or target/idl/solana_layer.json.");
}

function stableStringify(value: any): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    .join(",")}}`;
}

function hashBytes(value: any): number[] {
  const data = typeof value === "string" || Buffer.isBuffer(value) ? value : stableStringify(value);
  return Array.from(crypto.createHash("sha256").update(data).digest());
}

function hashHex(value: any): string {
  return Buffer.from(hashBytes(value)).toString("hex");
}

function hexToHash32(hex: string): number[] {
  const normalized = String(hex || "").replace(/^sha256:/, "");
  if (!/^[0-9a-fA-F]{64}$/.test(normalized)) return hashBytes(normalized);
  return Array.from(Buffer.from(normalized, "hex"));
}

function flattenSplitTree(node: any): any[] {
  if (!node || typeof node !== "object") return [];
  const children = Array.isArray(node.children) ? node.children : [];
  return [node, ...children.flatMap((child) => flattenSplitTree(child))];
}

function splitParents(summary: any): any[] {
  if (!summary.split_tree) return [];
  return flattenSplitTree(summary.split_tree).filter((node) => Array.isArray(node.children) && node.children.length > 0);
}

function leavesFromTree(summary: any): any[] {
  if (!summary.split_tree) return [];
  return flattenSplitTree(summary.split_tree).filter((node) => !Array.isArray(node.children) || node.children.length === 0);
}

async function fundParticipant(provider: anchor.AnchorProvider, to: PublicKey, label: string) {
  const tx = new anchor.web3.Transaction().add(
    SystemProgram.transfer({
      fromPubkey: provider.wallet.publicKey,
      toPubkey: to,
      lamports: 80_000_000,
    }),
  );
  const signature = await provider.sendAndConfirm(tx, []);
  console.log(`${label} fund tx:`, signature);
  return signature;
}

async function ensureWorkerRegistered(sdk: SiliciumLayerSdk, owner: Keypair, label: string) {
  const worker = sdk.pdas.worker(owner.publicKey);
  const info = await sdk.provider.connection.getAccountInfo(worker, "confirmed");
  if (info) {
    console.log(`${label} worker already registered:`, worker.toBase58());
    return worker;
  }
  const signature = await sdk.registerWorker({ worker: owner.publicKey, signers: [owner] });
  console.log(`${label} registerWorker tx:`, signature);
  return worker;
}

async function main() {
  const summaryPath = process.argv[2];
  if (!summaryPath) {
    throw new Error("usage: ts-node scripts/devnet_trace_render3d_fragments.ts <fragmented-demo-summary.json>");
  }
  const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
  if (!summary.success) {
    throw new Error("refusing to trace an unsuccessful fragmented demo");
  }
  const fragments = Array.isArray(summary.fragments) ? summary.fragments : [];
  if (fragments.length === 0) {
    throw new Error("summary has no fragments");
  }
  if (FRAGMENT_QUORUM < 2) {
    throw new Error("fragment quorum must be at least 2 for the current Solana program");
  }

  const walletPath = process.env.ANCHOR_WALLET ?? path.join(NETWORK_ROOT, ".silicium", "solana", "id.json");
  const payer = readKeypair(walletPath);
  const connection = new Connection(DEVNET_RPC, "confirmed");
  const provider = new anchor.AnchorProvider(connection, new anchor.Wallet(payer), {
    commitment: "confirmed",
    preflightCommitment: "confirmed",
  });
  anchor.setProvider(provider);
  const program = new (anchor as any).Program(loadIdl(), provider) as any;
  const sdk = new SiliciumLayerSdk({ provider, program });

  console.log("rpc:", DEVNET_RPC);
  console.log("program:", PROGRAM_ID.toBase58());
  console.log("wallet:", provider.wallet.publicKey.toBase58());
  console.log("balance:", (await connection.getBalance(provider.wallet.publicKey)) / LAMPORTS_PER_SOL, "SOL");

  const programInfo = await connection.getAccountInfo(PROGRAM_ID, "confirmed");
  if (!programInfo?.executable) {
    throw new Error(`Program not found or not executable on Devnet: ${PROGRAM_ID.toBase58()}`);
  }

  const mint = await createMint(connection, payer, provider.wallet.publicKey, null, 6);
  const clientToken = await createAssociatedTokenAccount(connection, payer, mint, provider.wallet.publicKey);
  await mintTo(connection, payer, mint, clientToken, provider.wallet.publicKey, 50_000_000);

  const computeWorker = Keypair.generate();
  const verifier1 = Keypair.generate();
  const verifier2 = Keypair.generate();
  await fundParticipant(provider, computeWorker.publicKey, "compute worker");
  await throttle();
  await fundParticipant(provider, verifier1.publicKey, "verifier 1");
  await throttle();
  await fundParticipant(provider, verifier2.publicKey, "verifier 2");
  await throttle();

  const computeToken = await createAssociatedTokenAccount(connection, payer, mint, computeWorker.publicKey);
  const verifier1Token = await createAssociatedTokenAccount(connection, payer, mint, verifier1.publicKey);
  const verifier2Token = await createAssociatedTokenAccount(connection, payer, mint, verifier2.publicKey);
  await mintTo(connection, payer, mint, computeToken, provider.wallet.publicKey, 10_000_000);
  await mintTo(connection, payer, mint, verifier1Token, provider.wallet.publicKey, 10_000_000);
  await mintTo(connection, payer, mint, verifier2Token, provider.wallet.publicKey, 10_000_000);

  const computeWorkerAccount = await ensureWorkerRegistered(sdk, computeWorker, "compute");
  await throttle();
  await sdk.stakeWorker({ worker: computeWorker.publicKey, mint, workerToken: computeToken, amount: 1_000_000, signers: [computeWorker] });
  await throttle();
  const verifier1WorkerAccount = await ensureWorkerRegistered(sdk, verifier1, "verifier 1");
  await throttle();
  await sdk.stakeWorker({ worker: verifier1.publicKey, mint, workerToken: verifier1Token, amount: 1_000_000, signers: [verifier1] });
  await throttle();
  const verifier2WorkerAccount = await ensureWorkerRegistered(sdk, verifier2, "verifier 2");
  await throttle();
  await sdk.stakeWorker({ worker: verifier2.publicKey, mint, workerToken: verifier2Token, amount: 1_000_000, signers: [verifier2] });
  await throttle();

  const hasSplitTree = Boolean(summary.split_tree);
  const splitParentNodes = splitParents(summary);
  const treeLeaves = leavesFromTree(summary);
  const expectedInitialFragments = hasSplitTree ? 1 : fragments.length;

  const escrow = Keypair.generate();
  const jobId = new anchor.BN(Date.now());
  const verifierRewardBudget = VERIFIER_REWARD_PER_VOTE.mul(new anchor.BN(FRAGMENT_QUORUM * fragments.length));
  const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);
  const created = await sdk.createJob({
    mint,
    clientToken,
    escrow,
    jobId,
    expectedFragments: expectedInitialFragments,
    rewardPerFragment: REWARD_PER_FRAGMENT,
    verifierRewardPerVote: VERIFIER_REWARD_PER_VOTE,
    verifierRewardBudget,
    deadlineUnix,
    fragmentQuorum: FRAGMENT_QUORUM,
  });
  await throttle();

  const storageManifest = {
    schema_version: 1,
    source_summary_path: path.resolve(summaryPath),
    job_id: summary.job_id,
    fragment_count: fragments.length,
    split_tree: summary.split_tree,
    fragments: fragments.map((fragment: any) => ({
      fragment_index: fragment.fragment_index,
      output_ref: fragment.compute_output_ref,
      result_hash: fragment.compute_result_hash,
      y_start: fragment.y_start,
      y_end: fragment.y_end,
    })),
    reassembled_png: summary.reassembled_png,
    reassembled_hash: summary.reassembled_hash,
  };
  const storageDeclared = await sdk.declareJobStorage({
    job: created.job,
    manifestHash: hashBytes(storageManifest),
    inputRootHash: hashBytes(fragments.map((fragment: any) => fragment.expected_hash).join(":")),
    storageRefHash: hashBytes({ protocol: "file", summary_path: path.resolve(summaryPath) }),
  });
  await throttle();

  const splitTraces = [];
  const splitFragmentByIndex = new Map<number, PublicKey>();
  if (hasSplitTree) {
    const root = summary.split_tree;
    const rootIndex = Number(root.fragment_index ?? 0);
    const rootClaim = await sdk.claimFragment({
      worker: computeWorker.publicKey,
      job: created.job,
      fragmentIndex: rootIndex,
      workerToken: computeToken,
      signers: [computeWorker],
    });
    splitFragmentByIndex.set(rootIndex, rootClaim.fragment);
    splitTraces.push({
      fragment_index: rootIndex,
      action: "claim_split_root",
      fragment: rootClaim.fragment.toBase58(),
      signature: rootClaim.signature,
    });
    await throttle();

    for (const parent of splitParentNodes) {
      const parentIndex = Number(parent.fragment_index);
      const parentFragment = splitFragmentByIndex.get(parentIndex) ?? sdk.pdas.fragment(created.job, parentIndex);
      const children = Array.isArray(parent.children) ? parent.children : [];
      const manifest = {
        schema_version: 1,
        job_id: summary.job_id,
        parent_index: parentIndex,
        depth: parent.depth,
        complexity_score: parent.complexity_score,
        children: children.map((child: any) => ({
          fragment_index: child.fragment_index,
          y_start: child.y_start,
          y_end: child.y_end,
          depth: child.depth,
          complexity_score: child.complexity_score,
        })),
      };
      const proposed = await sdk.proposeFragmentSplit({
        splitter: computeWorker.publicKey,
        job: created.job,
        parentFragment,
        parentFragmentIndex: parentIndex,
        manifestHash: hashBytes(manifest),
        childCount: children.length,
        signers: [computeWorker],
      });
      await throttle();
      const approved = await sdk.approveFragmentSplit({
        job: created.job,
        parentFragment,
        parentFragmentIndex: parentIndex,
        splitProposal: proposed.splitProposal,
        approve: true,
      });
      await throttle();
      const childTraces = [];
      for (const child of children) {
        const childIndex = Number(child.fragment_index);
        const createdChild = await sdk.createSubFragment({
          job: created.job,
          parentFragment,
          parentFragmentIndex: parentIndex,
          splitProposal: proposed.splitProposal,
          childFragmentIndex: childIndex,
          requiredComputeReputation: new anchor.BN(1500),
          requiredStake: new anchor.BN(1),
          complexityScore: Number(child.complexity_score ?? 1000),
          inputHash: hashBytes({
            job_id: summary.job_id,
            fragment_index: childIndex,
            parent_index: parentIndex,
            y_start: child.y_start,
            y_end: child.y_end,
          }),
        });
        splitFragmentByIndex.set(childIndex, createdChild.childFragment);
        childTraces.push({
          fragment_index: childIndex,
          fragment: createdChild.childFragment.toBase58(),
          signature: createdChild.signature,
        });
        await throttle();

        if (Array.isArray(child.children) && child.children.length > 0) {
          const childClaim = await sdk.claimFragment({
            worker: computeWorker.publicKey,
            job: created.job,
            fragmentIndex: childIndex,
            workerToken: computeToken,
            signers: [computeWorker],
          });
          splitTraces.push({
            fragment_index: childIndex,
            action: "claim_split_child",
            fragment: childClaim.fragment.toBase58(),
            signature: childClaim.signature,
          });
          await throttle();
        }
      }
      splitTraces.push({
        fragment_index: parentIndex,
        parent_fragment: parentFragment.toBase58(),
        split_proposal: proposed.splitProposal.toBase58(),
        child_count: children.length,
        signatures: {
          propose_fragment_split: proposed.signature,
          approve_fragment_split: approved.signature,
        },
        children: childTraces,
      });
    }

    const leafIndexes = new Set(treeLeaves.map((node: any) => Number(node.fragment_index)));
    const summaryLeafIndexes = new Set(fragments.map((fragment: any) => Number(fragment.fragment_index)));
    if (leafIndexes.size !== summaryLeafIndexes.size || Array.from(leafIndexes).some((index) => !summaryLeafIndexes.has(index))) {
      throw new Error("split tree leaves do not match computed summary fragments");
    }
  }

  const fragmentTraces = [];
  for (const fragment of fragments) {
    const index = Number(fragment.fragment_index);
    let claimedFragment = splitFragmentByIndex.get(index);
    let claimSignature = "";
    if (!claimedFragment) {
      const claimed = await sdk.claimFragment({
        worker: computeWorker.publicKey,
        job: created.job,
        fragmentIndex: index,
        workerToken: computeToken,
        signers: [computeWorker],
      });
      claimedFragment = claimed.fragment;
      claimSignature = claimed.signature;
      await throttle();
    } else {
      const claimed = await sdk.claimFragment({
        worker: computeWorker.publicKey,
        job: created.job,
        fragmentIndex: index,
        workerToken: computeToken,
        signers: [computeWorker],
      });
      claimedFragment = claimed.fragment;
      claimSignature = claimed.signature;
      await throttle();
    }
    const submitted = await sdk.submitFragmentResult({
      worker: computeWorker.publicKey,
      job: created.job,
      fragmentIndex: index,
      workerToken: computeToken,
      resultHash: hexToHash32(fragment.compute_result_hash),
      proofRef: hashBytes(fragment.compute_output_ref),
      signers: [computeWorker],
    });
    await throttle();
    const voted1 = await sdk.voteFragment({
      verifier: verifier1.publicKey,
      job: created.job,
      fragment: claimedFragment,
      escrow: escrow.publicKey,
      workerToken: computeToken,
      computeWorker: computeWorker.publicKey,
      choice: Boolean(fragment.verify_choice),
      signers: [verifier1],
    });
    await throttle();
    const voted2 = await sdk.voteFragment({
      verifier: verifier2.publicKey,
      job: created.job,
      fragment: claimedFragment,
      escrow: escrow.publicKey,
      workerToken: computeToken,
      computeWorker: computeWorker.publicKey,
      choice: Boolean(fragment.verify_choice),
      signers: [verifier2],
    });
    await throttle();
    const reward1 = await sdk.claimVerifierReward({
      verifier: verifier1.publicKey,
      job: created.job,
      fragment: claimedFragment,
      escrow: escrow.publicKey,
      verifierToken: verifier1Token,
      signers: [verifier1],
    });
    await throttle();
    const reward2 = await sdk.claimVerifierReward({
      verifier: verifier2.publicKey,
      job: created.job,
      fragment: claimedFragment,
      escrow: escrow.publicKey,
      verifierToken: verifier2Token,
      signers: [verifier2],
    });
    await throttle();
    fragmentTraces.push({
      fragment_index: index,
      fragment: claimedFragment.toBase58(),
      result_hash: fragment.compute_result_hash,
      signatures: {
        claim_fragment: claimSignature,
        submit_fragment_result: submitted,
        vote_1: voted1.signature,
        vote_2: voted2.signature,
        claim_verifier_reward_1: reward1,
        claim_verifier_reward_2: reward2,
      },
    });
  }

  const finalized = await sdk.finalizeJob({
    job: created.job,
    escrow: escrow.publicKey,
    clientToken,
    finalHash: hexToHash32(summary.reassembled_hash),
    outputUri: summary.reassembled_png || summary.reassembled_ppm || "",
  });
  await throttle();

  const trace = {
    schema_version: 1,
    success: true,
    source_summary_path: path.resolve(summaryPath),
    rpc: DEVNET_RPC,
    program_id: PROGRAM_ID.toBase58(),
    wallet: provider.wallet.publicKey.toBase58(),
    mint: mint.toBase58(),
    client_token: clientToken.toBase58(),
    job: created.job.toBase58(),
    escrow: escrow.publicKey.toBase58(),
    job_storage: storageDeclared.jobStorage.toBase58(),
    compute_worker: computeWorker.publicKey.toBase58(),
    compute_worker_account: computeWorkerAccount.toBase58(),
    verifiers: [
      { owner: verifier1.publicKey.toBase58(), worker_account: verifier1WorkerAccount.toBase58(), token: verifier1Token.toBase58() },
      { owner: verifier2.publicKey.toBase58(), worker_account: verifier2WorkerAccount.toBase58(), token: verifier2Token.toBase58() },
    ],
    split_tree: summary.split_tree,
    split_traces: splitTraces,
    signatures: {
      create_job: created.signature,
      declare_job_storage: storageDeclared.signature,
      finalize_job: finalized.signature,
    },
    fragments: fragmentTraces,
    final_hash: summary.reassembled_hash,
    output_uri: summary.reassembled_png || summary.reassembled_ppm || "",
    finished_utc: new Date().toISOString(),
  };

  const outPath = process.env.SILICIUM_TRACE_RESULT_PATH || path.join(path.dirname(summaryPath), "devnet-trace.json");
  fs.writeFileSync(outPath, JSON.stringify(trace, null, 2), "utf8");
  console.log(JSON.stringify(trace, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
