import * as anchor from '@coral-xyz/anchor';
import { Connection } from '@solana/web3.js';
import { SiliciumLayerSdk } from '../src';

async function main() {
  const connection = new Connection('http://127.0.0.1:8899', 'confirmed');

  const wallet = anchor.Wallet.local();

  const provider = new anchor.AnchorProvider(connection, wallet, {
    commitment: 'confirmed',
    preflightCommitment: 'confirmed',
  });

  anchor.setProvider(provider);

  const program = anchor.workspace.SolanaLayer;
  const sdk = SiliciumLayerSdk.fromWorkspace(provider, program);

  console.log('SDK loaded');
  console.log('Wallet:', wallet.publicKey.toBase58());
  console.log('Program:', sdk.programId.toBase58());

  const workerAccount = sdk.pdas.worker(wallet.publicKey);

  console.log('Expected worker PDA:', workerAccount.toBase58());

  const before = await provider.connection.getAccountInfo(workerAccount, 'confirmed');

  if (before) {
    console.log('Worker already exists, fetching...');
    const worker = await sdk.fetchWorker(workerAccount, true);
    console.log('Worker data:', worker);
    return;
  }

  const sig = await sdk.registerWorker();

  console.log('Worker registered tx:', sig);

  await provider.connection.confirmTransaction(sig, 'confirmed');

  const worker = await sdk.fetchWorker(workerAccount, true);

  console.log('Worker account:', workerAccount.toBase58());
  console.log('Worker data:', worker);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
