import type { WalletChallenge } from '~/types/api';
import { isUserRejection, phantomProvider } from '~/utils/wallet';
import { extractJobError } from '~/utils/jobs';
import { translate } from '~/utils/i18n';
import { resolveSolanaRpcEndpoint } from '~/utils/solanaRpc';

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 1) binary += String.fromCharCode(bytes[index]!);
  return window.btoa(binary);
}

export function useWallet() {
  const { authorizedFetch, loadUser } = useSession();
  const config = useRuntimeConfig();
  const connecting = ref(false);
  const balance = ref<number | null>(null);
  const silBalance = ref<number | null>(null);
  const balanceError = ref('');
  const error = ref('');

  async function balanceFor(address: string): Promise<number> {
    const { Connection, PublicKey, LAMPORTS_PER_SOL } = await import('@solana/web3.js');
    const connection = new Connection(resolveSolanaRpcEndpoint(config.public.solanaRpc), 'confirmed');
    return (await connection.getBalance(new PublicKey(address))) / LAMPORTS_PER_SOL;
  }

  async function silBalanceFor(address: string): Promise<number | null> {
    const mintAddress = String(config.public.silMint || '').trim();
    if (!mintAddress) return null;
    const { Connection, PublicKey } = await import('@solana/web3.js');
    const connection = new Connection(resolveSolanaRpcEndpoint(config.public.solanaRpc), 'confirmed');
    const accounts = await connection.getParsedTokenAccountsByOwner(
      new PublicKey(address),
      { mint: new PublicKey(mintAddress) },
      'confirmed',
    );
    let rawAmount = 0n;
    let decimals = 6;
    for (const account of accounts.value) {
      const tokenAmount = account.account.data.parsed.info.tokenAmount;
      rawAmount += BigInt(tokenAmount.amount || '0');
      decimals = Number(tokenAmount.decimals ?? decimals);
    }
    return Number(rawAmount) / (10 ** decimals);
  }

  async function refreshBalances(address: string): Promise<void> {
    const [sol, sil] = await Promise.allSettled([balanceFor(address), silBalanceFor(address)]);
    balance.value = sol.status === 'fulfilled' ? sol.value : null;
    silBalance.value = sil.status === 'fulfilled' ? sil.value : null;
    balanceError.value = sil.status === 'rejected' || sil.status === 'fulfilled' && sil.value === null
      ? translate('errors.walletBalanceUnavailable')
      : '';
  }

  async function connect(): Promise<string> {
    error.value = '';
    const provider = import.meta.client ? phantomProvider(window) : null;
    if (!provider) {
      // Shown under the button: without it, the click seemed to do nothing.
      error.value = translate('errors.phantomRequired');
      throw new Error(error.value);
    }
    connecting.value = true;
    try {
      const connection = await provider.connect();
      const walletAddress = connection.publicKey.toString();
      const challenge = await authorizedFetch<WalletChallenge>('/user/wallet/challenge', {
        method: 'POST', body: { walletAddress },
      });
      const signed = await provider.signMessage(new TextEncoder().encode(challenge.message), 'utf8');
      await authorizedFetch('/user/wallet', {
        method: 'POST',
        body: { walletAddress, challenge: challenge.challenge, signature: bytesToBase64(signed.signature) },
      });
      await refreshBalances(walletAddress);
      await loadUser(true);
      return walletAddress;
    } catch (failure) {
      error.value = isUserRejection(failure)
        ? translate('errors.walletRejected')
        : extractJobError(failure, translate('errors.walletFailed'));
      throw failure;
    } finally {
      connecting.value = false;
    }
  }

  async function loadBalance(address?: string): Promise<void> {
    if (!address || !import.meta.client) return;
    await refreshBalances(address);
  }

  return { connecting, balance, silBalance, balanceError, error, connect, loadBalance };
}
