import { Buffer } from 'buffer';
import type {
  PublicKey as SolanaPublicKey,
  Transaction as SolanaTransaction,
  VersionedTransaction as SolanaVersionedTransaction,
} from '@solana/web3.js';
import { phantomProvider } from '~/utils/wallet';
import { resolveSolanaRpcEndpoint } from '~/utils/solanaRpc';

export type SILSwapDirection = 'buy' | 'sell';

export interface SILEconomyMarket {
  poolId: string;
  solReserve: number;
  silReserve: number;
  silPerSol: number;
  solPerSil: number;
  solUsd: number | null;
  silUsd: number | null;
  tradeFeeBps: number;
  slot: number;
  observedAt: number;
  pythPublishedAt: number | null;
  pythAgeSeconds: number | null;
  oracleAvailable: boolean;
}

export interface SILSwapQuote {
  input: number;
  output: number;
  minimumOutput: number;
  priceImpactPercent: number;
  direction: SILSwapDirection;
}

const DEVNET_CPMM_PROGRAM_ID = 'DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb';
const DEVNET_SIL_MINT_ID = 'F5zPejtGPm2eqG1hwFGof6uWVJ79LDKeKYDVifXqhPRP';
const WSOL_MINT_ID = 'So11111111111111111111111111111111111111112';
const SPL_TOKEN_PROGRAM_ID = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const ASSOCIATED_TOKEN_PROGRAM_ID = 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL';
const PYTH_RECEIVER_PROGRAM_ID = 'rec2HHDDnjLfj4kE7VyEtFA1HPGQLK33259532cRyHp';
const PYTH_SOL_USD_ACCOUNT_ID = '7AviUf9nL62mcxNbQGKm4nKDQnPjswo6c5MX4D57HmyE';
const PYTH_SOL_USD_FEED = Buffer.from('ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d', 'hex');
const FEE_DENOMINATOR = BigInt(1_000_000);
const ZERO = BigInt(0);
const BPS_DENOMINATOR = BigInt(10_000);
const SWAP_SLIPPAGE_BPS = 50;
const TOKEN_ACCOUNT_AMOUNT_OFFSET = 64;
const MAX_PYTH_AGE_SECONDS = 180;

function publicKeyAt(
  data: Buffer,
  offset: number,
  PublicKey: typeof import('@solana/web3.js').PublicKey,
): SolanaPublicKey {
  return new PublicKey(data.subarray(offset, offset + 32));
}

function tokenAmount(
  account: { owner: SolanaPublicKey; data: Buffer },
  mint: SolanaPublicKey,
  authority: SolanaPublicKey,
  tokenProgram: SolanaPublicKey,
  PublicKey: typeof import('@solana/web3.js').PublicKey,
): bigint {
  if (!account.owner.equals(tokenProgram) || account.data.length < 165
    || !publicKeyAt(account.data, 0, PublicKey).equals(mint)
    || !publicKeyAt(account.data, 32, PublicKey).equals(authority)) {
    throw new Error('The SIL/SOL pool vault does not match its on-chain mint or authority.');
  }
  return account.data.readBigUInt64LE(TOKEN_ACCOUNT_AMOUNT_OFFSET);
}

function parsePyth(
  account: { owner: SolanaPublicKey; data: Buffer } | null,
  pythProgram: SolanaPublicKey,
): { price: number; publishedAt: number; ageSeconds: number } | null {
  if (!account || !account.owner.equals(pythProgram) || account.data.length < 134) return null;
  const data = account.data;
  const variant = data[40];
  // The sponsored Devnet feed is fully verified. Partial accounts are ignored.
  if (variant !== 1) return null;
  const feedStart = 41;
  if (!data.subarray(feedStart, feedStart + 32).equals(PYTH_SOL_USD_FEED)) return null;
  const priceOffset = feedStart + 32;
  const rawPrice = data.readBigInt64LE(priceOffset);
  const rawConfidence = data.readBigUInt64LE(priceOffset + 8);
  const exponent = data.readInt32LE(priceOffset + 16);
  const publishedAt = Number(data.readBigInt64LE(priceOffset + 20));
  const ageSeconds = Math.floor(Date.now() / 1000) - publishedAt;
  const price = Number(rawPrice) * 10 ** exponent;
  const confidence = Number(rawConfidence) * 10 ** exponent;
  if (rawPrice <= ZERO || ageSeconds < 0 || ageSeconds > MAX_PYTH_AGE_SECONDS || confidence / price > 0.01) return null;
  return { price, publishedAt, ageSeconds };
}

function associatedTokenAddress(
  owner: SolanaPublicKey,
  mint: SolanaPublicKey,
  PublicKey: typeof import('@solana/web3.js').PublicKey,
  tokenProgram: SolanaPublicKey,
  associatedProgram: SolanaPublicKey,
): SolanaPublicKey {
  return PublicKey.findProgramAddressSync(
    [owner.toBuffer(), tokenProgram.toBuffer(), mint.toBuffer()],
    associatedProgram,
  )[0];
}

function rawAmount(value: number, decimals: number): bigint {
  if (!Number.isFinite(value) || value <= 0) throw new Error('Enter a positive token amount.');
  const precision = 10 ** decimals;
  if (value * precision > Number.MAX_SAFE_INTEGER) throw new Error('The swap amount is too large.');
  return BigInt(Math.floor(value * precision));
}

function decimalAmount(raw: bigint, decimals: number): number {
  return Number(raw) / 10 ** decimals;
}

export function useSILEconomy() {
  const runtime = useRuntimeConfig();
  const market = useState<SILEconomyMarket | null>('sil-economy-market', () => null);
  const marketLoading = useState<boolean>('sil-economy-market-loading', () => false);
  const marketError = useState<string>('sil-economy-market-error', () => '');
  const marketFetchedAt = useState<number>('sil-economy-market-fetched-at', () => 0);
  const swapLoading = ref(false);
  const swapError = ref('');

  function rpcForDevnet(): string {
    const cluster = String(runtime.public.solanaCluster || 'devnet').trim().toLowerCase();
    const rpc = resolveSolanaRpcEndpoint(runtime.public.solanaRpc);
    if (cluster !== 'devnet' || !rpc || new URL(rpc).hostname.toLowerCase().includes('mainnet')) {
      throw new Error('SIL exchange is available only on Solana Devnet.');
    }
    return rpc;
  }

  async function refreshMarket(force = false): Promise<void> {
    if (!import.meta.client || marketLoading.value) return;
    if (!force && market.value && Date.now() - marketFetchedAt.value < 15_000) return;
    marketLoading.value = true;
    marketError.value = '';
    try {
      // Load web3.js only in the browser. Importing it during Nuxt SSR pulls
      // Jayson's browser client into Node's ESM module loader.
      const rpc = rpcForDevnet();
      const { Connection, PublicKey } = await import('@solana/web3.js');
      const connection = new Connection(rpc, 'confirmed');
      const devnetProgram = new PublicKey(DEVNET_CPMM_PROGRAM_ID);
      const silMint = new PublicKey(DEVNET_SIL_MINT_ID);
      const wsolMint = new PublicKey(WSOL_MINT_ID);
      const tokenProgram = new PublicKey(SPL_TOKEN_PROGRAM_ID);
      const associatedProgram = new PublicKey(ASSOCIATED_TOKEN_PROGRAM_ID);
      const pythProgram = new PublicKey(PYTH_RECEIVER_PROGRAM_ID);
      const poolId = new PublicKey(String(runtime.public.silPoolId || '66Un5iGRBuzE4kcVQkDkKrtZUVnTiXnxpUHoFL3mEsdS'));
      const poolResult = await connection.getAccountInfoAndContext(poolId, 'confirmed');
      const pool = poolResult.value;
      if (!pool || !pool.owner.equals(devnetProgram) || pool.data.length !== 637) {
        throw new Error('The SIL/SOL Devnet pool is not available.');
      }
      const poolData = pool.data;
      const vaultSol = publicKeyAt(poolData, 72, PublicKey);
      const vaultSil = publicKeyAt(poolData, 104, PublicKey);
      const mintSol = publicKeyAt(poolData, 168, PublicKey);
      const mintSil = publicKeyAt(poolData, 200, PublicKey);
      if (!mintSol.equals(wsolMint) || !mintSil.equals(silMint) || (poolData[329]! & 0x04) !== 0) {
        throw new Error('The configured Devnet pool does not match the SIL/SOL market.');
      }

      const poolAuthority = PublicKey.findProgramAddressSync(
        [Buffer.from('vault_and_lp_mint_auth_seed')],
        devnetProgram,
      )[0];
      const configId = publicKeyAt(poolData, 8, PublicKey);
      const [solVault, silVault, configAccount, pythAccount] = await connection.getMultipleAccountsInfo([
        vaultSol,
        vaultSil,
        configId,
        new PublicKey(PYTH_SOL_USD_ACCOUNT_ID),
      ], 'confirmed');
      if (!solVault || !silVault || !configAccount || !configAccount.owner.equals(devnetProgram)
        || configAccount.data.length < 20) {
        throw new Error('The SIL/SOL pool reserves could not be read from Devnet.');
      }

      const rawSol = tokenAmount(solVault, wsolMint, poolAuthority, tokenProgram, PublicKey);
      const rawSil = tokenAmount(silVault, silMint, poolAuthority, tokenProgram, PublicKey);
      // The pool keeps protocol and fund fees in its vaults; subtract those amounts
      // so the displayed spot price follows tradable reserves.
      const owedSol = poolData.readBigUInt64LE(341) + poolData.readBigUInt64LE(357) + poolData.readBigUInt64LE(397);
      const owedSil = poolData.readBigUInt64LE(349) + poolData.readBigUInt64LE(365) + poolData.readBigUInt64LE(405);
      const solReserveRaw = rawSol > owedSol ? rawSol - owedSol : ZERO;
      const silReserveRaw = rawSil > owedSil ? rawSil - owedSil : ZERO;
      const solReserve = decimalAmount(solReserveRaw, 9);
      const silReserve = decimalAmount(silReserveRaw, 6);
      if (solReserve <= 0 || silReserve <= 0) throw new Error('The SIL/SOL Devnet pool has no active liquidity.');

      const feeRate = Number(configAccount.data.readBigUInt64LE(12));
      const creatorFeeRate = poolData[390] === 1 ? Number(configAccount.data.readBigUInt64LE(108)) : 0;
      const pyth = parsePyth(pythAccount, pythProgram);
      const silPerSol = silReserve / solReserve;
      market.value = {
        poolId: poolId.toBase58(),
        solReserve,
        silReserve,
        silPerSol,
        solPerSil: 1 / silPerSol,
        solUsd: pyth?.price ?? null,
        silUsd: pyth ? pyth.price / silPerSol : null,
        tradeFeeBps: (feeRate + creatorFeeRate) / 100,
        slot: poolResult.context.slot,
        observedAt: Date.now(),
        pythPublishedAt: pyth?.publishedAt ?? null,
        pythAgeSeconds: pyth?.ageSeconds ?? null,
        oracleAvailable: Boolean(pyth),
      };
      marketFetchedAt.value = Date.now();
    } catch (failure) {
      market.value = null;
      marketError.value = failure instanceof Error ? failure.message : 'The Devnet SIL market is unavailable.';
    } finally {
      marketLoading.value = false;
    }
  }

  function quoteSwap(input: number, direction: SILSwapDirection): SILSwapQuote | null {
    const current = market.value;
    if (!current || !Number.isFinite(input) || input <= 0) return null;
    try {
      const buying = direction === 'buy';
      const inDecimals = buying ? 9 : 6;
      const outDecimals = buying ? 6 : 9;
      const reserveIn = BigInt(Math.round((buying ? current.solReserve : current.silReserve) * 10 ** inDecimals));
      const reserveOut = BigInt(Math.round((buying ? current.silReserve : current.solReserve) * 10 ** outDecimals));
      const amountIn = rawAmount(input, inDecimals);
      const rateRaw = BigInt(Math.round(current.tradeFeeBps * 100));
      const amountAfterFee = amountIn * (FEE_DENOMINATOR - rateRaw) / FEE_DENOMINATOR;
      const amountOut = amountAfterFee * reserveOut / (reserveIn + amountAfterFee);
      if (amountOut <= ZERO) return null;
      const spotOut = Number(amountIn) / Number(reserveIn) * Number(reserveOut);
      const priceImpactPercent = Math.max(0, (1 - Number(amountOut) / spotOut) * 100);
      const minimum = amountOut * BigInt(10_000 - SWAP_SLIPPAGE_BPS) / BPS_DENOMINATOR;
      return {
        input,
        output: decimalAmount(amountOut, outDecimals),
        minimumOutput: decimalAmount(minimum, outDecimals),
        priceImpactPercent,
        direction,
      };
    } catch {
      return null;
    }
  }

  async function swap(input: number, direction: SILSwapDirection, linkedWallet: string): Promise<string> {
    swapError.value = '';
    swapLoading.value = true;
    try {
      const rpc = rpcForDevnet();
      const { Connection, PublicKey, Transaction, VersionedTransaction } = await import('@solana/web3.js');
      const connection = new Connection(rpc, 'confirmed');
      const devnetSilMint = new PublicKey(DEVNET_SIL_MINT_ID);
      const wsolMint = new PublicKey(WSOL_MINT_ID);
      const tokenProgram = new PublicKey(SPL_TOKEN_PROGRAM_ID);
      const associatedProgram = new PublicKey(ASSOCIATED_TOKEN_PROGRAM_ID);
      const provider = import.meta.client ? phantomProvider(window) : null;
      if (!provider?.signTransaction) throw new Error('Install Phantom to sign the swap.');
      const connected = await provider.connect();
      const owner = new PublicKey(connected.publicKey.toString());
      if (!linkedWallet || owner.toBase58() !== linkedWallet) throw new Error('Connect the wallet linked to this account.');
      const buying = direction === 'buy';
      const inputMint = buying ? wsolMint : devnetSilMint;
      const outputMint = buying ? devnetSilMint : wsolMint;
      const amount = rawAmount(input, buying ? 9 : 6);
      const params = new URLSearchParams({
        inputMint: inputMint.toBase58(),
        outputMint: outputMint.toBase58(),
        amount: amount.toString(),
        slippageBps: String(SWAP_SLIPPAGE_BPS),
        txVersion: 'LEGACY',
      });
      const api = 'https://transaction-v1-devnet.raydium.io';
      const quoteResponse = await fetch(`${api}/compute/swap-base-in?${params.toString()}`);
      if (!quoteResponse.ok) throw new Error('Raydium Devnet could not produce a swap quote.');
      const swapQuote = await quoteResponse.json();
      if (!swapQuote.success || !swapQuote.data) throw new Error('No executable SIL/SOL route is available yet.');

      const inputAccount = buying ? undefined : associatedTokenAddress(owner, devnetSilMint, PublicKey, tokenProgram, associatedProgram).toBase58();
      const outputAccount = buying ? associatedTokenAddress(owner, devnetSilMint, PublicKey, tokenProgram, associatedProgram).toBase58() : undefined;
      const buildResponse = await fetch(`${api}/transaction/swap-base-in`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          computeUnitPriceMicroLamports: '1000',
          swapResponse: swapQuote,
          txVersion: 'LEGACY',
          wallet: owner.toBase58(),
          wrapSol: buying,
          unwrapSol: !buying,
          inputAccount,
          outputAccount,
        }),
      });
      if (!buildResponse.ok) throw new Error('Raydium Devnet could not build the swap transaction.');
      const buildResult = await buildResponse.json();
      if (!buildResult.success) throw new Error('Raydium Devnet rejected the swap request.');
      const transactionRows = Array.isArray(buildResult.data) ? buildResult.data : [buildResult.data];
      const signatures: string[] = [];
      for (const row of transactionRows) {
        if (typeof row?.transaction !== 'string') throw new Error('Raydium returned an invalid swap transaction.');
        const serialized = Buffer.from(row.transaction, 'base64');
        let transaction: SolanaTransaction | SolanaVersionedTransaction;
        try {
          transaction = Transaction.from(serialized);
        } catch {
          transaction = VersionedTransaction.deserialize(serialized);
        }
        const signed = await provider.signTransaction(transaction);
        const signature = await connection.sendRawTransaction(signed.serialize(), {
          maxRetries: 3,
          preflightCommitment: 'confirmed',
        });
        const confirmation = await connection.confirmTransaction(signature, 'confirmed');
        if (confirmation.value.err) throw new Error('Solana rejected the Devnet swap.');
        signatures.push(signature);
      }
      if (!signatures.length) throw new Error('Raydium did not return a swap transaction.');
      await refreshMarket(true);
      return signatures.at(-1)!;
    } catch (failure) {
      swapError.value = failure instanceof Error ? failure.message : 'The SIL/SOL swap could not be completed.';
      throw failure;
    } finally {
      swapLoading.value = false;
    }
  }

  return { market, marketLoading, marketError, swapLoading, swapError, refreshMarket, quoteSwap, swap };
}
