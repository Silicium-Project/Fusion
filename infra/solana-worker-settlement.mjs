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

const PROGRAM_ID = new PublicKey(process.env.SILICIUM_SOLANA_PROGRAM_ID || 'A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2');
const MINT = new PublicKey(process.env.SILICIUM_SOLANA_MINT || 'F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP');
const TOKEN_PROGRAM = new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');
const ATA_PROGRAM = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');
const RPC_URL = process.env.SILICIUM_SOLANA_RPC || 'https://api.devnet.solana.com';
const WALLET_PATH = process.env.SILICIUM_SOLANA_WALLET_PATH || '/data/solana-wallet.json';
const TOKEN_UNIT = 1_000_000n;

class SettlementError extends Error {
  constructor(code) { super(code); this.code = code; }
}

const fail = code => { throw new SettlementError(code); };
const pda = (seeds) => PublicKey.findProgramAddressSync(seeds, PROGRAM_ID)[0];
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
  return new Connection(RPC_URL, 'confirmed');
}

async function ensureFeeBalance(conn, wallet) {
  let balance;
  try { balance = await conn.getBalance(wallet.publicKey, 'confirmed'); } catch { fail('devnet_rpc_unavailable'); }
  if (balance >= 1_000_000) return;
  try {
    const signature = await conn.requestAirdrop(wallet.publicKey, 5_000_000);
    await conn.confirmTransaction(signature, 'confirmed');
  } catch { fail('devnet_fee_funding_unavailable'); }
}

async function account(conn, address, owner = PROGRAM_ID) {
  let info;
  try { info = await conn.getAccountInfo(address, 'confirmed'); } catch { fail('devnet_rpc_unavailable'); }
  if (!info || !info.owner.equals(owner)) fail('onchain_account_unavailable');
  return info.data;
}

async function readJob(conn, jobAddress, expected) {
  const job = new PublicKey(jobAddress);
  const initial = await account(conn, job);
  if (initial.length < 246) fail('onchain_job_invalid');
  const escrow = new PublicKey(initial.subarray(80, 112));
  let infos;
  try { infos = await conn.getMultipleAccountsInfo([job, escrow], 'confirmed'); } catch { fail('devnet_rpc_unavailable'); }
  const jobInfo = infos[0];
  const escrowInfo = infos[1];
  if (!jobInfo?.owner.equals(PROGRAM_ID) || !escrowInfo?.owner.equals(TOKEN_PROGRAM)) fail('onchain_account_unavailable');
  const data = jobInfo.data;
  if (data.length < 246 || !data.subarray(0, 8).equals(createHash('sha256').update('account:Job').digest().subarray(0, 8))) {
    fail('onchain_job_invalid');
  }
  if (!data.subarray(48, 80).equals(MINT.toBuffer())) fail('onchain_mint_mismatch');
  if (data.readUInt32LE(112) !== expected || data[243] !== 0) fail('onchain_job_not_open');
  if (data.readBigUInt64LE(120) !== TOKEN_UNIT
    || data.readBigUInt64LE(128) !== TOKEN_UNIT
    || data.readBigUInt64LE(136) !== BigInt(expected) * 2n * TOKEN_UNIT
    || data.readBigUInt64LE(144) !== BigInt(expected) * 3n * TOKEN_UNIT
    || data.readUInt16LE(200) !== 2) fail('onchain_payment_schedule_invalid');
  if (BigInt(data.readBigInt64LE(184)) <= BigInt(Math.floor(Date.now() / 1000))) fail('onchain_job_expired');
  if (!data.subarray(80, 112).equals(escrow.toBuffer())) fail('onchain_escrow_invalid');
  const escrowData = escrowInfo.data;
  if (escrowData.length < 72 || !escrowData.subarray(0, 32).equals(MINT.toBuffer())) fail('onchain_escrow_invalid');
  const remaining = BigInt(data.readBigUInt64LE(144)) - BigInt(data.readBigUInt64LE(152));
  if (BigInt(escrowData.readBigUInt64LE(64)) !== remaining) fail('onchain_escrow_balance_mismatch');
  return { job, data, escrow };
}

async function readPayout(conn, worker) {
  const address = workerPayout(worker);
  const data = await account(conn, address);
  if (data.length < 73 || !data.subarray(8, 40).equals(worker.toBuffer())) fail('worker_not_linked_to_account');
  const payoutWallet = new PublicKey(data.subarray(40, 72));
  const workerToken = tokenAddress(worker);
  const payoutToken = tokenAddress(payoutWallet);
  const workerTokenInfo = await account(conn, workerToken, TOKEN_PROGRAM);
  const payoutTokenInfo = await account(conn, payoutToken, TOKEN_PROGRAM);
  if (!workerTokenInfo.subarray(0, 32).equals(MINT.toBuffer()) || !payoutTokenInfo.subarray(0, 32).equals(MINT.toBuffer())) {
    fail('worker_sil_accounts_invalid');
  }
  return { address, payoutWallet, payoutToken };
}

async function send(conn, wallet, instructions) {
  await ensureFeeBalance(conn, wallet);
  const latest = await conn.getLatestBlockhash('confirmed');
  const tx = new Transaction({ feePayer: wallet.publicKey, recentBlockhash: latest.blockhash });
  tx.add(...instructions);
  tx.sign(wallet);
  try {
    const signature = await conn.sendRawTransaction(tx.serialize(), { maxRetries: 3, preflightCommitment: 'confirmed' });
    const confirmation = await conn.confirmTransaction({ signature, ...latest }, 'confirmed');
    if (confirmation.value.err) fail('solana_transaction_rejected');
    return signature;
  } catch (error) {
    if (error instanceof SettlementError) throw error;
    fail('solana_transaction_failed');
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
  try { prior = await conn.getAccountInfo(fragment, 'confirmed'); } catch { fail('devnet_rpc_unavailable'); }
  if (prior) {
    if (!prior.owner.equals(PROGRAM_ID) || prior.data.length < 205) fail('onchain_fragment_invalid');
    const status = prior.data[204];
    const worker = new PublicKey(prior.data.subarray(76, 108));
    if ((status === 2 || status === 3) && worker.equals(wallet.publicKey) && prior.data.subarray(140, 172).equals(hash)) {
      return 'already_submitted';
    }
    if (status !== 0) fail('onchain_fragment_unavailable');
  }
  const signature = await send(conn, wallet, [
    claimFragmentInstruction(wallet.publicKey, workerToken, job, fragment, index),
    submitResultInstruction(wallet.publicKey, workerToken, job, fragment, index, hash),
  ]);
  return signature;
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
  if (!computePayoutData.subarray(8, 40).equals(computeWorker.toBuffer())
    || !verifierPayoutData.subarray(8, 40).equals(wallet.publicKey.toBuffer())) fail('worker_not_linked_to_account');
  const computePayoutWallet = new PublicKey(computePayoutData.subarray(40, 72));
  const verifierPayoutWallet = new PublicKey(verifierPayoutData.subarray(40, 72));
  accounts.computePayoutToken = tokenAddress(computePayoutWallet);
  accounts.verifierPayoutToken = tokenAddress(verifierPayoutWallet);

  const existingVote = await conn.getAccountInfo(accounts.vote, 'confirmed');
  if (existingVote) {
    if (!existingVote.owner.equals(PROGRAM_ID) || existingVote.data.length < 78
      || !existingVote.data.subarray(40, 72).equals(wallet.publicKey.toBuffer())
      || Boolean(existingVote.data[72]) !== approved) fail('onchain_vote_conflict');
  } else {
    await send(conn, wallet, [voteInstruction(accounts, approved)]);
  }

  // A verifier that votes first waits for the other accepted verifier. Both
  // claim their own one-SIL reward as soon as the on-chain quorum resolves.
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const resolutionInfo = await conn.getAccountInfo(accounts.resolution, 'confirmed');
    if (resolutionInfo?.owner.equals(PROGRAM_ID) && resolutionInfo.data.length >= 49 && resolutionInfo.data[42] === 1) {
      const winning = resolutionInfo.data[43] === 1;
      if (!winning || approved) {
        const voteInfo = await conn.getAccountInfo(accounts.vote, 'confirmed');
        if (voteInfo?.data[76] !== 1) await send(conn, wallet, [claimVerifierRewardInstruction(accounts)]);
      }
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 2_000));
  }
  fail('verification_quorum_not_reached');
}

async function main() {
  const [command, jobAddress, expectedText, indexText, value] = process.argv.slice(2);
  const expected = Number(expectedText);
  const index = Number(indexText);
  if (!['ready', 'submit', 'vote'].includes(command) || !jobAddress || !Number.isInteger(expected) || expected < 1 || expected > 256) {
    fail('worker_settlement_usage');
  }
  const conn = connection();
  const wallet = await loadWallet();
  const jobInfo = await readJob(conn, jobAddress, expected);
  await readPayout(conn, wallet.publicKey);
  if (command === 'ready') {
    return;
  }
  if (!Number.isInteger(index) || index < 0 || index >= expected) fail('fragment_index_invalid');
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
