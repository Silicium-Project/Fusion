import type { WalletChallenge } from '~/types/api';
import { extractJobError } from '~/utils/jobs';
import { translate } from '~/utils/i18n';

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
  const error = ref('');

  async function balanceFor(address: string): Promise<number> {
    const { Connection, PublicKey, LAMPORTS_PER_SOL } = await import('@solana/web3.js');
    const connection = new Connection(String(config.public.solanaRpc), 'confirmed');
    return (await connection.getBalance(new PublicKey(address))) / LAMPORTS_PER_SOL;
  }

  async function connect(): Promise<string> {
    if (!import.meta.client || !window.solana?.isPhantom) {
      throw new Error(translate('errors.phantomRequired'));
    }
    connecting.value = true;
    error.value = '';
    try {
      const provider = window.solana;
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
      balance.value = await balanceFor(walletAddress).catch(() => null);
      await loadUser(true);
      return walletAddress;
    } catch (failure) {
      error.value = extractJobError(failure, translate('errors.walletFailed'));
      throw failure;
    } finally {
      connecting.value = false;
    }
  }

  async function loadBalance(address?: string): Promise<void> {
    if (!address || !import.meta.client) return;
    balance.value = await balanceFor(address).catch(() => null);
  }

  return { connecting, balance, error, connect, loadBalance };
}
