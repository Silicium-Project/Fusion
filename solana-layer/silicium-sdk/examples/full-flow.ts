import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import {
  Keypair,
  LAMPORTS_PER_SOL,
  PublicKey,
  TransactionSignature,
} from "@solana/web3.js";
import {
  createAccount,
  createMint,
  getAccount,
  mintTo,
} from "@solana/spl-token";
import {
  EventSubscription,
  SiliciumLayerSdk,
  SdkEventName,
} from "../src";

type NodeWalletWithPayer = anchor.Wallet & { payer: Keypair };

function randomHash(seed: number): number[] {
  return Array.from({ length: 32 }, (_, index) => (seed + index) % 256);
}

async function confirm(
  provider: anchor.AnchorProvider,
  signature: TransactionSignature,
  label: string,
): Promise<void> {
  const latest = await provider.connection.getLatestBlockhash();

  await provider.connection.confirmTransaction(
    {
      signature,
      blockhash: latest.blockhash,
      lastValidBlockHeight: latest.lastValidBlockHeight,
    },
    "confirmed",
  );

  console.log(`✅ ${label}: ${signature}`);
}

async function airdropSol(
  provider: anchor.AnchorProvider,
  pubkey: PublicKey,
  sol = 3,
): Promise<void> {
  const signature = await provider.connection.requestAirdrop(
    pubkey,
    sol * LAMPORTS_PER_SOL,
  );

  await confirm(provider, signature, `airdrop ${sol} SOL to ${pubkey.toBase58()}`);
}

async function printTokenBalance(
  label: string,
  account: PublicKey,
  provider: anchor.AnchorProvider,
): Promise<void> {
  const data = await getAccount(provider.connection, account);
  console.log(`${label}: ${data.amount.toString()}`);
}

async function main(): Promise<void> {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);

  const program = anchor.workspace.SolanaLayer as Program;
  const sdk = SiliciumLayerSdk.fromWorkspace(provider, program as any);

  const payer = (provider.wallet as NodeWalletWithPayer).payer;

  if (!payer) {
    throw new Error("This script expects AnchorProvider.env() with a local NodeWallet payer.");
  }

  console.log("\n=== Silicium SDK full local flow ===");
  console.log("Wallet:", provider.wallet.publicKey.toBase58());
  console.log("Program:", sdk.program.programId.toBase58());

  const subscriptions: EventSubscription[] = sdk.events.onAll(
    (eventName: SdkEventName, event: unknown, slot: number, signature: string) => {
      console.log(`\n📣 EVENT ${eventName} | slot=${slot} | tx=${signature}`);
      console.dir(event, { depth: null });
    },
  );

  const computeWorker = Keypair.generate();
  const verifier1 = Keypair.generate();
  const verifier2 = Keypair.generate();

  await airdropSol(provider, computeWorker.publicKey, 3);
  await airdropSol(provider, verifier1.publicKey, 3);
  await airdropSol(provider, verifier2.publicKey, 3);

  console.log("\n--- SPL token setup ---");

  const mint = await createMint(
    provider.connection,
    payer,
    payer.publicKey,
    null,
    6,
  );

  console.log("Mint:", mint.toBase58());

  const clientToken = await createAccount(
    provider.connection,
    payer,
    mint,
    provider.wallet.publicKey,
  );

  const computeWorkerToken = await createAccount(
    provider.connection,
    payer,
    mint,
    computeWorker.publicKey,
  );

  const verifier1Token = await createAccount(
    provider.connection,
    payer,
    mint,
    verifier1.publicKey,
  );

  const verifier2Token = await createAccount(
    provider.connection,
    payer,
    mint,
    verifier2.publicKey,
  );

  await mintTo(provider.connection, payer, mint, clientToken, payer, 10_000_000);
  await mintTo(provider.connection, payer, mint, computeWorkerToken, payer, 1_000_000);
  await mintTo(provider.connection, payer, mint, verifier1Token, payer, 1_000_000);
  await mintTo(provider.connection, payer, mint, verifier2Token, payer, 1_000_000);

  await printTokenBalance("Client token balance", clientToken, provider);
  await printTokenBalance("Compute worker token balance", computeWorkerToken, provider);
  await printTokenBalance("Verifier 1 token balance", verifier1Token, provider);
  await printTokenBalance("Verifier 2 token balance", verifier2Token, provider);

  console.log("\n--- Worker and verifier registration/staking ---");

  await confirm(
    provider,
    await sdk.registerWorker({
      worker: computeWorker.publicKey,
      signers: [computeWorker],
    }),
    "register compute worker",
  );

  await confirm(
    provider,
    await sdk.registerWorker({
      worker: verifier1.publicKey,
      signers: [verifier1],
    }),
    "register verifier 1",
  );

  await confirm(
    provider,
    await sdk.registerWorker({
      worker: verifier2.publicKey,
      signers: [verifier2],
    }),
    "register verifier 2",
  );

  await confirm(
    provider,
    await sdk.stakeWorker({
      worker: computeWorker.publicKey,
      workerToken: computeWorkerToken,
      mint,
      amount: 100,
      signers: [computeWorker],
    }),
    "stake compute worker",
  );

  await confirm(
    provider,
    await sdk.stakeWorker({
      worker: verifier1.publicKey,
      workerToken: verifier1Token,
      mint,
      amount: 100,
      signers: [verifier1],
    }),
    "stake verifier 1",
  );

  await confirm(
    provider,
    await sdk.stakeWorker({
      worker: verifier2.publicKey,
      workerToken: verifier2Token,
      mint,
      amount: 100,
      signers: [verifier2],
    }),
    "stake verifier 2",
  );

  console.log("\n--- Job / fragment / verification flow ---");

  const escrow = Keypair.generate();
  const jobId = new anchor.BN(Date.now());
  const nowUnix = Math.floor(Date.now() / 1000);

  const expectedFragments = 1;

  // Montants volontairement hauts pour passer MIN_JOB_DEPOSIT en test local.
  const rewardPerFragment = 1_000_000;
  const verifierRewardPerVote = 100_000;
  const fragmentQuorum = 2;

  const verifierRewardBudget =
    expectedFragments * fragmentQuorum * verifierRewardPerVote;

  const totalJobDeposit =
    expectedFragments * rewardPerFragment + verifierRewardBudget;

  console.log("Job deposit debug:");
  console.log("expectedFragments:", expectedFragments);
  console.log("rewardPerFragment:", rewardPerFragment);
  console.log("verifierRewardPerVote:", verifierRewardPerVote);
  console.log("fragmentQuorum:", fragmentQuorum);
  console.log("verifierRewardBudget:", verifierRewardBudget);
  console.log("totalJobDeposit:", totalJobDeposit);

  const created = await sdk.createJob({
    mint,
    clientToken,
    escrow,
    jobId,
    expectedFragments,
    rewardPerFragment,
    verifierRewardPerVote,
    verifierRewardBudget,
    deadlineUnix: nowUnix + 600,
    fragmentQuorum,
  });

  await confirm(provider, created.signature, "create job");

  console.log("Job:", created.job.toBase58());
  console.log("Escrow:", escrow.publicKey.toBase58());

  const claimed = await sdk.claimFragment({
    worker: computeWorker.publicKey,
    job: created.job,
    fragmentIndex: 0,
    workerToken: computeWorkerToken,
    signers: [computeWorker],
  });

  await confirm(provider, claimed.signature, "claim fragment 0");

  await confirm(
    provider,
    await sdk.submitFragmentResult({
      worker: computeWorker.publicKey,
      job: created.job,
      fragmentIndex: 0,
      workerToken: computeWorkerToken,
      resultHash: randomHash(10),
      proofRef: randomHash(90),
      signers: [computeWorker],
    }),
    "submit fragment result",
  );

  const vote1 = await sdk.voteFragment({
    verifier: verifier1.publicKey,
    job: created.job,
    fragment: claimed.fragment,
    escrow: escrow.publicKey,
    workerToken: computeWorkerToken,
    choice: true,
    signers: [verifier1],
  });

  await confirm(provider, vote1.signature, "vote fragment valid - verifier 1");

  const vote2 = await sdk.voteFragment({
    verifier: verifier2.publicKey,
    job: created.job,
    fragment: claimed.fragment,
    escrow: escrow.publicKey,
    workerToken: computeWorkerToken,
    choice: true,
    signers: [verifier2],
  });

  await confirm(provider, vote2.signature, "vote fragment valid - verifier 2");

  await confirm(
    provider,
    await sdk.claimVerifierReward({
      verifier: verifier1.publicKey,
      job: created.job,
      fragment: claimed.fragment,
      escrow: escrow.publicKey,
      verifierToken: verifier1Token,
      signers: [verifier1],
    }),
    "claim verifier 1 reward",
  );

  await confirm(
    provider,
    await sdk.claimVerifierReward({
      verifier: verifier2.publicKey,
      job: created.job,
      fragment: claimed.fragment,
      escrow: escrow.publicKey,
      verifierToken: verifier2Token,
      signers: [verifier2],
    }),
    "claim verifier 2 reward",
  );

  const finalized = await sdk.finalizeJob({
    job: created.job,
    escrow: escrow.publicKey,
    clientToken,
    finalHash: randomHash(140),
    outputUri: "ipfs://silicium-local-demo-output",
  });

  await confirm(provider, finalized.signature, "finalize job");

  console.log("Result account:", finalized.result.toBase58());

  await printTokenBalance("Client token balance after job", clientToken, provider);
  await printTokenBalance(
    "Compute worker token balance after reward",
    computeWorkerToken,
    provider,
  );
  await printTokenBalance(
    "Verifier 1 token balance after reward",
    verifier1Token,
    provider,
  );
  await printTokenBalance(
    "Verifier 2 token balance after reward",
    verifier2Token,
    provider,
  );

  console.log("\n--- Network staking flow ---");

  const stakeVault = Keypair.generate();
  const rewardVault = Keypair.generate();

  const poolCreated = await sdk.initStakingPool({
    mint,
    stakeVault,
    rewardVault,
  });

  await confirm(provider, poolCreated.signature, "init staking pool");

  console.log("Staking pool:", poolCreated.pool.toBase58());

  const networkStakeAmount = 1_000_000;

  const networkStake = await sdk.stakeNetwork({
    mint,
    ownerToken: clientToken,
    amount: networkStakeAmount,
  });

  await confirm(provider, networkStake.signature, "stake network");

  await confirm(
    provider,
  await sdk.fundStakingRewards({
    mint,
    funderToken: clientToken,
    amount: 100_000,
  }),
    "fund staking rewards",
  );

  await confirm(
    provider,
    await sdk.claimStakingReward({
      mint,
      ownerRewardToken: clientToken,
    }),
    "claim staking reward",
  );

  const unstakeRequested = await sdk.requestUnstake({
    mint,
    amount: 500_000,
  });

  await confirm(provider, unstakeRequested.signature, "request unstake");

  try {
    await confirm(
      provider,
      await sdk.withdrawUnstaked({
        mint,
        ownerToken: clientToken,
      }),
      "withdraw unstaked",
    );
  } catch (error) {
    console.log("ℹ️ withdrawUnstaked not executed yet. Cooldown is probably still active.");
    console.log("   Re-run withdraw later, or reduce UNSTAKE_COOLDOWN_SECS for local tests.");
  }

  console.log("\n--- Final on-chain reads ---");

  console.log("\nJob:");
  console.dir(await sdk.fetchJob(created.job), { depth: null });

  console.log("\nFragment:");
  console.dir(await sdk.fetchFragment(claimed.fragment), { depth: null });

  console.log("\nCompute worker:");
  console.dir(await sdk.fetchWorker(computeWorker.publicKey), { depth: null });

  console.log("\nVerifier 1:");
  console.dir(await sdk.fetchWorker(verifier1.publicKey), { depth: null });

  console.log("\nVerifier 2:");
  console.dir(await sdk.fetchWorker(verifier2.publicKey), { depth: null });

  console.log("\nStaking pool:");
  console.dir(await sdk.fetchStakingPool(poolCreated.pool), { depth: null });

  console.log("\nNetwork staker:");
  console.dir(await sdk.fetchNetworkStaker(provider.wallet.publicKey, mint), {
    depth: null,
  });

  for (const sub of subscriptions) {
    await sub.remove();
  }

  console.log("\n✅ Full SDK flow completed.");
}

main().catch((error) => {
  console.error("\n❌ Full SDK flow failed:");
  console.error(error);
  process.exit(1);
});
