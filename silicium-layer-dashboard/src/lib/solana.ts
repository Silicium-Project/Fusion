import { AnchorProvider, Program, Idl, Wallet } from "@coral-xyz/anchor";
import { Connection, PublicKey, Keypair } from "@solana/web3.js";

export const DEVNET_PROGRAM_ID = "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2";
export const DEVNET_RPC = "https://api.devnet.solana.com";
export const LOCALNET_RPC = "http://127.0.0.1:8899";

export type ClusterName = "devnet" | "localnet" | "custom";

class ReadonlyWallet implements Wallet {
  readonly payer = Keypair.generate();
  readonly publicKey = this.payer.publicKey;

  async signTransaction<T>(tx: T): Promise<T> {
    return tx;
  }

  async signAllTransactions<T>(txs: T[]): Promise<T[]> {
    return txs;
  }
}

export function makeConnection(rpcUrl: string): Connection {
  return new Connection(rpcUrl, "confirmed");
}

export function makeReadonlyProgram(idl: Idl, rpcUrl: string, programId: string): Program {
  const connection = makeConnection(rpcUrl);
  const provider = new AnchorProvider(connection, new ReadonlyWallet(), {
    commitment: "confirmed",
  });
  // Anchor 0.32 resolves the program address from the IDL. Keep the
  // dashboard's explicit cluster selection authoritative so a stale/generated
  // IDL cannot silently query a different deployed program.
  const configuredIdl = { ...idl, address: new PublicKey(programId).toBase58() } as Idl;
  return new Program(configuredIdl, provider);
}

export function toPublicKey(value: string): PublicKey | null {
  try {
    return new PublicKey(value);
  } catch {
    return null;
  }
}

export function shortKey(value?: string | PublicKey | null, left = 4, right = 4): string {
  if (!value) return "—";
  const s = typeof value === "string" ? value : value.toBase58();
  if (s.length <= left + right + 3) return s;
  return `${s.slice(0, left)}…${s.slice(-right)}`;
}

export function enumName(value: unknown): string {
  if (!value) return "unknown";
  if (typeof value === "string") return value;
  if (typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>);
    return keys[0] ?? "unknown";
  }
  return String(value);
}

export function toNum(value: any): number {
  if (value == null) return 0;
  if (typeof value === "number") return value;
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "string") return Number(value) || 0;
  if (typeof value.toNumber === "function") return value.toNumber();
  if (typeof value.toString === "function") return Number(value.toString()) || 0;
  return 0;
}

export function toBase58(value: any): string {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (typeof value.toBase58 === "function") return value.toBase58();
  return String(value);
}

export async function safeAll(program: any, accountName: string): Promise<Array<{ publicKey: PublicKey; account: any }>> {
  try {
    const accountApi = program.account?.[accountName];
    if (!accountApi?.all) return [];
    return await accountApi.all();
  } catch (err) {
    console.warn(`Failed fetching ${accountName}`, err);
    return [];
  }
}
