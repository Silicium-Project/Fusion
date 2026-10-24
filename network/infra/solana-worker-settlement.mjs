import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import {
  Connection,
  Keypair,
  PublicKey,
  SystemProgram,
  Transaction,
  TransactionInstruction,
} from '@solana/web3.js';
import { createAssociatedTokenAccountIdempotentInstruction } from '@solana/spl-token';

const PROGRAM_ID = new PublicKey(process.env.SILICIUM_SOLANA_PROGRAM_ID || '64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG');
const MINT = new PublicKey(process.env.SILICIUM_SOLANA_MINT || 'F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP');
const TOKEN_PROGRAM = new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');
const ATA_PROGRAM = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');
const RPC_URL = process.env.SILICIUM_SOLANA_RPC || 'https://api.devnet.solana.com';
const WALLET_PATH = process.env.SILICIUM_SOLANA_WALLET_PATH || '/data/solana-wallet.json';
const TOKEN_UNIT = 1_000_000n;
const MAX_FRAGMENTS = 1_000;
const MAX_FRAGMENT_NODES = 1_000;

function maxLeafFragments(initialFragments) {
  const childSlotsPerRoot = Math.floor((MAX_FRAGMENT_NODES - initialFragments) / initialFragments);
  return Math.min(initialFragments * 16, initialFragments * (1 + Math.floor(childSlotsPerRoot / 2)), MAX_FRAGMENTS);
}

class SettlementError extends Error {
  constructor(code) { super(code); this.code = code; }
}

const fail = code => { throw new SettlementError(code); };
const pda = (seeds) => PublicKey.findProgramAddressSync(seeds, PROGRAM_ID)[0];

function retryAfterMs(response) {
  const value = response.headers.get('retry-after');
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds * 1_000);
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - Date.now()) : null;
}

async function rateLimitAwareFetch(input, init) {
  for (let attempt = 0; ; attempt += 1) {
    const response = await fetch(input, init);
    if (response.status !== 429 || attempt >= 4) return response;
    const advertised = retryAfterMs(response);
    const fallback = Math.min(1_000 * (2 ** attempt), 15_000);
    const delay = Math.min(30_000, Math.max(advertised ?? fallback, fallback)
      + Math.floor(Math.random() * 5_000));
    await response.body?.cancel().catch(() => {});
    await new Promise(resolve => setTimeout(resolve, delay));
  }
}

function rpcFailureCode(error) {
  const detail = [error?.message, error?.cause?.message, error?.status, error?.cause?.status]
    .filter(value => value !== undefined && value !== null)
    .join(' ');
  if (/\b429\b|rate limit|too many requests/i.test(detail)) return 'devnet_rpc_rate_limited';
  if (/\b403\b|forbidden|blocked/i.test(detail)) return 'devnet_rpc_rejected';
  return 'devnet_rpc_unavailable';
}

const failRpc = error => fail(rpcFailureCode(error));
const u16 = value => { const out = Buffer.alloc(2); out.writeUInt16LE(value); return out; };
const u32 = value => { const out = Buffer.alloc(4); out.writeUInt32LE(value); return out; };
const anchorData = (name, ...parts) => Buffer.concat([
  createHash('sha256').update(`global:${name}`).digest().subarray(0, 8),
  ...parts,
]);

function workerAccount(worker) { return pda([Buffer.from('worker'), worker.toBuffer()]); }
function workerPayout(worker) {
  return pda([Buffer.from('worker_payout'), workerAccount(worker).toBuffer()]);
}
function fragmentAccount(job, index) {
  return pda([Buffer.from('fragment'), job.toBuffer(), u32(index)]);
}
function tokenAddress(owner, mint = MINT) {
  return PublicKey.findProgramAddressSync([
    owner.toBuffer(), TOKEN_PROGRAM.toBuffer(), mint.toBuffer(),
  ], ATA_PROGRAM)[0];
}
function fragmentResolution(fragment, round) {
  return pda([Buffer.from('fragment_resolution'), fragment.toBuffer(), u16(round)]);
}
function fragmentVote(fragment, verifier, round) {
  return pda([Buffer.from('fragment_vote'), fragment.toBuffer(), verifier.toBuffer(), u16(round)]);
}

async function loadWallet() {
  let secret;
  try { secret = JSON.parse(await readFile(WALLET_PATH, 'utf8')); } catch { fail('worker_wallet_unavailable'); }
  if (!Array.isArray(secret) || secret.length !== 64 || secret.some(value => !Number.isInteger(value) || value < 0 || value > 255)) {
    fail('worker_wallet_invalid');
  }
  try { return Keypair.fromSecretKey(Uint8Array.from(secret)); } catch { fail('worker_wallet_invalid'); }
}

function connection() {
  if (!RPC_URL.toLowerCase().includes('devnet')) fail('payments_require_devnet');
  return new Connection(RPC_URL, {
    commitment: 'confirmed',
    disableRetryOnRateLimit: true,
    fetch: rateLimitAwareFetch,
  });
}

function safeTransactionFailure(error) {
  let serialized = '';
  try { serialized = JSON.stringify(error); } catch {}
  const detail = [
    typeof error?.message === 'string' ? error.message : '',
    ...(Array.isArray(error?.logs) ? error.logs.filter(line => typeof line === 'string') : []),
    serialized,
  ].join('\n');
  const instruction = detail.match(/(?:Error processing Instruction\s+|InstructionError["']?\s*:\s*\[?)(\d+)/i)?.[1];
  const suffix = instruction === undefined ? '' : `_instruction_${instruction}`;
  const custom = detail.match(/custom program error:\s*(0x[0-9a-f]+)|["']?Custom["']?\s*:\s*(\d+)/i);
  if (custom) return `solana_program_error_${(custom[1] || custom[2]).toLowerCase()}${suffix}`;
  if (/insufficient funds for fee|insufficient lamports|attempt to debit an account/i.test(detail)) {
    return 'solana_fee_payer_insufficient_sol';
  }
  if (/blockhash not found|block height exceeded|blockhash expired/i.test(detail)) {
    return 'solana_blockhash_expired';
  }
  if (/accountnotinitialized|account is not initialized/i.test(detail)) return 'solana_account_not_initialized';
  if (/incorrectprogramid|incorrect program id/i.test(detail)) return 'solana_incorrect_program_id';
  if (/invalidaccountowner|invalid account owner/i.test(detail)) return 'solana_invalid_account_owner';
  if (/429|rate limit|too many requests/i.test(detail)) return 'solana_rpc_rate_limited';
  if (/failed to fetch|econnreset|econnrefused|etimedout|\b50[234]\b/i.test(detail)) return 'solana_rpc_unavailable';
  return 'solana_transaction_failed';
}

async function ensureFeeBalance(conn, wallet) {
  let balance;
  try { balance = await conn.getBalance(wallet.publicKey, 'confirmed'); } catch (error) { failRpc(error); }
  if (balance >= 1_000_000) return;
  try {
    const signature = await conn.requestAirdrop(wallet.publicKey, 5_000_000);
    await conn.confirmTransaction(signature, 'confirmed');
  } catch { fail('devnet_fee_funding_unavailable'); }
}

async function account(conn, address, owner = PROGRAM_ID) {
  let info;
  try { info = await conn.getAccountInfo(address, 'confirmed'); } catch (error) { failRpc(error); }
  if (!info || !info.owner.equals(owner)) fail('onchain_account_unavailable');
  return info.data;
}

async function readJob(conn, jobAddress, expected) {
  const job = new PublicKey(jobAddress);
  const initial = await account(conn, job);
  if (initial.length < 246) fail('onchain_job_invalid');
  const escrow = new PublicKey(initial.subarray(80, 112));
  let infos;
  try { infos = await conn.getMultipleAccountsInfo([job, escrow], 'confirmed'); } catch (error) { failRpc(error); }
  const jobInfo = infos[0];
  const escrowInfo = infos[1];
  if (!jobInfo?.owner.equals(PROGRAM_ID) || !escrowInfo?.owner.equals(TOKEN_PROGRAM)) fail('onchain_account_unavailable');
  const data = jobInfo.data;
  if (data.length < 246 || !data.subarray(0, 8).equals(createHash('sha256').update('account:Job').digest().subarray(0, 8))) {
    fail('onchain_job_invalid');
  }
  if (!data.subarray(48, 80).equals(MINT.toBuffer())) fail('onchain_mint_mismatch');
  const maxFragments = maxLeafFragments(expected);
  const currentFragments = data.readUInt32LE(112);
  const totalFragmentsCreated = data.readUInt32LE(206);
  const derivedInitialFragments = currentFragments * 2 - totalFragmentsCreated;
  if (derivedInitialFragments !== expected
    || data.readUInt32LE(202) !== MAX_FRAGMENT_NODES
    || currentFragments < expected || currentFragments > maxFragments
    || data[243] !== 0) fail('onchain_job_not_open');
  if (data.readBigUInt64LE(120) !== TOKEN_UNIT
    || data.readBigUInt64LE(128) !== TOKEN_UNIT
    || data.readBigUInt64LE(136) !== BigInt(maxFragments) * 2n * TOKEN_UNIT
    || data.readBigUInt64LE(144) !== BigInt(maxFragments) * 3n * TOKEN_UNIT
    || data.readUInt16LE(200) !== 2) fail('onchain_payment_schedule_invalid');
  if (BigInt(data.readBigInt64LE(184)) <= BigInt(Math.floor(Date.now() / 1000))) fail('onchain_job_expired');
  if (!data.subarray(80, 112).equals(escrow.toBuffer())) fail('onchain_escrow_invalid');
  const escrowData = escrowInfo.data;
  if (escrowData.length < 72 || !escrowData.subarray(0, 32).equals(MINT.toBuffer())) fail('onchain_escrow_invalid');
  const deposited = BigInt(data.readBigUInt64LE(144));
  const paid = BigInt(data.readBigUInt64LE(152));
  if (BigInt(escrowData.readBigUInt64LE(64)) !== deposited - paid) fail('onchain_escrow_balance_mismatch');
  return { job, data, escrow, maxFragments, maxNodes: MAX_FRAGMENT_NODES };
}

async function readPayout(conn, wallet) {
  const worker = wallet.publicKey;
  const address = workerPayout(worker);
  const data = await account(conn, address);
  if (data.length < 73 || !data.subarray(8, 40).equals(worker.toBuffer())) fail('worker_not_linked_to_account');
  const payoutWallet = new PublicKey(data.subarray(40, 72));
  const workerToken = tokenAddress(worker);
  const payoutToken = tokenAddress(payoutWallet);
  const missing = [];
  for (const [ata, owner] of [[workerToken, worker], [payoutToken, payoutWallet]]) {
    let info;
    try { info = await conn.getAccountInfo(ata, 'confirmed'); } catch (error) { failRpc(error); }
    if (!info) missing.push(createAssociatedTokenAccountIdempotentInstruction(
      worker,
      ata,
      owner,
      MINT,
      TOKEN_PROGRAM,
    ));
  }
  if (missing.length) await send(conn, wallet, missing);
  const workerTokenInfo = await account(conn, workerToken, TOKEN_PROGRAM);
  const payoutTokenInfo = await account(conn, payoutToken, TOKEN_PROGRAM);
  if (!workerTokenInfo.subarray(0, 32).equals(MINT.toBuffer()) || !payoutTokenInfo.subarray(0, 32).equals(MINT.toBuffer())) {
    fail('worker_sil_accounts_invalid');
  }
  if (!workerTokenInfo.subarray(32, 64).equals(worker.toBuffer())
    || !payoutTokenInfo.subarray(32, 64).equals(payoutWallet.toBuffer())) fail('worker_sil_accounts_invalid');
  return { address, payoutWallet, payoutToken };
}

async function send(conn, wallet, instructions) {
  await ensureFeeBalance(conn, wallet);
  let latest;
  try { latest = await conn.getLatestBlockhash('confirmed'); } catch (error) { failRpc(error); }
  const tx = new Transaction({ feePayer: wallet.publicKey, recentBlockhash: latest.blockhash });
  tx.add(...instructions);
  tx.sign(wallet);
  try {
    const signature = await conn.sendRawTransaction(tx.serialize(), { maxRetries: 3, preflightCommitment: 'confirmed' });
    const confirmation = await conn.confirmTransaction({ signature, ...latest }, 'confirmed');
    if (confirmation.value.err) fail(safeTransactionFailure(confirmation.value.err));
    return signature;
  } catch (error) {
    if (error instanceof SettlementError) throw error;
    fail(safeTransactionFailure(error));
  }
}

function claimFragmentInstruction(worker, workerToken, job, fragment, index) {
  return new TransactionInstruction({
    programId: PROGRAM_ID,
    keys: [
      { pubkey: worker, isSigner: true, isWritable: true },
      { pubkey: workerAccount(worker), isSigner: false, isWritable: true },
      { pubkey: job, isSigner: false, isWritable: false },
      { pubkey: fragment, isSigner: false, isWritable: true },
      { pubkey: workerToken, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data: anchorData('claim_fragment', u32(index)),
  });
}

function submitResultInstruction(worker, workerToken, job, fragment, index, hash) {
  return new TransactionInstruction({
    programId: PROGRAM_ID,
    keys: [
      { pubkey: worker, isSigner: true, isWritable: true },
      { pubkey: workerAccount(worker), isSigner: false, isWritable: true },
      { pubkey: job, isSigner: false, isWritable: false },
      { pubkey: fragment, isSigner: false, isWritable: true },
      { pubkey: workerToken, isSigner: false, isWritable: false },
    ],
    data: anchorData('submit_fragment_result', u32(index), hash, hash),
  });
}

async function submit(conn, wallet, jobInfo, index, resultHash) {
  const job = jobInfo.job;
  const fragment = fragmentAccount(job, index);
  const hash = Buffer.from(resultHash, 'hex');
  if (hash.length !== 32) fail('result_hash_invalid');
  const workerToken = tokenAddress(wallet.publicKey);
  let prior;
  try { prior = await conn.getAccountInfo(fragment, 'confirmed'); } catch (error) { failRpc(error); }
  let priorStatus = 0;
  if (prior) {
    if (!prior.owner.equals(PROGRAM_ID) || prior.data.length < 205) fail('onchain_fragment_invalid');
    const status = prior.data[204];
    priorStatus = status;
    if (status === 7) return 'split_parent';
    const worker = new PublicKey(prior.data.subarray(76, 108));
    if ((status === 2 || status === 3) && worker.equals(wallet.publicKey) && prior.data.subarray(140, 172).equals(hash)) {
      return 'already_submitted';
    }
    if (status !== 0 && !(status === 1 && new PublicKey(prior.data.subarray(44, 76)).equals(wallet.publicKey))) {
      fail('onchain_fragment_unavailable');
    }
  }
  const instructions = [];
  if (!prior || priorStatus === 0) instructions.push(claimFragmentInstruction(wallet.publicKey, workerToken, job, fragment, index));
  instructions.push(submitResultInstruction(wallet.publicKey, workerToken, job, fragment, index, hash));
  const signature = await send(conn, wallet, instructions);
  return signature;
}

function rootForFragment(initialFragments, maxFragments, fragmentIndex) {
  const remaining = maxFragments - initialFragments;
  if (initialFragments < 1 || remaining < initialFragments) fail('split_index_capacity_exhausted');
  const perRoot = Math.floor(remaining / initialFragments);
  if (fragmentIndex < initialFragments) return { root: fragmentIndex, local: 0, perRoot };
  const offset = fragmentIndex - initialFragments;
  const root = Math.floor(offset / perRoot);
  if (root >= initialFragments) fail('split_fragment_index_invalid');
  return { root, local: (offset % perRoot) + 1, perRoot };
}

function expectedChildIndexes(initialFragments, maxFragments, parentIndex) {
  const { root, local, perRoot } = rootForFragment(initialFragments, maxFragments, parentIndex);
  const firstLocal = local * 2 + 1;
  const secondLocal = firstLocal + 1;
  if (secondLocal > perRoot) fail('split_index_capacity_exhausted');
  return [
    initialFragments + root * perRoot + firstLocal - 1,
    initialFragments + root * perRoot + secondLocal - 1,
  ];
}

function proposeSplitInstruction(wallet, job, parent, proposal, escrow, manifestHash) {
  return new TransactionInstruction({
    programId: PROGRAM_ID,
    keys: [
      { pubkey: wallet.publicKey, isSigner: true, isWritable: true },
      { pubkey: workerAccount(wallet.publicKey), isSigner: false, isWritable: true },
      { pubkey: job, isSigner: false, isWritable: true },
      { pubkey: parent, isSigner: false, isWritable: true },
      { pubkey: proposal, isSigner: false, isWritable: true },
      { pubkey: escrow, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data: anchorData('propose_fragment_split', manifestHash, u16(2)),
  });
}

function createSubFragmentInstruction(wallet, job, parent, proposal, index, inputHash) {
  const hash = Buffer.from(inputHash, 'hex');
  if (hash.length !== 32 || hash.equals(Buffer.alloc(32))) fail('split_input_hash_invalid');
  return new TransactionInstruction({
    programId: PROGRAM_ID,
    keys: [
      { pubkey: wallet.publicKey, isSigner: true, isWritable: true },
      { pubkey: job, isSigner: false, isWritable: false },
      { pubkey: parent, isSigner: false, isWritable: true },
      { pubkey: proposal, isSigner: false, isWritable: true },
      { pubkey: fragmentAccount(job, index), isSigner: false, isWritable: true },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data: anchorData('create_sub_fragment', u32(index), Buffer.alloc(8), Buffer.alloc(8), u32(1_000), hash),
  });
}

async function claim(conn, wallet, jobInfo, index) {
  if (!Number.isInteger(index) || index < 0 || index >= jobInfo.data.readUInt32LE(202)) fail('fragment_index_invalid');
  const fragment = fragmentAccount(jobInfo.job, index);
  const prior = await conn.getAccountInfo(fragment, 'confirmed');
  if (prior?.owner.equals(PROGRAM_ID) && prior.data.length >= 205) {
    const status = prior.data[204];
    if (status === 1 && new PublicKey(prior.data.subarray(44, 76)).equals(wallet.publicKey)) return;
    if (status !== 0) fail('onchain_fragment_unavailable');
  } else if (prior) {
    fail('onchain_fragment_invalid');
  }
  await send(conn, wallet, [claimFragmentInstruction(
    wallet.publicKey,
    tokenAddress(wallet.publicKey),
    jobInfo.job,
    fragment,
    index,
  )]);
}

async function split(conn, wallet, jobInfo, parentIndex, manifestHashText, children) {
  if (!/^[0-9a-f]{64}$/i.test(manifestHashText || '') || children.length !== 2) fail('split_manifest_invalid');
  const maxFragments = jobInfo.maxNodes;
  const initialFragments = jobInfo.data.readUInt32LE(112) * 2 - jobInfo.data.readUInt32LE(206);
  const parent = fragmentAccount(jobInfo.job, parentIndex);
  const parentInfo = await conn.getAccountInfo(parent, 'confirmed');
  if (parentInfo && (!parentInfo.owner.equals(PROGRAM_ID) || parentInfo.data.length < 229)) fail('onchain_fragment_unavailable');
  const manifestHash = Buffer.from(manifestHashText, 'hex');
  const childIndexes = expectedChildIndexes(initialFragments, maxFragments, parentIndex);
  if (parentInfo?.data[204] === 7) {
    if (!parentInfo.data.subarray(266, 298).equals(manifestHash)) fail('split_manifest_conflict');
    for (const childIndex of childIndexes) {
      const childInfo = await conn.getAccountInfo(fragmentAccount(jobInfo.job, childIndex), 'confirmed');
      if (!childInfo?.owner.equals(PROGRAM_ID)) fail('onchain_fragment_unavailable');
    }
    return;
  }
  if (parentInfo && ![0, 1, 2].includes(parentInfo.data[204])) fail('split_parent_state_invalid');
  if (parentInfo && parentInfo.data[204] !== 0
    && !new PublicKey(parentInfo.data.subarray(44, 76)).equals(wallet.publicKey)) {
    fail('split_requires_claimed_parent');
  }
  const childrenByIndex = [...children].sort((a, b) => a.index - b.index);
  if (childrenByIndex.some((child, index) => child.index !== childIndexes[index])) fail('split_child_index_invalid');
  const round = parentInfo ? parentInfo.data.readUInt16LE(227) : 0;
  const proposal = pda([Buffer.from('split_proposal'), parent.toBuffer(), u16(round)]);
  const instructions = [];
  if (!parentInfo || parentInfo.data[204] === 0) {
    instructions.push(claimFragmentInstruction(
      wallet.publicKey,
      tokenAddress(wallet.publicKey),
      jobInfo.job,
      parent,
      parentIndex,
    ));
  }
  instructions.push(proposeSplitInstruction(
    wallet,
    jobInfo.job,
    parent,
    proposal,
    jobInfo.escrow,
    manifestHash,
  ));
  for (const child of childrenByIndex) {
    instructions.push(createSubFragmentInstruction(
      wallet,
      jobInfo.job,
      parent,
      proposal,
      child.index,
      child.inputHash,
    ));
  }
  await send(conn, wallet, instructions);
}

function voteInstruction(accounts, approved) {
  return new TransactionInstruction({
    programId: PROGRAM_ID,
    keys: [
      { pubkey: accounts.verifier, isSigner: true, isWritable: true },
      { pubkey: accounts.job, isSigner: false, isWritable: true },
      { pubkey: accounts.fragment, isSigner: false, isWritable: true },
      { pubkey: accounts.verifierWorker, isSigner: false, isWritable: true },
      { pubkey: accounts.computeWorker, isSigner: false, isWritable: true },
      { pubkey: accounts.vote, isSigner: false, isWritable: true },
      { pubkey: accounts.resolution, isSigner: false, isWritable: true },
      { pubkey: accounts.escrowAuth, isSigner: false, isWritable: false },
      { pubkey: accounts.escrow, isSigner: false, isWritable: true },
      { pubkey: accounts.workerToken, isSigner: false, isWritable: true },
      { pubkey: accounts.computePayout, isSigner: false, isWritable: false },
      { pubkey: accounts.computePayoutToken, isSigner: false, isWritable: true },
      { pubkey: TOKEN_PROGRAM, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data: anchorData('vote_fragment', Buffer.from([approved ? 1 : 0])),
  });
}

function claimVerifierRewardInstruction(accounts) {
  return new TransactionInstruction({
    programId: PROGRAM_ID,
    keys: [
      { pubkey: accounts.verifier, isSigner: true, isWritable: true },
      { pubkey: accounts.job, isSigner: false, isWritable: true },
      { pubkey: accounts.fragment, isSigner: false, isWritable: true },
      { pubkey: accounts.resolution, isSigner: false, isWritable: true },
      { pubkey: accounts.vote, isSigner: false, isWritable: true },
      { pubkey: accounts.verifierWorker, isSigner: false, isWritable: true },
      { pubkey: accounts.escrowAuth, isSigner: false, isWritable: false },
      { pubkey: accounts.escrow, isSigner: false, isWritable: true },
      { pubkey: accounts.verifierToken, isSigner: false, isWritable: true },
      { pubkey: accounts.verifierPayout, isSigner: false, isWritable: false },
      { pubkey: accounts.verifierPayoutToken, isSigner: false, isWritable: true },
      { pubkey: TOKEN_PROGRAM, isSigner: false, isWritable: false },
    ],
    data: anchorData('claim_verifier_reward'),
  });
}

async function vote(conn, wallet, jobInfo, index, approved) {
  const job = jobInfo.job;
  const fragment = fragmentAccount(job, index);
  const fragmentData = await account(conn, fragment);
  if (fragmentData.length >= 205 && fragmentData[204] === 7) return;
  if (fragmentData.length < 229 || fragmentData[204] !== 2) fail('onchain_fragment_not_submitted');
  const computeWorker = new PublicKey(fragmentData.subarray(76, 108));
  if (computeWorker.equals(wallet.publicKey) || new PublicKey(jobInfo.data.subarray(16, 48)).equals(wallet.publicKey)) {
    fail('worker_cannot_verify_own_job');
  }
  const round = fragmentData.readUInt16LE(227);
  const accounts = {
    verifier: wallet.publicKey,
    job,
    fragment,
    verifierWorker: workerAccount(wallet.publicKey),
    computeWorker: workerAccount(computeWorker),
    vote: fragmentVote(fragment, wallet.publicKey, round),
    resolution: fragmentResolution(fragment, round),
    escrowAuth: pda([Buffer.from('escrow_auth'), job.toBuffer()]),
    escrow: jobInfo.escrow,
    workerToken: new PublicKey(fragmentData.subarray(108, 140)),
    computePayout: workerPayout(computeWorker),
    computePayoutToken: null,
    verifierToken: tokenAddress(wallet.publicKey),
    verifierPayout: workerPayout(wallet.publicKey),
    verifierPayoutToken: null,
  };
  const [computePayoutData, verifierPayoutData] = await Promise.all([
    account(conn, accounts.computePayout),
    account(conn, accounts.verifierPayout),
  ]);
  if (computePayoutData.length < 73 || verifierPayoutData.length < 73) fail('worker_payout_account_invalid');
  if (!computePayoutData.subarray(8, 40).equals(computeWorker.toBuffer())
    || !verifierPayoutData.subarray(8, 40).equals(wallet.publicKey.toBuffer())) fail('worker_not_linked_to_account');
  const computePayoutWallet = new PublicKey(computePayoutData.subarray(40, 72));
  const verifierPayoutWallet = new PublicKey(verifierPayoutData.subarray(40, 72));
  accounts.computePayoutToken = tokenAddress(computePayoutWallet);
  accounts.verifierPayoutToken = tokenAddress(verifierPayoutWallet);

  let existingVote;
  try { existingVote = await conn.getAccountInfo(accounts.vote, 'confirmed'); } catch (error) { failRpc(error); }
  if (existingVote) {
    if (!existingVote.owner.equals(PROGRAM_ID) || existingVote.data.length < 78
      || !existingVote.data.subarray(40, 72).equals(wallet.publicKey.toBuffer())
      || Boolean(existingVote.data[72]) !== approved) fail('onchain_vote_conflict');
  } else {
    const instructions = [];
    let computePayoutTokenInfo;
    try { computePayoutTokenInfo = await conn.getAccountInfo(accounts.computePayoutToken, 'confirmed'); } catch (error) { failRpc(error); }
    if (!computePayoutTokenInfo) {
      instructions.push(createAssociatedTokenAccountIdempotentInstruction(
        wallet.publicKey,
        accounts.computePayoutToken,
        computePayoutWallet,
        MINT,
        TOKEN_PROGRAM,
      ));
    } else if (!computePayoutTokenInfo.owner.equals(TOKEN_PROGRAM)
      || computePayoutTokenInfo.data.length < 72
      || !computePayoutTokenInfo.data.subarray(0, 32).equals(MINT.toBuffer())
      || !computePayoutTokenInfo.data.subarray(32, 64).equals(computePayoutWallet.toBuffer())) {
      fail('worker_sil_accounts_invalid');
    }
    instructions.push(voteInstruction(accounts, approved));
    await send(conn, wallet, instructions);
  }

  // A verifier that votes first waits for the other accepted verifier. The
  // successful quorum's approving votes claim one SIL each; rejected rounds
  // remain unpaid and preserve escrow for a retry.
  const deadline = Date.now() + 120_000;
  let pollDelayMs = 1_000;
  while (Date.now() < deadline) {
    let resolutionInfo;
    let voteInfo;
    try {
      [resolutionInfo, voteInfo] = await conn.getMultipleAccountsInfo(
        [accounts.resolution, accounts.vote],
        'confirmed',
      );
    } catch (error) {
      failRpc(error);
    }
    if (resolutionInfo?.owner.equals(PROGRAM_ID) && resolutionInfo.data.length >= 49 && resolutionInfo.data[42] === 1) {
      const winning = resolutionInfo.data[43] === 1;
      if (winning && approved) {
        if (voteInfo?.data[76] !== 1) await send(conn, wallet, [claimVerifierRewardInstruction(accounts)]);
      }
      return;
    }
    const jitterMs = Math.floor(Math.random() * Math.min(3_000, pollDelayMs));
    await new Promise(resolve => setTimeout(resolve, pollDelayMs + jitterMs));
    pollDelayMs = Math.min(pollDelayMs * 2, 30_000);
  }
  fail('verification_quorum_not_reached');
}

async function main() {
  const [command, jobAddress, expectedText, indexText, value, ...extra] = process.argv.slice(2);
  const expected = Number(expectedText);
  const index = Number(indexText);
  if (!['ready', 'claim', 'split', 'submit', 'vote'].includes(command) || !jobAddress || !Number.isInteger(expected) || expected < 1 || expected > 256) {
    fail('worker_settlement_usage');
  }
  const conn = connection();
  const wallet = await loadWallet();
  const jobInfo = await readJob(conn, jobAddress, expected);
  await readPayout(conn, wallet);
  if (command === 'ready') {
    return;
  }
  if (!Number.isInteger(index) || index < 0 || index >= jobInfo.maxNodes) fail('fragment_index_invalid');
  if (command === 'claim') {
    await claim(conn, wallet, jobInfo, index);
    return;
  }
  if (command === 'split') {
    if (extra.length !== 4) fail('worker_settlement_usage');
    await split(conn, wallet, jobInfo, index, value, [
      { index: Number(extra[0]), inputHash: extra[1] },
      { index: Number(extra[2]), inputHash: extra[3] },
    ]);
    return;
  }
  if (command === 'submit') {
    if (!/^[0-9a-f]{64}$/i.test(value || '')) fail('result_hash_invalid');
    await submit(conn, wallet, jobInfo, index, value.toLowerCase());
    return;
  }
  if (value !== 'true' && value !== 'false') fail('verification_choice_invalid');
  await vote(conn, wallet, jobInfo, index, value === 'true');
}

main().catch(error => {
  // Never echo RPC URLs, account JSON, or wallet material to container logs.
  const code = error instanceof SettlementError ? error.code : 'solana_transaction_failed';
  process.stderr.write(`worker_settlement_error:${code}\n`);
  process.exitCode = 1;
});
