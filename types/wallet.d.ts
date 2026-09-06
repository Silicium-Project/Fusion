export {};

declare global {
  interface Window {
    solana?: {
      isPhantom?: boolean;
      publicKey?: { toString(): string };
      connect(): Promise<{ publicKey: { toString(): string } }>;
      disconnect?(): Promise<void>;
      signMessage(message: Uint8Array, display?: string): Promise<{ signature: Uint8Array }>;
    };
  }
}
