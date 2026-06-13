#!/usr/bin/env node
"use strict";

const fs = require("fs");
const Module = require("module");
const os = require("os");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..");
const solanaLayerDir = path.join(repoRoot, "solana-layer");
const solanaNodeModules = path.join(solanaLayerDir, "node_modules");
process.env.NODE_PATH = [solanaNodeModules, process.env.NODE_PATH || ""].filter(Boolean).join(path.delimiter);
Module._initPaths();
require(path.join(__dirname, "node_uuid_cjs_shim.cjs"));

const anchor = require("@coral-xyz/anchor");
const { Connection, Keypair, PublicKey } = require("@solana/web3.js");

const sdk = require(path.join(solanaLayerDir, "silicium-sdk", "dist", "index.js"));

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function resolveHome(value) {
  if (!value) return value;
  return value.startsWith("~") ? path.join(os.homedir(), value.slice(1)) : value;
}

function readKeypair(filePath) {
  const resolved = resolveHome(filePath);
  return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(resolved, "utf8"))));
}

function readKeypairPubkey(filePath) {
  return readKeypair(filePath).publicKey;
}

function loadIdl(programId) {
  const candidates = [
    path.join(solanaLayerDir, "target", "idl", "solana_layer.json"),
    path.join(repoRoot, "target", "idl", "solana_layer.json"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      const idl = JSON.parse(fs.readFileSync(candidate, "utf8"));
      idl.address = programId.toBase58();
      return idl;
    }
  }
  throw new Error("solana_layer_idl_not_found");
}

function publicKey(value, field) {
  if (!value) throw new Error(`missing_${field}`);
  return new PublicKey(value);
}

function hash32(value, field) {
  if (Array.isArray(value)) {
    if (value.length !== 32) throw new Error(`${field}_must_be_32_bytes`);
    return value.map((item) => Number(item));
  }
  if (typeof value !== "string") throw new Error(`${field}_must_be_string_or_32_byte_array`);

  const normalized = value.startsWith("sha256:") ? value.slice("sha256:".length) : value;
  if (/^[0-9a-fA-F]{64}$/.test(normalized)) {
    return Array.from(Buffer.from(normalized, "hex"));
  }
  return Array.from(crypto.createHash("sha256").update(value).digest());
}

function optionalHash32(value) {
  return value === undefined || value === null || value === "" ? undefined : hash32(value, "optional_hash");
}

function resultAccounts(result) {
  const out = {};
  for (const [key, value] of Object.entries(result || {})) {
    if (value && typeof value.toBase58 === "function") {
      out[key] = value.toBase58();
    }
  }
  return out;
}

async function createContext(request) {
  const programId = publicKey(request.program_id, "program_id");
  const payer = readKeypair(request.wallet_path);
  const connection = new Connection(request.rpc_url, "confirmed");
  const provider = new anchor.AnchorProvider(connection, new anchor.Wallet(payer), {
    commitment: "confirmed",
    preflightCommitment: "confirmed",
  });
  anchor.setProvider(provider);
  const program = new anchor.Program(loadIdl(programId), provider);
  return {
    connection,
    payer,
    provider,
    program,
    layer: new sdk.SiliciumLayerSdk({ provider, program }),
  };
}

async function handle(request) {
  const params = request.params || {};
  const { layer, program } = await createContext(request);
  const signatures = [];
  let accounts = {};

  if (request.op === "register_worker") {
    const worker = layer.pdas.worker(layer.walletPubkey());
    accounts.worker = worker.toBase58();
    const existing = await program.provider.connection.getAccountInfo(worker, "confirmed");
    if (existing) {
      return { signatures, accounts, already_registered: true };
    }
    signatures.push(await layer.registerWorker({}));
    return { signatures, accounts, already_registered: false };
  }

  if (request.op === "create_job") {
    const escrow = readKeypair(params.escrow_keypair_path || params.escrowKeypairPath);
    const result = await layer.createJob({
      mint: publicKey(params.mint, "mint"),
      clientToken: publicKey(params.client_token || params.clientToken, "client_token"),
      escrow,
      jobId: params.job_id ?? params.jobId,
      expectedFragments: Number(params.expected_fragments ?? params.expectedFragments),
      rewardPerFragment: params.reward_per_fragment ?? params.rewardPerFragment,
      verifierRewardPerVote: params.verifier_reward_per_vote ?? params.verifierRewardPerVote ?? 0,
      verifierRewardBudget: params.verifier_reward_budget ?? params.verifierRewardBudget ?? 0,
      deadlineUnix: params.deadline_unix ?? params.deadlineUnix,
      fragmentQuorum: Number(params.fragment_quorum ?? params.fragmentQuorum ?? 1),
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "declare_storage") {
    const result = await layer.declareJobStorage({
      job: publicKey(params.job, "job"),
      manifestHash: hash32(params.manifest_hash || params.manifestHash, "manifest_hash"),
      inputRootHash: hash32(params.input_root_hash || params.inputRootHash, "input_root_hash"),
      storageRefHash: hash32(params.storage_ref_hash || params.storageRefHash, "storage_ref_hash"),
      encryptionRefHash: optionalHash32(params.encryption_ref_hash || params.encryptionRefHash),
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "claim_fragment" || request.op === "claim_and_submit_fragment") {
    if (!params.skip_claim) {
      const claimed = await layer.claimFragment({
        job: publicKey(params.job, "job"),
        fragmentIndex: Number(params.fragment_index ?? params.fragmentIndex),
        workerToken: publicKey(params.worker_token || params.workerToken, "worker_token"),
      });
      signatures.push(claimed.signature);
      accounts = { ...accounts, ...resultAccounts(claimed) };
    }
    if (request.op === "claim_fragment") {
      return { signatures, accounts };
    }
  }

  if (request.op === "submit_fragment_result" || request.op === "claim_and_submit_fragment") {
    const signature = await layer.submitFragmentResult({
      job: publicKey(params.job, "job"),
      fragmentIndex: Number(params.fragment_index ?? params.fragmentIndex),
      workerToken: publicKey(params.worker_token || params.workerToken, "worker_token"),
      resultHash: hash32(params.result_hash || params.resultHash, "result_hash"),
      proofRef: hash32(params.proof_ref || params.proofRef, "proof_ref"),
    });
    signatures.push(signature);
    return { signatures, accounts };
  }

  if (request.op === "propose_fragment_split") {
    const result = await layer.proposeFragmentSplit({
      job: publicKey(params.job, "job"),
      parentFragment: params.parent_fragment || params.parentFragment ? publicKey(params.parent_fragment || params.parentFragment, "parent_fragment") : undefined,
      parentFragmentIndex: Number(params.parent_fragment_index ?? params.parentFragmentIndex ?? params.fragment_index ?? params.fragmentIndex),
      manifestHash: hash32(params.manifest_hash || params.manifestHash, "manifest_hash"),
      childCount: Number(params.child_count ?? params.childCount),
      round: params.round === undefined || params.round === null ? undefined : Number(params.round),
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "approve_fragment_split") {
    const result = await layer.approveFragmentSplit({
      job: publicKey(params.job, "job"),
      parentFragment: params.parent_fragment || params.parentFragment ? publicKey(params.parent_fragment || params.parentFragment, "parent_fragment") : undefined,
      parentFragmentIndex: Number(params.parent_fragment_index ?? params.parentFragmentIndex ?? params.fragment_index ?? params.fragmentIndex),
      splitProposal: params.split_proposal || params.splitProposal ? publicKey(params.split_proposal || params.splitProposal, "split_proposal") : undefined,
      approve: params.approve !== false,
      round: params.round === undefined || params.round === null ? undefined : Number(params.round),
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "create_sub_fragment") {
    const result = await layer.createSubFragment({
      job: publicKey(params.job, "job"),
      parentFragment: params.parent_fragment || params.parentFragment ? publicKey(params.parent_fragment || params.parentFragment, "parent_fragment") : undefined,
      parentFragmentIndex: Number(params.parent_fragment_index ?? params.parentFragmentIndex),
      splitProposal: params.split_proposal || params.splitProposal ? publicKey(params.split_proposal || params.splitProposal, "split_proposal") : undefined,
      childFragmentIndex: Number(params.child_fragment_index ?? params.childFragmentIndex),
      requiredComputeReputation: params.required_compute_reputation ?? params.requiredComputeReputation ?? 1500,
      requiredStake: params.required_stake ?? params.requiredStake ?? 1,
      complexityScore: Number(params.complexity_score ?? params.complexityScore ?? 1000),
      inputHash: hash32(params.input_hash || params.inputHash, "input_hash"),
      round: params.round === undefined || params.round === null ? undefined : Number(params.round),
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "vote_fragment") {
    const job = publicKey(params.job, "job");
    const fragment = params.fragment
      ? publicKey(params.fragment, "fragment")
      : layer.pdas.fragment(job, Number(params.fragment_index ?? params.fragmentIndex));
    const result = await layer.voteFragment({
      job,
      fragment,
      escrow: publicKey(params.escrow, "escrow"),
      workerToken: publicKey(params.worker_token || params.workerToken, "worker_token"),
      choice: params.choice !== false,
      computeWorker: params.compute_worker || params.computeWorker ? publicKey(params.compute_worker || params.computeWorker, "compute_worker") : undefined,
      round: params.round === undefined || params.round === null ? undefined : Number(params.round),
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "claim_verifier_reward") {
    const result = await layer.claimVerifierReward({
      job: publicKey(params.job, "job"),
      fragment: publicKey(params.fragment, "fragment"),
      escrow: publicKey(params.escrow, "escrow"),
      verifierToken: publicKey(params.verifier_token || params.verifierToken || params.worker_token || params.workerToken, "verifier_token"),
      round: params.round === undefined || params.round === null ? undefined : Number(params.round),
    });
    signatures.push(result);
    return { signatures, accounts };
  }

  if (request.op === "finalize_job") {
    const result = await layer.finalizeJob({
      job: publicKey(params.job, "job"),
      escrow: publicKey(params.escrow, "escrow"),
      clientToken: publicKey(params.client_token || params.clientToken, "client_token"),
      finalHash: hash32(params.final_hash || params.finalHash, "final_hash"),
      outputUri: params.output_uri || params.outputUri || "",
    });
    signatures.push(result.signature);
    accounts = resultAccounts(result);
    return { signatures, accounts };
  }

  if (request.op === "fetch_job") {
    const job = publicKey(params.job, "job");
    const account = await program.account.job.fetch(job);
    return { account: JSON.parse(JSON.stringify(account)), accounts: { job: job.toBase58() } };
  }

  if (request.op === "fetch_fragment") {
    const fragment = params.fragment
      ? publicKey(params.fragment, "fragment")
      : layer.pdas.fragment(publicKey(params.job, "job"), Number(params.fragment_index ?? params.fragmentIndex));
    const account = await program.account.fragment.fetch(fragment);
    return { account: JSON.parse(JSON.stringify(account)), accounts: { fragment: fragment.toBase58() } };
  }

  if (request.op === "fetch_worker") {
    const owner = params.owner ? publicKey(params.owner, "owner") : readKeypairPubkey(request.wallet_path);
    const worker = params.worker_account
      ? publicKey(params.worker_account, "worker_account")
      : layer.pdas.worker(owner);
    const account = await program.account.worker.fetch(worker);
    return { account: JSON.parse(JSON.stringify(account)), accounts: { worker: worker.toBase58(), owner: owner.toBase58() } };
  }

  throw new Error(`unsupported_op:${request.op}`);
}

(async () => {
  try {
    const raw = await readStdin();
    const request = JSON.parse(raw || "{}");
    const result = await handle(request);
    process.stdout.write(JSON.stringify({ ok: true, op: request.op, ...result }) + "\n");
  } catch (error) {
    process.stdout.write(
      JSON.stringify({
        ok: false,
        error: error && error.stack ? String(error.stack) : String(error),
      }) + "\n",
    );
    process.exitCode = 1;
  }
})();
