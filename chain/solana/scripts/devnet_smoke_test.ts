/**
 * Silicium Solana Layer — Devnet smoke test V2.5
 *
 * Put this file in:
 *   solana-layer/scripts/devnet_smoke_test.ts
 *
 * Read-only:
 *   npx ts-node scripts/devnet_smoke_test.ts
 *
 * Write smoke:
 *   npx ts-node scripts/devnet_smoke_test.ts --write
 */

import * as anchor from '@coral-xyz/anchor';
import { Connection, PublicKey, SystemProgram, Keypair } from '@solana/web3.js';
import fs from 'fs';
import os from 'os';
import path from 'path';

const DEVNET_RPC = process.env.SOLANA_RPC_URL ?? 'https://api.devnet.solana.com';
const PROGRAM_ID = new PublicKey(
  process.env.SOLANA_LAYER_PROGRAM_ID ?? '64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG',
);
const WRITE_MODE = process.argv.includes('--write');

function logStep(title: string) {
  console.log(`\n=== ${title} ===`);
}

function readKeypair(filePath: string): Keypair {
  const resolved = filePath.startsWith('~') ? path.join(os.homedir(), filePath.slice(1)) : filePath;
  return Keypair.fromSecretKey(Uint8Array.from(JSON.parse(fs.readFileSync(resolved, 'utf8'))));
}

function loadIdl(): any {
  const candidates = [
    path.resolve(process.cwd(), 'target/idl/solana_layer.json'),
    path.resolve(process.cwd(), 'solana-layer/target/idl/solana_layer.json'),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      const idl = JSON.parse(fs.readFileSync(candidate, 'utf8'));
      idl.address = PROGRAM_ID.toBase58();
      return idl;
    }
  }

  throw new Error('IDL not found. Run `anchor build` from solana-layer/ first.');
}

function workerPda(owner: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync([Buffer.from('worker'), owner.toBuffer()], PROGRAM_ID)[0];
}

function rep(value: any): number {
  return Number(value?.toString?.() ?? value ?? 0);
}

function formatWorker(workerState: any) {
  return {
    owner: workerState.owner?.toBase58?.() ?? String(workerState.owner),
    computeReputation: rep(workerState.computeReputation),
    verifyReputation: rep(workerState.verifyReputation),
    storageReputation: rep(workerState.storageReputation),
    globalReputation: rep(workerState.globalReputation),
    stakeAmount: rep(workerState.stakeAmount),
    status: workerState.status,
  };
}

async function main() {
  logStep('Devnet connection');
  const connection = new Connection(DEVNET_RPC, 'confirmed');
  const version = await connection.getVersion();
  const slot = await connection.getSlot('confirmed');
  console.log('rpc:', DEVNET_RPC);
  console.log('slot:', slot);
  console.log('solana-core:', version['solana-core']);

  logStep('Program account');
  const programInfo = await connection.getAccountInfo(PROGRAM_ID, 'confirmed');
  if (!programInfo) throw new Error(`Program not found on Devnet: ${PROGRAM_ID.toBase58()}`);

  console.log('programId:', PROGRAM_ID.toBase58());
  console.log('owner:', programInfo.owner.toBase58());
  console.log('executable:', programInfo.executable);
  console.log('dataLength:', programInfo.data.length);
  console.log('lamports:', programInfo.lamports);

  if (!programInfo.executable) throw new Error('Program account exists but is not executable.');
  if (programInfo.data.length === 0) throw new Error('Program account has empty data.');

  logStep('IDL and Anchor client');
  const idl = loadIdl();
  console.log('idl name:', idl.name ?? idl.metadata?.name ?? 'unknown');
  console.log('instructions:', idl.instructions?.length ?? 0);
  console.log('accounts:', idl.accounts?.length ?? 0);
  console.log('events:', idl.events?.length ?? 0);

  const walletPath = process.env.ANCHOR_WALLET ?? '~/.config/solana/id.json';
  const payer = readKeypair(walletPath);
  const wallet = new anchor.Wallet(payer);
  const provider = new anchor.AnchorProvider(connection, wallet, {
    commitment: 'confirmed',
    preflightCommitment: 'confirmed',
  });
  anchor.setProvider(provider);

  const program = new (anchor as any).Program(idl, provider) as any;
  console.log('wallet:', wallet.publicKey.toBase58());
  console.log('client program:', program.programId.toBase58());

  const balance = await connection.getBalance(wallet.publicKey, 'confirmed');
  console.log('wallet balance:', balance / anchor.web3.LAMPORTS_PER_SOL, 'SOL');

  logStep('Worker PDA check');
  const workerAccount = workerPda(wallet.publicKey);
  const workerInfo = await connection.getAccountInfo(workerAccount, 'confirmed');
  console.log('workerPda:', workerAccount.toBase58());
  console.log('worker exists:', Boolean(workerInfo));

  if (!WRITE_MODE) {
    if (workerInfo) {
      const workerState = await program.account.worker.fetch(workerAccount);
      console.log('worker V2.5 reputation:', formatWorker(workerState));
    }
    console.log('\n✅ Read-only Devnet smoke test passed');
    console.log('Run with `--write` to also call registerWorker if needed.');
    return;
  }

  logStep('Write smoke: registerWorker');
  if (balance < 50_000_000) {
    throw new Error('Wallet balance is too low for write smoke test. Need at least ~0.05 SOL.');
  }

  if (workerInfo) {
    const workerState = await program.account.worker.fetch(workerAccount);
    console.log('worker already registered:', formatWorker(workerState));
  } else {
    const sig = await program.methods
      .registerWorker()
      .accounts({
        worker: wallet.publicKey,
        workerAccount,
        workerPayout: PublicKey.findProgramAddressSync(
          [Buffer.from('worker_payout'), workerAccount.toBuffer()],
          program.programId,
        )[0],
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    console.log('registerWorker tx:', sig);
    const workerState = await program.account.worker.fetch(workerAccount);
    console.log('worker registered:', formatWorker(workerState));
  }

  console.log('\n✅ Devnet write smoke test passed');
}

main().catch((error) => {
  console.error('\n❌ Devnet smoke test failed');
  console.error(error);
  process.exit(1);
});
