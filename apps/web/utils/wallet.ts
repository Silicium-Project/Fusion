// Phantom wallet helpers, without the page: which provider to use and how
// to recognize a request the user refused.
import type { PhantomProvider } from '../types/wallet';

/** The Phantom provider of the page, if the extension is installed. */
export function phantomProvider(
  source: Pick<Window, 'phantom' | 'solana'>,
): PhantomProvider | null {
  const provider = source.phantom?.solana ?? source.solana;
  return provider?.isPhantom ? provider : null;
}

/** True when the user closed or refused the Phantom request. */
export const isUserRejection = (failure: unknown): boolean => {
  const code = (failure as { code?: unknown } | null)?.code;
  return code === 4001 || code === 'ACTION_REJECTED';
};
