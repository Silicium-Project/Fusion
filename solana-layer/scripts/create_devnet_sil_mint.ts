/** Create or inspect the project's six-decimal SIL test mint on Devnet. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createMint, createAssociatedTokenAccount, getAssociatedTokenAddress, mintTo, getMint, getAccount } from "@solana/spl-token";
import { Connection, Keypair, LAMPORTS_PER_SOL, PublicKey } from "@solana/web3.js";

const RPC_URL = process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
const DEFAULT_STATE_DIR = path.resolve(process.cwd(), "../.silicium/solana");
const AUTHORITY_PATH = process.env.SILICIUM_TEST_MINT_AUTHORITY_FILE
  ?? path.join(DEFAULT_STATE_DIR, "test-mint-authority.json");
const STATE_PATH = path.join(DEFAULT_STATE_DIR, "test-sil-mint.json");
const TOKEN_DECIMALS = 6;
const INITIAL_SUPPLY = 1_000_000_000_000n; // 1,000,000 SIL

function assertDevnet(url: string): void {
  const host = new URL(url).hostname.toLowerCase();
  if (!host.includes("devnet") && process.env.SILICIUM_ALLOW_CUSTOM_DEVNET_RPC !== "1") {
    throw new Error("Refusing to run: SOLANA_RPC_URL must point to Devnet (custom Devnet RPC requires SILICIUM_ALLOW_CUSTOM_DEVNET_RPC=1).");
  }
}

function writeKeypair(pathname: string, keypair: Keypair): void {
  fs.mkdirSync(path.dirname(pathname), { recursive: true, mode: 0o700 });
  fs.writeFileSync(pathname, JSON.stringify(Array.from(keypair.secretKey)), { flag: "wx", mode: 0o600 });
}

function loadOrCreateAuthority(): Keypair {
  if (fs.existsSync(AUTHORITY_PATH)) {
    const metadata = fs.lstatSync(AUTHORITY_PATH);
    if (!metadata.isFile() || metadata.isSymbolicLink()) throw new Error("Mint authority must be a regular keypair file.");
    fs.chmodSync(AUTHORITY_PATH, 0o600);
    return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(AUTHORITY_PATH, "utf8"))));
  }
  const keypair = Keypair.generate();
  writeKeypair(AUTHORITY_PATH, keypair);
  return keypair;
}

async function main(): Promise<void> {
  assertDevnet(RPC_URL);
  const connection = new Connection(RPC_URL, "confirmed");
  const authority = loadOrCreateAuthority();
  console.log(`RPC: ${new URL(RPC_URL).origin}`);
  console.log(`Mint authority: ${authority.publicKey.toBase58()}`);

  let mint: PublicKey;
  if (fs.existsSync(STATE_PATH)) {
    const state = JSON.parse(fs.readFileSync(STATE_PATH, "utf8")) as { mint: string; authority: string };
    if (state.authority !== authority.publicKey.toBase58()) throw new Error("Saved mint authority does not match the authority keypair.");
    mint = new PublicKey(state.mint);
    const info = await getMint(connection, mint, "confirmed");
    if (info.decimals !== TOKEN_DECIMALS || !info.mintAuthority?.equals(authority.publicKey)) {
      throw new Error("Saved SIL mint has unexpected decimals or mint authority.");
    }
    console.log(`SIL mint already exists: ${mint.toBase58()}`);
  } else {
    const balance = await connection.getBalance(authority.publicKey, "confirmed");
    if (balance < 0.05 * LAMPORTS_PER_SOL) {
      console.log("Requesting 0.1 Devnet SOL for mint creation fees…");
      const signature = await connection.requestAirdrop(authority.publicKey, LAMPORTS_PER_SOL / 10);
      const latest = await connection.getLatestBlockhash("confirmed");
      await connection.confirmTransaction({ signature, ...latest }, "confirmed");
    }
    mint = await createMint(connection, authority, authority.publicKey, null, TOKEN_DECIMALS);
    fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true, mode: 0o700 });
    fs.writeFileSync(STATE_PATH, JSON.stringify({
      cluster: "devnet",
      mint: mint.toBase58(),
      decimals: TOKEN_DECIMALS,
      authority: authority.publicKey.toBase58(),
    }, null, 2) + "\n", { flag: "wx", mode: 0o600 });
    console.log(`Created six-decimal SIL test mint: ${mint.toBase58()}`);
  }

  const account = await getAssociatedTokenAddress(mint, authority.publicKey);
  if (!(await connection.getAccountInfo(account, "confirmed"))) {
    await createAssociatedTokenAccount(connection, authority, mint, authority.publicKey);
  }
  const current = await getAccount(connection, account, "confirmed");
  if (current.amount < INITIAL_SUPPLY) {
    await mintTo(connection, authority, mint, account, authority, INITIAL_SUPPLY - current.amount);
  }
  console.log(`Authority token account: ${account.toBase58()}`);
  console.log(`Authority test balance: ${(await getAccount(connection, account, "confirmed")).amount.toString()} base units`);
  console.log("Mint authority key remains in the local ignored .silicium directory; only its public address was printed.");
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "unknown failure";
  console.error(`SIL Devnet mint setup failed: ${message}`);
  process.exitCode = 1;
});
