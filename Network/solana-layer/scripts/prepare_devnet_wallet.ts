import { Connection, Keypair, LAMPORTS_PER_SOL } from "@solana/web3.js";
import fs from "fs";
import os from "os";
import path from "path";

const DEVNET_RPC = process.env.SOLANA_RPC_URL ?? "https://api.devnet.solana.com";
const NETWORK_ROOT = path.resolve(__dirname, "..", "..");

function resolveHome(value: string): string {
  return value.startsWith("~") ? path.join(os.homedir(), value.slice(1)) : value;
}

function defaultWalletPath(): string {
  return path.join(NETWORK_ROOT, ".silicium", "solana", "id.json");
}

function readOrCreateKeypair(walletPath: string): { keypair: Keypair; created: boolean } {
  if (fs.existsSync(walletPath)) {
    return {
      keypair: Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(walletPath, "utf8")))),
      created: false,
    };
  }
  const keypair = Keypair.generate();
  fs.mkdirSync(path.dirname(walletPath), { recursive: true });
  fs.writeFileSync(walletPath, JSON.stringify(Array.from(keypair.secretKey)), "utf8");
  return { keypair, created: true };
}

async function confirmAirdrop(connection: Connection, signature: string) {
  const latest = await connection.getLatestBlockhash("confirmed");
  await connection.confirmTransaction(
    {
      signature,
      blockhash: latest.blockhash,
      lastValidBlockHeight: latest.lastValidBlockHeight,
    },
    "confirmed",
  );
}

async function main() {
  const walletPath = path.resolve(resolveHome(process.argv[2] || process.env.ANCHOR_WALLET || defaultWalletPath()));
  const targetSol = Number(process.env.SILICIUM_DEVNET_TARGET_SOL ?? "2");
  const connection = new Connection(DEVNET_RPC, "confirmed");
  const { keypair, created } = readOrCreateKeypair(walletPath);

  let balance = await connection.getBalance(keypair.publicKey, "confirmed");
  const targetLamports = Math.floor(targetSol * LAMPORTS_PER_SOL);
  const airdropSignatures: string[] = [];
  const airdropErrors: string[] = [];

  if (balance < targetLamports) {
    const chunks = [
      Math.min(targetLamports - balance, LAMPORTS_PER_SOL),
      Math.min(targetLamports - balance, Math.floor(0.5 * LAMPORTS_PER_SOL)),
      Math.min(targetLamports - balance, Math.floor(0.25 * LAMPORTS_PER_SOL)),
    ].filter((value, index, values) => value > 0 && values.indexOf(value) === index);

    for (const lamports of chunks) {
      for (let attempt = 1; attempt <= 3 && balance < targetLamports; attempt += 1) {
        try {
          const signature = await connection.requestAirdrop(keypair.publicKey, lamports);
          await confirmAirdrop(connection, signature);
          airdropSignatures.push(signature);
          balance = await connection.getBalance(keypair.publicKey, "confirmed");
        } catch (error) {
          airdropErrors.push(`attempt=${attempt} lamports=${lamports} error=${String(error)}`);
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    }
  }

  console.log(
    JSON.stringify(
      {
        ok: balance > 0,
        wallet_path: walletPath,
        created,
        public_key: keypair.publicKey.toBase58(),
        rpc: DEVNET_RPC,
        balance_sol: balance / LAMPORTS_PER_SOL,
        airdrop_signatures: airdropSignatures,
        airdrop_errors: airdropErrors.slice(-5),
        faucet_hint: balance > 0 ? "" : "Use a Devnet faucet with the printed public_key, then rerun this helper.",
      },
      null,
      2,
    ),
  );
  if (balance <= 0) {
    process.exitCode = 2;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
