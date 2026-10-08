import { describe, expect, it } from 'vitest';
import { isUserRejection, phantomProvider } from '../utils/wallet';

const provider = (isPhantom: boolean) => ({ isPhantom, connect: async () => ({ publicKey: { toString: () => 'k' } }), signMessage: async () => ({ signature: new Uint8Array() }) });

describe('wallet helpers', () => {
  it('finds Phantom where current and older versions put it', () => {
    const current = provider(true);
    expect(phantomProvider({ phantom: { solana: current } })).toBe(current);
    const older = provider(true);
    expect(phantomProvider({ solana: older })).toBe(older);
    expect(phantomProvider({})).toBeNull();
    expect(phantomProvider({ solana: provider(false) })).toBeNull();
  });

  it('recognizes a request refused in the wallet', () => {
    expect(isUserRejection({ code: 4001, message: 'User rejected the request.' })).toBe(true);
    expect(isUserRejection(new Error('network'))).toBe(false);
    expect(isUserRejection(null)).toBe(false);
  });
});
