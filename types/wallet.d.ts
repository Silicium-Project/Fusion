export {};

/** The Solana provider that Phantom injects in the page. */
export interface PhantomProvider {
  isPhantom?: boolean;
  publicKey?: { toString(): string };
  connect(): Promise<{ publicKey: { toString(): string } }>;
  disconnect?(): Promise<void>;
  signMessage(message: Uint8Array, display?: string): Promise<{ signature: Uint8Array }>;
}

declare global {
  interface Window {
    /** Where current Phantom versions expose the provider. */
    phantom?: { solana?: PhantomProvider };
    /** Older location, kept by Phantom for compatibility. */
    solana?: PhantomProvider;
  }
}
