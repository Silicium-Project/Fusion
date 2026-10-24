import {
  Connection,
  Keypair,
  PublicKey,
  SYSVAR_RENT_PUBKEY,
  SystemProgram,
  Transaction,
  TransactionInstruction,
} from '@solana/web3.js';
import { Buffer } from 'buffer';
import type { PhantomProvider } from '~/types/wallet';
import { MAX_SIL_FRAGMENT_NODES, maxSILFragments } from './solanaQuote';

export { MAX_SIL_FRAGMENTS, MAX_SIL_FRAGMENT_NODES, maxSILFragments } from './solanaQuote';

export const DEVNET_SIL_MINT = 'F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP';
export const SILICIUM_PROGRAM_ID = '64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG';
export const SIL_PER_FRAGMENT = 3;
const TOKEN_PROGRAM_ID = new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');
const ASSOCIATED_TOKEN_PROGRAM_ID = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');
const TOKEN_UNIT = 1_000_000n;

export interface CreatedSILEscrow { jobAddress: string; signature: string }

function programId(): PublicKey { return new PublicKey(SILICIUM_PROGRAM_ID); }
function mintId(value = DEVNET_SIL_MINT): PublicKey { return new PublicKey(value); }
function u16(value: number): Buffer { const data = Buffer.alloc(2); data.writeUInt16LE(value); return data; }
function u32(value: number): Buffer { const data = Buffer.alloc(4); data.writeUInt32LE(value); return data; }
function u64(value: bigint): Buffer { const data = Buffer.alloc(8); data.writeBigUInt64LE(value); return data; }
function i64(value: bigint): Buffer { const data = Buffer.alloc(8); data.writeBigInt64LE(value); return data; }

async function anchorDiscriminator(name: string): Promise<Buffer> {
  const input = new TextEncoder().encode(`global:${name}`);
  const digest = await crypto.subtle.digest('SHA-256', input);
  return Buffer.from(digest).subarray(0, 8);
}

function associatedTokenAddress(owner: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [owner.toBuffer(), TOKEN_PROGRAM_ID.toBuffer(), mint.toBuffer()],
    ASSOCIATED_TOKEN_PROGRAM_ID,
  )[0];
}

function createAssociatedTokenInstruction(payer: PublicKey, owner: PublicKey, mint: PublicKey): TransactionInstruction {
  return new TransactionInstruction({
    programId: ASSOCIATED_TOKEN_PROGRAM_ID,
    keys: [
      { pubkey: payer, isSigner: true, isWritable: true },
      { pubkey: associatedTokenAddress(owner, mint), isSigner: false, isWritable: true },
      { pubkey: owner, isSigner: false, isWritable: false },
      { pubkey: mint, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
    ],
    data: Buffer.from([1]),
  });
}

function requireDevnet(connection: Connection): void {
  if (!connection.rpcEndpoint.toLowerCase().includes('devnet')) throw new Error('SIL payments are restricted to Solana Devnet.');
}

function isRateLimitedRpcFailure(failure: unknown): boolean {
  const error = failure as { message?: unknown; code?: unknown; cause?: { message?: unknown; code?: unknown } };
  return /429|too many requests|rate limit/i.test([
    error?.message,
    error?.code,
    error?.cause?.message,
    error?.cause?.code,
  ].filter(value => value !== undefined && value !== null).join(' '));
}

async function getAccountInfoWithBackoff(connection: Connection, address: PublicKey) {
  return retryRateLimitedRpc(() => connection.getAccountInfo(address, 'confirmed'));
}

/** Retry only idempotent RPC reads; transaction submission must never be replayed blindly. */
async function retryRateLimitedRpc<T>(operation: () => Promise<T>): Promise<T> {
  const delays = [500, 1_000, 2_000, 4_000, 8_000];
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation();
    } catch (failure) {
      if (!isRateLimitedRpcFailure(failure)) throw failure;
      if (attempt >= delays.length) throw new Error('SOLANA_RPC_RATE_LIMITED');
      const delay = delays[attempt]! + Math.floor(Math.random() * 500);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

async function sendWithWallet(connection: Connection, provider: PhantomProvider, transaction: Transaction, signers: Keypair[] = []): Promise<string> {
  if (!provider.signTransaction) throw new Error('Phantom must support transaction signing.');
  // Some RPCs return a JSON-RPC 429 (HTTP 200), which web3.js's HTTP-level
  // retry does not catch. Fetching a blockhash is safe to retry before signing.
  const latest = await retryRateLimitedRpc(() => connection.getLatestBlockhash('confirmed'));
  transaction.feePayer = new PublicKey(provider.publicKey?.toString() || '11111111111111111111111111111111');
  transaction.recentBlockhash = latest.blockhash;
  if (signers.length) transaction.partialSign(...signers);
  const signed = await provider.signTransaction(transaction);
  const signature = await connection.sendRawTransaction(signed.serialize(), { maxRetries: 3, preflightCommitment: 'confirmed' });
  const confirmation = await connection.confirmTransaction({ signature, ...latest }, 'confirmed');
  if (confirmation.value.err) throw new Error('Solana rejected the transaction.');
  return signature;
}

export async function createSILEscrow(
  connection: Connection,
  provider: PhantomProvider,
  clientAddress: string,
  expectedFragments: number,
  deadlineUnix: number,
  mintAddress = DEVNET_SIL_MINT,
): Promise<CreatedSILEscrow> {
  requireDevnet(connection);
  if (!Number.isInteger(expectedFragments) || expectedFragments < 1 || expectedFragments > 256) throw new Error('Invalid SIL quote fragment count.');
  if (!Number.isSafeInteger(deadlineUnix) || deadlineUnix <= Math.floor(Date.now() / 1000) + 60) throw new Error('The SIL escrow deadline must be at least one minute in the future.');
  const client = new PublicKey(clientAddress);
  if (provider.publicKey?.toString() !== client.toBase58()) throw new Error('Connect the verified wallet of this account in Phantom.');
  const mint = mintId(mintAddress);
  const random = new Uint8Array(8);
  crypto.getRandomValues(random);
  const jobId = Buffer.from(random).readBigUInt64LE(0);
  const jobSeed = u64(jobId);
  const [job] = PublicKey.findProgramAddressSync([Buffer.from('job'), client.toBuffer(), jobSeed], programId());
  const [escrowAuth] = PublicKey.findProgramAddressSync([Buffer.from('escrow_auth'), job.toBuffer()], programId());
  const escrow = Keypair.generate();
  const clientToken = associatedTokenAddress(client, mint);
  const maxFragments = maxSILFragments(expectedFragments);
  const deposit = BigInt(maxFragments) * BigInt(SIL_PER_FRAGMENT) * TOKEN_UNIT;
  const data = Buffer.concat([
    await anchorDiscriminator('create_job'),
    jobSeed,
    u32(expectedFragments),
    u64(TOKEN_UNIT),
    u64(TOKEN_UNIT),
    u64(BigInt(maxFragments) * 2n * TOKEN_UNIT),
    i64(BigInt(deadlineUnix)),
    u16(2),
  ]);
  const createJobInstruction = new TransactionInstruction({
    programId: programId(),
    keys: [
      { pubkey: client, isSigner: true, isWritable: true },
      { pubkey: mint, isSigner: false, isWritable: false },
      { pubkey: job, isSigner: false, isWritable: true },
      { pubkey: escrowAuth, isSigner: false, isWritable: false },
      { pubkey: escrow.publicKey, isSigner: true, isWritable: true },
      { pubkey: clientToken, isSigner: false, isWritable: true },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
      { pubkey: SYSVAR_RENT_PUBKEY, isSigner: false, isWritable: false },
    ],
    data,
  });
  const transaction = new Transaction().add(
    createAssociatedTokenInstruction(client, client, mint),
    createJobInstruction,
  );
  const signature = await sendWithWallet(connection, provider, transaction, [escrow]);
  return { jobAddress: job.toBase58(), signature };
}

function readOpenJob(data: Buffer, jobAddress: PublicKey, client: PublicKey, expectedFragments: number): { mint: PublicKey; escrow: PublicKey; currentFragments: number } {
  if (data.length < 246 || !data.subarray(0, 8).equals(Buffer.from('4b7c50cba1b4ca50', 'hex')) || data[243] !== 0) throw new Error('The Devnet job escrow is not open.');
  if (!new PublicKey(data.subarray(16, 48)).equals(client)) throw new Error('This escrow belongs to another wallet.');
  const maxFragments = maxSILFragments(expectedFragments);
  const maxFragmentNodes = MAX_SIL_FRAGMENT_NODES;
  const currentFragments = data.readUInt32LE(112);
  const totalFragmentsCreated = data.readUInt32LE(206);
  const initialFragments = currentFragments * 2 - totalFragmentsCreated;
  if (initialFragments !== expectedFragments || currentFragments < expectedFragments
    || currentFragments > maxFragments || data.readUInt32LE(202) !== maxFragmentNodes
    || data.readUInt16LE(200) !== 2
    || data.readBigUInt64LE(120) !== TOKEN_UNIT || data.readBigUInt64LE(128) !== TOKEN_UNIT
    || data.readBigUInt64LE(136) !== BigInt(maxFragments) * 2n * TOKEN_UNIT
    || data.readBigUInt64LE(144) !== BigInt(maxFragments) * BigInt(SIL_PER_FRAGMENT) * TOKEN_UNIT) {
    throw new Error('The Devnet escrow does not match the 3 SIL per fragment quote.');
  }
  return {
    mint: new PublicKey(data.subarray(48, 80)),
    escrow: new PublicKey(data.subarray(80, 112)),
    currentFragments,
  };
}

export async function cancelSILEscrow(
  connection: Connection,
  provider: PhantomProvider,
  clientAddress: string,
  jobAddress: string,
  expectedFragments: number,
): Promise<string | null> {
  requireDevnet(connection);
  const client = new PublicKey(clientAddress);
  if (provider.publicKey?.toString() !== client.toBase58()) throw new Error('Connect the verified wallet of this account in Phantom.');
  const job = new PublicKey(jobAddress);
  const info = await getAccountInfoWithBackoff(connection, job);
  if (!info || !info.owner.equals(programId())) throw new Error('The Devnet job escrow was not found.');
  if (info.data[243] === 2) return null;
  if (info.data[243] !== 0) throw new Error('This Devnet job has already been finalized.');
  const { mint, escrow } = readOpenJob(info.data, job, client, expectedFragments);
  const claimable = info.data.readBigUInt64LE(160);
  const claimed = info.data.readBigUInt64LE(168);
  if (claimed !== claimable) throw new Error('Waiting for the accepted verifier rewards to be claimed before refunding the remainder.');
  const [escrowAuth] = PublicKey.findProgramAddressSync([Buffer.from('escrow_auth'), job.toBuffer()], programId());
  const instruction = new TransactionInstruction({
    programId: programId(),
    keys: [
      { pubkey: client, isSigner: true, isWritable: true },
      { pubkey: job, isSigner: false, isWritable: true },
      { pubkey: escrowAuth, isSigner: false, isWritable: false },
      { pubkey: escrow, isSigner: false, isWritable: true },
      { pubkey: associatedTokenAddress(client, mint), isSigner: false, isWritable: true },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
    ],
    data: await anchorDiscriminator('cancel_job'),
  });
  return sendWithWallet(connection, provider, new Transaction().add(instruction));
}

export async function finalizeSILEscrow(
  connection: Connection,
  provider: PhantomProvider,
  clientAddress: string,
  jobAddress: string,
  expectedFragments: number,
  resultHash: string,
): Promise<string | null> {
  requireDevnet(connection);
  const client = new PublicKey(clientAddress);
  if (provider.publicKey?.toString() !== client.toBase58()) throw new Error('Connect the verified wallet of this account in Phantom.');
  if (!/^[0-9a-f]{64}$/i.test(resultHash)) throw new Error('A final SHA-256 result is required to close this escrow.');
  const job = new PublicKey(jobAddress);
  const info = await getAccountInfoWithBackoff(connection, job);
  if (!info || !info.owner.equals(programId())) throw new Error('The Devnet job escrow was not found.');
  if (info.data[243] === 1) return null;
  if (info.data[243] !== 0) throw new Error('This Devnet job has already been cancelled.');
  const { mint, escrow, currentFragments } = readOpenJob(info.data, job, client, expectedFragments);
  if (info.data.readUInt32LE(116) !== currentFragments) throw new Error('The on-chain job has not verified all fragments yet.');
  if (info.data.readBigUInt64LE(160) !== info.data.readBigUInt64LE(168)) throw new Error('Waiting for the accepted verifier rewards to be claimed before finalizing.');
  const [escrowAuth] = PublicKey.findProgramAddressSync([Buffer.from('escrow_auth'), job.toBuffer()], programId());
  const [result] = PublicKey.findProgramAddressSync([Buffer.from('result'), job.toBuffer()], programId());
  const instruction = new TransactionInstruction({
    programId: programId(),
    keys: [
      { pubkey: client, isSigner: true, isWritable: true },
      { pubkey: job, isSigner: false, isWritable: true },
      { pubkey: result, isSigner: false, isWritable: true },
      { pubkey: escrowAuth, isSigner: false, isWritable: false },
      { pubkey: escrow, isSigner: false, isWritable: true },
      { pubkey: associatedTokenAddress(client, mint), isSigner: false, isWritable: true },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data: Buffer.concat([
      await anchorDiscriminator('finalize_job'),
      Buffer.from(resultHash, 'hex'),
      u32(0),
    ]),
  });
  return sendWithWallet(connection, provider, new Transaction().add(instruction));
}
