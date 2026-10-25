import * as anchor from '@coral-xyz/anchor';
import { Program } from '@coral-xyz/anchor';
import { SiliciumLayerSdk, SdkEventName } from '../src';

async function main() {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace.SolanaLayer as Program;
  const sdk = SiliciumLayerSdk.fromWorkspace(provider, program as any);

  console.log('Listening to all Silicium events...');
  console.log('Wallet:', provider.wallet.publicKey.toBase58());
  console.log('Program:', sdk.program.programId.toBase58());

  const subscriptions = sdk.events.onAll(
    (eventName: SdkEventName, event: unknown, slot: number, signature: string) => {
      console.log('\n================ EVENT ================');
      console.log('name:', eventName);
      console.log('slot:', slot);
      console.log('signature:', signature);
      console.dir(event, { depth: null });
      console.log('=======================================\n');
    },
  );

  console.log('Active listeners:', subscriptions.length);
  console.log('Now trigger an instruction in another terminal.');

  process.on('SIGINT', async () => {
    console.log('\nRemoving listeners...');
    for (const sub of subscriptions) {
      await sub.remove();
    }
    process.exit(0);
  });

  await new Promise(() => {});
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
