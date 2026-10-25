const DEVNET_RPC_FALLBACK = 'https://api.devnet.solana.com';

/** Resolve same-origin Devnet relay paths for browser-side web3.js clients. */
export function resolveSolanaRpcEndpoint(configured: unknown): string {
  const endpoint = String(configured ?? '').trim();
  if (!endpoint) return DEVNET_RPC_FALLBACK;
  if (endpoint.startsWith('/') && !endpoint.startsWith('//')) {
    if (typeof window === 'undefined') return DEVNET_RPC_FALLBACK;
    return new URL(endpoint, window.location.origin).toString();
  }
  return endpoint;
}
