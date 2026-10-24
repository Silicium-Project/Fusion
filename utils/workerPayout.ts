import {
  Connection,
  Ed25519Program,
  PublicKey,
  SystemProgram,
  Transaction,
  TransactionInstruction,
} from '@solana/web3.js';
import { Buffer } from 'buffer';
import type { PhantomProvider } from '~/types/wallet';

export interface WorkerPayoutDevice {
  nodeId: string;
  peerId: string;
  solanaWallet?: string;
  payoutWallet?: string;
  workerPayoutProof?: { message: string; signature: string };
}

export interface SignedPayoutTransaction {
  transaction: Transaction;
  blockhash: string;
  lastValidBlockHeight: number;
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

async function retryRateLimitedRpc<T>(operation: () => Promise<T>): Promise<T> {
  const delays = [500, 1_000, 2_000, 4_000];
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await operation();
    } catch (failure) {
      if (!isRateLimitedRpcFailure(failure)) throw failure;
      if (attempt >= delays.length) throw new Error('SOLANA_RPC_RATE_LIMITED');
      await new Promise(resolve => setTimeout(resolve, delays[attempt]! + Math.floor(Math.random() * 500)));
    }
  }
}

function isBlockhashFailure(failure: unknown): boolean {
  const error = failure as { message?: unknown; logs?: unknown; cause?: { message?: unknown } };
  const logs = Array.isArray(error?.logs) ? error.logs.filter(line => typeof line === 'string') : [];
  return /blockhash not found|block height exceeded|blockhash expired/i.test([
    error?.message,
    error?.cause?.message,
    ...logs,
  ].filter(value => value !== undefined && value !== null).join('\n'));
}

/** Send the signed registration batch, refreshing expired blockhashes safely. */
export async function sendWorkerPayoutBatch(
  connection: Connection,
  provider: PhantomProvider,
  transactions: SignedPayoutTransaction[],
): Promise<string[]> {
  if (!provider.signAllTransactions) throw new Error('Phantom must support signing worker-link transactions as a group.');
  let signed = await provider.signAllTransactions(transactions.map(item => item.transaction));
  if (signed.length !== transactions.length) throw new Error('Phantom returned an incomplete transaction batch.');

  const signatures: string[] = [];
  let index = 0;
  let blockhashRefreshes = 0;
  while (index < transactions.length) {
    try {
      const signature = await connection.sendRawTransaction(signed[index]!.serialize(), {
        maxRetries: 3,
        preflightCommitment: 'confirmed',
      });
      signatures.push(signature);
      index += 1;
      blockhashRefreshes = 0;
    } catch (failure) {
      if (!isBlockhashFailure(failure) || blockhashRefreshes >= 2) throw failure;
      blockhashRefreshes += 1;
      const latest = await retryRateLimitedRpc(() => connection.getLatestBlockhash('confirmed'));
      const refreshed = transactions.slice(index).map(({ transaction }) => (
        new Transaction({ feePayer: transaction.feePayer, recentBlockhash: latest.blockhash })
          .add(...transaction.instructions)
      ));
      const resigned = await provider.signAllTransactions(refreshed);
      if (resigned.length !== refreshed.length) throw new Error('Phantom returned an incomplete refreshed transaction batch.');
      signed = [...signed.slice(0, index), ...resigned];
    }
  }
  return signatures;
}

export async function inspectWorkerPayouts(
  connection: Connection,
  payoutWalletAddress: string,
  mintAddress: string,
  devices: WorkerPayoutDevice[],
): Promise<string[]> {
  const payoutWallet = new PublicKey(payoutWalletAddress);
  const mint = new PublicKey(mintAddress);
  const candidates = devices.filter(device => device.solanaWallet && device.payoutWallet === payoutWalletAddress);
  if (!candidates.length) return [];
  const accountRows = candidates.map(device => {
    const worker = new PublicKey(device.solanaWallet!);
    return {
      device,
      worker,
      workerAccount: workerAccountForPayout(worker),
      payout: PublicKey.findProgramAddressSync(
        [new TextEncoder().encode('worker_payout'), workerAccountForPayout(worker).toBytes()],
        SILICIUM_PROGRAM_ID,
      )[0],
      workerToken: associatedTokenAddress(worker, mint),
      payoutToken: associatedTokenAddress(payoutWallet, mint),
    };
  });
  const infos = await retryRateLimitedRpc(() => connection.getMultipleAccountsInfo(
    accountRows.flatMap(row => [row.payout, row.workerAccount, row.workerToken, row.payoutToken]),
    'confirmed',
  ));
  const ready: string[] = [];
  accountRows.forEach((row, index) => {
    const payoutInfo = infos[index * 4];
    const workerInfo = infos[index * 4 + 1];
    const workerTokenInfo = infos[index * 4 + 2];
    const payoutTokenInfo = infos[index * 4 + 3];
    if (!payoutInfo?.owner.equals(SILICIUM_PROGRAM_ID) || payoutInfo.data.length < 73
      || !payoutInfo.data.subarray(8, 40).equals(row.worker.toBuffer())
      || !payoutInfo.data.subarray(40, 72).equals(payoutWallet.toBuffer())) return;
    if (!workerInfo?.owner.equals(SILICIUM_PROGRAM_ID) || workerInfo.data.length < 199
      || !workerInfo.data.subarray(8, 40).equals(row.worker.toBuffer())
      || workerInfo.data[198] !== 0 || (workerInfo.data[196]! & 3) !== 3) return;
    if (!workerTokenInfo?.owner.equals(TOKEN_PROGRAM_ID) || workerTokenInfo.data.length < 72
      || !workerTokenInfo.data.subarray(0, 32).equals(mint.toBuffer())) return;
    if (!payoutTokenInfo?.owner.equals(TOKEN_PROGRAM_ID) || payoutTokenInfo.data.length < 72
      || !payoutTokenInfo.data.subarray(0, 32).equals(mint.toBuffer())) return;
    ready.push(row.device.nodeId);
  });
  return ready;
}

const SILICIUM_PROGRAM_ID = new PublicKey('64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG');
const TOKEN_PROGRAM_ID = new PublicKey('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');
const ASSOCIATED_TOKEN_PROGRAM_ID = new PublicKey('ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL');
const INSTRUCTIONS_SYSVAR_ID = new PublicKey('Sysvar1nstructions1111111111111111111111111');
const REGISTER_WORKER_PAYOUT_DISCRIMINATOR = Uint8Array.from([0x29, 0x52, 0xa1, 0xb5, 0xd0, 0x41, 0xb0, 0x73]);

function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const length = parts.reduce((sum, part) => sum + part.length, 0);
  const result = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    result.set(part, offset);
    offset += part.length;
  }
  return result;
}

function anchorString(value: string): Uint8Array {
  const encoded = new TextEncoder().encode(value);
  const length = new Uint8Array(4);
  new DataView(length.buffer).setUint32(0, encoded.length, true);
  return concatBytes(length, encoded);
}

function decodeHex(value: string, expectedBytes: number): Uint8Array {
  if (!new RegExp(`^[0-9a-fA-F]{${expectedBytes * 2}}$`).test(value)) {
    throw new Error('The worker payout proof has an invalid signature.');
  }
  return Uint8Array.from(value.match(/.{2}/g)!.map(byte => Number.parseInt(byte, 16)));
}

function associatedTokenAddress(owner: PublicKey, mint: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [owner.toBytes(), TOKEN_PROGRAM_ID.toBytes(), mint.toBytes()],
    ASSOCIATED_TOKEN_PROGRAM_ID,
  )[0];
}

function createAssociatedTokenInstruction(payer: PublicKey, owner: PublicKey, mint: PublicKey, address: PublicKey): TransactionInstruction {
  return new TransactionInstruction({
    programId: ASSOCIATED_TOKEN_PROGRAM_ID,
    keys: [
      { pubkey: payer, isSigner: true, isWritable: true },
      { pubkey: address, isSigner: false, isWritable: true },
      { pubkey: owner, isSigner: false, isWritable: false },
      { pubkey: mint, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
      { pubkey: TOKEN_PROGRAM_ID, isSigner: false, isWritable: false },
    ],
    data: Buffer.from([1]), // CreateIdempotent
  });
}

function registerWorkerPayoutInstruction(
  payoutWallet: PublicKey,
  worker: PublicKey,
  pairingCode: string,
  nodeId: string,
  peerId: string,
): TransactionInstruction {
  const [workerPayout] = PublicKey.findProgramAddressSync(
    [new TextEncoder().encode('worker_payout'), workerAccountForPayout(worker).toBytes()],
    SILICIUM_PROGRAM_ID,
  );
  const data = Buffer.from(concatBytes(
    REGISTER_WORKER_PAYOUT_DISCRIMINATOR,
    anchorString(pairingCode),
    anchorString(nodeId),
    anchorString(peerId),
  ));
  return new TransactionInstruction({
    programId: SILICIUM_PROGRAM_ID,
    keys: [
      { pubkey: payoutWallet, isSigner: true, isWritable: true },
      { pubkey: worker, isSigner: false, isWritable: false },
      { pubkey: workerAccountForPayout(worker), isSigner: false, isWritable: true },
      { pubkey: workerPayout, isSigner: false, isWritable: true },
      { pubkey: worker, isSigner: false, isWritable: false }, // previous destination is the worker's default wallet
      { pubkey: INSTRUCTIONS_SYSVAR_ID, isSigner: false, isWritable: false },
      { pubkey: SystemProgram.programId, isSigner: false, isWritable: false },
    ],
    data,
  });
}

function workerAccountForPayout(worker: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [new TextEncoder().encode('worker'), worker.toBytes()],
    SILICIUM_PROGRAM_ID,
  )[0];
}

export async function buildWorkerPayoutTransactions(
  connection: Connection,
  payoutWalletAddress: string,
  mintAddress: string,
  devices: WorkerPayoutDevice[],
): Promise<{ transactions: SignedPayoutTransaction[]; registered: number; alreadyLinked: number }> {
  const payoutWallet = new PublicKey(payoutWalletAddress);
  const mint = new PublicKey(mintAddress);
  const tokenAddress = associatedTokenAddress(payoutWallet, mint);
  const accountRows = devices.map(device => {
    if (!device.solanaWallet || !device.payoutWallet || !device.workerPayoutProof) {
      throw new Error(`Missing signed payout proof for ${device.nodeId}.`);
    }
    if (device.payoutWallet !== payoutWalletAddress) {
      throw new Error(`The payout wallet for ${device.nodeId} differs from this account.`);
    }
    const worker = new PublicKey(device.solanaWallet);
    const messageLines = device.workerPayoutProof.message.split('\n');
    if (messageLines.length !== 6
      || messageLines[0] !== 'silicium-device-payout-v1'
      || messageLines[2] !== device.nodeId
      || messageLines[3] !== device.peerId
      || messageLines[4] !== worker.toBase58()
      || messageLines[5] !== payoutWalletAddress
      || !/^[0-9a-fA-F]{64}$/.test(messageLines[1] || '')) {
      throw new Error(`The signed payout proof for ${device.nodeId} does not match this device and account.`);
    }
    const workerAccount = workerAccountForPayout(worker);
    const [payout] = PublicKey.findProgramAddressSync(
      [new TextEncoder().encode('worker_payout'), workerAccount.toBytes()],
      SILICIUM_PROGRAM_ID,
    );
    return {
      device,
      worker,
      payout,
      workerAccount,
      workerTokenAddress: associatedTokenAddress(worker, mint),
    };
  });

  // One RPC request replaces 3 account lookups per worker. The 20-worker pool
  // uses 61 addresses, below Solana's 100-account getMultipleAccounts limit.
  const infos = await retryRateLimitedRpc(() => connection.getMultipleAccountsInfo([
    tokenAddress,
    ...accountRows.flatMap(row => [row.payout, row.workerAccount, row.workerTokenAddress]),
  ], 'confirmed'));
  const tokenAccountInfo = infos[0];
  const resolvedRows = accountRows.map((row, index) => {
    const info = infos[1 + index * 3];
    const workerInfo = infos[2 + index * 3];
    const workerTokenInfo = infos[3 + index * 3];
    let alreadyLinked = false;
    if (info) {
      if (!info.owner.equals(SILICIUM_PROGRAM_ID) || info.data.length < 73
        || !new PublicKey(info.data.subarray(8, 40)).equals(row.worker)) {
        throw new Error(`The on-chain payout record for ${row.device.nodeId} has an unexpected layout.`);
      }
      const currentPayoutWallet = new PublicKey(info.data.subarray(40, 72));
      if (currentPayoutWallet.equals(payoutWallet)) alreadyLinked = true;
      else if (!currentPayoutWallet.equals(row.worker)) {
        throw new Error(`The payout for ${row.device.nodeId} is already assigned to another wallet. Both wallet owners must authorize a change.`);
      }
    }
    return { ...row, info, workerInfo, workerTokenInfo, alreadyLinked };
  });

  // Older versions could store the payout PDA without creating the Worker
  // profile. Re-submit the proof-bound instruction in that case so the
  // contract can accept this device in compute and verification calls.
  const rows = resolvedRows.filter(row => !row.alreadyLinked || !row.workerInfo);
  const alreadyLinked = resolvedRows.filter(row => row.alreadyLinked).length;
  const tokenRows = resolvedRows.filter(row => !row.workerTokenInfo);
  const missingTokenAccount = tokenAccountInfo === null;
  if (!rows.length && !tokenRows.length && !missingTokenAccount) {
    return { transactions: [], registered: 0, alreadyLinked };
  }

  const pending: Array<{ transaction: Transaction; blockhash: string; lastValidBlockHeight: number }> = [];
  // All registrations can share one recent blockhash. Fetching a blockhash for
  // each of 20 workers needlessly multiplies public Devnet RPC traffic.
  const block = await retryRateLimitedRpc(() => connection.getLatestBlockhash('confirmed'));
  const registrationByWorker = new Map(rows.map(row => [row.worker.toBase58(), row]));
  const rowsByWorker = new Map(resolvedRows.map(row => [row.worker.toBase58(), row]));
  const transactionWorkers = new Set([...registrationByWorker.keys(), ...tokenRows.map(row => row.worker.toBase58())]);
  if (!transactionWorkers.size && missingTokenAccount) {
    const transaction = new Transaction({ feePayer: payoutWallet, recentBlockhash: block.blockhash });
    transaction.add(createAssociatedTokenInstruction(payoutWallet, payoutWallet, mint, tokenAddress));
    pending.push({ transaction, ...block });
  }

  let payoutAtaAdded = !missingTokenAccount;
  for (const workerAddress of transactionWorkers) {
    const row = rowsByWorker.get(workerAddress)!;
    const registration = registrationByWorker.get(workerAddress);
    const transaction = new Transaction({ feePayer: payoutWallet, recentBlockhash: block.blockhash });
    if (!payoutAtaAdded) {
      transaction.add(createAssociatedTokenInstruction(payoutWallet, payoutWallet, mint, tokenAddress));
      payoutAtaAdded = true;
    }
    if (tokenRows.some(tokenRow => tokenRow.worker.toBase58() === workerAddress)) {
      transaction.add(createAssociatedTokenInstruction(
        payoutWallet,
        row.worker,
        mint,
        row.workerTokenAddress,
      ));
    }
    if (registration) {
      const proof = row.device.workerPayoutProof!;
      const message = new TextEncoder().encode(proof.message);
      const signature = decodeHex(proof.signature, 64);
      const proofInstruction = Ed25519Program.createInstructionWithPublicKey({
        publicKey: Buffer.from(row.worker.toBytes()),
        message: Buffer.from(message),
        signature: Buffer.from(signature),
      });
      const anchorInstruction = registerWorkerPayoutInstruction(
        payoutWallet,
        row.worker,
        proof.message.split('\n')[1]!,
        row.device.nodeId,
        row.device.peerId,
      );
      transaction.add(proofInstruction, anchorInstruction);
    }
    pending.push({ transaction, ...block });
  }

  if (missingTokenAccount && !payoutAtaAdded) {
    const transaction = new Transaction({ feePayer: payoutWallet, recentBlockhash: block.blockhash });
    transaction.add(createAssociatedTokenInstruction(payoutWallet, payoutWallet, mint, tokenAddress));
    pending.push({ transaction, ...block });
  }

  return { transactions: pending, registered: rows.length, alreadyLinked };
}
