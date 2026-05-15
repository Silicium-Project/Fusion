import * as anchor from "@coral-xyz/anchor";
import {
  Connection,
  PublicKey,
  SystemProgram,
  SYSVAR_RENT_PUBKEY,
  TransactionSignature,
} from "@solana/web3.js";
import { TOKEN_PROGRAM_ID } from "@solana/spl-token";

import { SiliciumEventClient } from "./events";
import {
  escrowAuthPda,
  fragmentPda,
  jobPda,
  networkStakerPda,
  resultPda,
  roundResolutionPda,
  splitProposalPda,
  stakeAuthPda,
  stakeVaultPda,
  stakingPoolAuthPda,
  stakingPoolPda,
  toBn,
  treasuryAuthPda,
  treasuryStatePda,
  votePda,
  workerPda,
} from "./pdas";
import type {
  CancelJobParams,
  ClaimFragmentParams,
  ClaimStakingRewardParams,
  ClaimVerifierRewardParams,
  CreateJobParams,
  CreateSdkParams,
  FinalizeJobParams,
  FundStakingRewardsParams,
  Hash32,
  IdlProgram,
  InitStakingPoolParams,
  InitTreasuryParams,
  ProposeFragmentSplitParams,
  ApproveFragmentSplitParams,
  CreateSubFragmentParams,
  ReclaimFragmentParams,
  RegisterWorkerParams,
  RequestUnstakeParams,
  SlashVoteParams,
  StakeNetworkParams,
  StakeWorkerParams,
  SubmitFragmentResultParams,
  VoteFragmentParams,
  WithdrawUnstakedParams,
} from "./types";

export * from "./pdas";
export * from "./events";
export * from "./types";

// Must match declare_id! in programs/solana-layer/src/lib.rs
export type SolanaLayerCluster = "devnet" | "localnet";

export const SOLANA_LAYER_DEVNET_PROGRAM_ID = new PublicKey("4FPGViycNEGCtwnNs3NN2pPQu9ziTch8o9zkVc2VnKVP");
export const SOLANA_LAYER_LOCALNET_PROGRAM_ID = new PublicKey("4FPGViycNEGCtwnNs3NN2pPQu9ziTch8o9zkVc2VnKVP");
export const SOLANA_LAYER_PROGRAM_ID = SOLANA_LAYER_DEVNET_PROGRAM_ID;

export const SOLANA_LAYER_DEVNET_RPC_URL = "https://api.devnet.solana.com";
export const SOLANA_LAYER_LOCALNET_RPC_URL = "http://127.0.0.1:8899";

export function getSolanaLayerProgramId(cluster: SolanaLayerCluster = "devnet"): PublicKey {
  return cluster === "localnet" ? SOLANA_LAYER_LOCALNET_PROGRAM_ID : SOLANA_LAYER_DEVNET_PROGRAM_ID;
}

export function getSolanaLayerRpcUrl(cluster: SolanaLayerCluster = "devnet"): string {
  return cluster === "localnet" ? SOLANA_LAYER_LOCALNET_RPC_URL : SOLANA_LAYER_DEVNET_RPC_URL;
}

export function createSolanaLayerConnection(cluster: SolanaLayerCluster = "devnet", commitment: anchor.web3.Commitment = "confirmed"): Connection {
  return new Connection(getSolanaLayerRpcUrl(cluster), commitment);
}

function asHash32(value: Hash32): number[] {
  const arr = Array.from(value);
  if (arr.length !== 32) {
    throw new Error(`Expected a 32-byte array, got ${arr.length} bytes`);
  }
  return arr;
}

function asBytes(value: string | Uint8Array | Buffer): Buffer {
  return typeof value === "string" ? Buffer.from(value) : Buffer.from(value);
}

function appendSigners<T extends { signers(signers: any[]): T }>(builder: T, signers?: any[]): T {
  return signers?.length ? builder.signers(signers) : builder;
}

export class SiliciumLayerSdk {
  readonly provider: anchor.AnchorProvider;
  readonly program: IdlProgram;
  readonly programId: PublicKey;
  readonly events: SiliciumEventClient;

  constructor(params: CreateSdkParams) {
    this.provider = params.provider;
    this.program = params.program;
    this.programId = params.program.programId;
    this.events = new SiliciumEventClient(params.program);
  }

  static fromWorkspace(provider: anchor.AnchorProvider, program: IdlProgram): SiliciumLayerSdk {
    return new SiliciumLayerSdk({ provider, program });
  }

  walletPubkey(): PublicKey {
    return this.provider.wallet.publicKey;
  }

  private get methods(): any {
    return this.program.methods as any;
  }

  private get accounts(): any {
    return this.program.account as any;
  }

  pdas = {
    job: (client: PublicKey, jobId: anchor.BN | number | bigint | string) => jobPda(this.programId, client, jobId),
    fragment: (job: PublicKey, fragmentIndex: number) => fragmentPda(this.programId, job, fragmentIndex),
    worker: (worker: PublicKey) => workerPda(this.programId, worker),
    escrowAuth: (job: PublicKey) => escrowAuthPda(this.programId, job),
    stakeAuth: (workerAccount: PublicKey) => stakeAuthPda(this.programId, workerAccount),
    stakeVault: (worker: PublicKey) => stakeVaultPda(this.programId, worker),
    vote: (fragment: PublicKey, verifier: PublicKey, round: number) => votePda(this.programId, fragment, verifier, round),
    roundResolution: (fragment: PublicKey, round: number) => roundResolutionPda(this.programId, fragment, round),
    splitProposal: (parentFragment: PublicKey, round: number) => splitProposalPda(this.programId, parentFragment, round),
    result: (job: PublicKey) => resultPda(this.programId, job),
    treasuryState: (mint: PublicKey) => treasuryStatePda(this.programId, mint),
    treasuryAuth: (mint: PublicKey) => treasuryAuthPda(this.programId, mint),
    stakingPool: (mint: PublicKey) => stakingPoolPda(this.programId, mint),
    stakingPoolAuth: (mint: PublicKey) => stakingPoolAuthPda(this.programId, mint),
    networkStaker: (owner: PublicKey, mint: PublicKey) => networkStakerPda(this.programId, owner, mint),
  };

  async registerWorker(params: RegisterWorkerParams = {}): Promise<TransactionSignature> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);

    let builder = this.methods
      .registerWorker()
      .accounts({
        worker,
        workerAccount,
        systemProgram: SystemProgram.programId,
      });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async stakeWorker(params: StakeWorkerParams): Promise<TransactionSignature> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);
    const stakeAuth = this.pdas.stakeAuth(workerAccount);
    const stakeVault = this.pdas.stakeVault(worker);

    let builder = this.methods
      .stakeWorker(toBn(params.amount))
      .accounts({
        worker,
        workerAccount,
        mint: params.mint,
        workerToken: params.workerToken,
        stakeAuth,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async createJob(params: CreateJobParams): Promise<{ signature: TransactionSignature; job: PublicKey; escrowAuth: PublicKey }> {
    const client = params.client ?? this.walletPubkey();
    const job = this.pdas.job(client, params.jobId);
    const escrowAuth = this.pdas.escrowAuth(job);

    const builder = this.methods
      .createJob(
        toBn(params.jobId),
        params.expectedFragments,
        toBn(params.rewardPerFragment),
        toBn(params.verifierRewardPerVote),
        toBn(params.verifierRewardBudget),
        toBn(params.deadlineUnix),
        params.fragmentQuorum,
      )
      .accounts({
        client,
        mint: params.mint,
        job,
        escrowAuth,
        escrow: params.escrow.publicKey,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([params.escrow]);

    const signature = await builder.rpc();
    return { signature, job, escrowAuth };
  }

  async claimFragment(params: ClaimFragmentParams): Promise<{ signature: TransactionSignature; fragment: PublicKey }> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);
    const fragment = this.pdas.fragment(params.job, params.fragmentIndex);

    let builder = this.methods
      .claimFragment(params.fragmentIndex)
      .accounts({
        worker,
        workerAccount,
        job: params.job,
        fragment,
        workerToken: params.workerToken,
        systemProgram: SystemProgram.programId,
      });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, fragment };
  }

  async reclaimFragment(params: ReclaimFragmentParams): Promise<{ signature: TransactionSignature; fragment: PublicKey }> {
    const caller = params.caller ?? this.walletPubkey();
    const fragment = this.pdas.fragment(params.job, params.fragmentIndex);

    let builder = this.methods
      .reclaimFragment(params.fragmentIndex)
      .accounts({ caller, job: params.job, fragment });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, fragment };
  }

  private async resolveParentFragmentAndRound(params: {
    job: PublicKey;
    parentFragment?: PublicKey;
    parentFragmentIndex: number;
    round?: number;
  }): Promise<{ parentFragment: PublicKey; round: number }> {
    const parentFragment = params.parentFragment ?? this.pdas.fragment(params.job, params.parentFragmentIndex);

    if (params.round !== undefined) {
      return { parentFragment, round: params.round };
    }

    const parentAccount = await this.accounts.fragment.fetch(parentFragment);
    return { parentFragment, round: Number(parentAccount.round) };
  }

  async proposeFragmentSplit(params: ProposeFragmentSplitParams): Promise<{ signature: TransactionSignature; parentFragment: PublicKey; splitProposal: PublicKey }> {
    const splitter = params.splitter ?? this.walletPubkey();
    const splitterWorker = this.pdas.worker(splitter);
    const { parentFragment, round } = await this.resolveParentFragmentAndRound(params);
    const splitProposal = this.pdas.splitProposal(parentFragment, round);

    let builder = this.methods
      .proposeFragmentSplit(asHash32(params.manifestHash), params.childCount)
      .accounts({
        splitter,
        splitterWorker,
        job: params.job,
        parentFragment,
        splitProposal,
        systemProgram: SystemProgram.programId,
      });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, parentFragment, splitProposal };
  }

  async approveFragmentSplit(params: ApproveFragmentSplitParams): Promise<{ signature: TransactionSignature; parentFragment: PublicKey; splitProposal: PublicKey }> {
    const authority = params.authority ?? this.walletPubkey();
    const { parentFragment, round } = await this.resolveParentFragmentAndRound(params);
    const splitProposal = params.splitProposal ?? this.pdas.splitProposal(parentFragment, round);

    let builder = this.methods
      .approveFragmentSplit(params.approve)
      .accounts({
        authority,
        job: params.job,
        parentFragment,
        splitProposal,
      });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, parentFragment, splitProposal };
  }

  async createSubFragment(params: CreateSubFragmentParams): Promise<{ signature: TransactionSignature; parentFragment: PublicKey; childFragment: PublicKey; splitProposal: PublicKey }> {
    const payer = params.payer ?? this.walletPubkey();
    const { parentFragment, round } = await this.resolveParentFragmentAndRound(params);
    const splitProposal = params.splitProposal ?? this.pdas.splitProposal(parentFragment, round);
    const childFragment = this.pdas.fragment(params.job, params.childFragmentIndex);

    let builder = this.methods
      .createSubFragment(
        params.childFragmentIndex,
        toBn(params.requiredComputeReputation),
        toBn(params.requiredStake),
        params.complexityScore,
        asHash32(params.inputHash),
      )
      .accounts({
        payer,
        job: params.job,
        parentFragment,
        splitProposal,
        childFragment,
        systemProgram: SystemProgram.programId,
      });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, parentFragment, childFragment, splitProposal };
  }

  async submitFragmentResult(params: SubmitFragmentResultParams): Promise<TransactionSignature> {
    return this.sendSubmitLike("submitFragmentResult", params);
  }

  async resubmitFragmentResult(params: SubmitFragmentResultParams): Promise<TransactionSignature> {
    return this.sendSubmitLike("resubmitFragmentResult", params);
  }

  private async sendSubmitLike(method: "submitFragmentResult" | "resubmitFragmentResult", params: SubmitFragmentResultParams): Promise<TransactionSignature> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);
    const fragment = this.pdas.fragment(params.job, params.fragmentIndex);

    let builder = this.methods[method](
      params.fragmentIndex,
      asHash32(params.resultHash),
      asHash32(params.proofRef),
    ).accounts({
      worker,
      workerAccount,
      job: params.job,
      fragment,
      workerToken: params.workerToken,
    });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async voteFragment(params: VoteFragmentParams): Promise<{ signature: TransactionSignature; vote: PublicKey; roundResolution: PublicKey }> {
    const verifier = params.verifier ?? this.walletPubkey();
    const verifierWorker = this.pdas.worker(verifier);
    const fragmentAccount = await this.accounts.fragment.fetch(params.fragment);
    const round = params.round ?? Number(fragmentAccount.round);
    const computeWorkerOwner: PublicKey = params.computeWorker ?? fragmentAccount.worker;
    const computeWorker = this.pdas.worker(computeWorkerOwner);
    const vote = this.pdas.vote(params.fragment, verifier, round);
    const roundResolution = this.pdas.roundResolution(params.fragment, round);
    const escrowAuth = this.pdas.escrowAuth(params.job);

    let builder = this.methods
      .voteFragment(params.choice)
      .accounts({
        verifier,
        job: params.job,
        fragment: params.fragment,
        verifierWorker,
        computeWorker,
        vote,
        roundResolution,
        escrowAuth,
        escrow: params.escrow,
        workerToken: params.workerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, vote, roundResolution };
  }

  async claimVerifierReward(params: ClaimVerifierRewardParams): Promise<TransactionSignature> {
    const verifier = params.verifier ?? this.walletPubkey();
    const verifierWorker = this.pdas.worker(verifier);
    const fragmentAccount = params.round === undefined
      ? await this.accounts.fragment.fetch(params.fragment)
      : undefined;
    const round = params.round ?? Number(fragmentAccount.round);
    const vote = this.pdas.vote(params.fragment, verifier, round);
    const roundResolution = this.pdas.roundResolution(params.fragment, round);
    const escrowAuth = this.pdas.escrowAuth(params.job);

    let builder = this.methods
      .claimVerifierReward()
      .accounts({
        verifier,
        job: params.job,
        fragment: params.fragment,
        roundResolution,
        vote,
        verifierWorker,
        escrowAuth,
        escrow: params.escrow,
        verifierToken: params.verifierToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async finalizeJob(params: FinalizeJobParams): Promise<{ signature: TransactionSignature; result: PublicKey }> {
    const client = params.client ?? this.walletPubkey();
    const result = this.pdas.result(params.job);
    const escrowAuth = this.pdas.escrowAuth(params.job);

    const signature = await this.methods
      .finalizeJob(asHash32(params.finalHash), asBytes(params.outputUri))
      .accounts({
        client,
        job: params.job,
        result,
        escrowAuth,
        escrow: params.escrow,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    return { signature, result };
  }

  async cancelJob(params: CancelJobParams): Promise<TransactionSignature> {
    const client = params.client ?? this.walletPubkey();
    const escrowAuth = this.pdas.escrowAuth(params.job);

    return this.methods
      .cancelJob()
      .accounts({
        client,
        job: params.job,
        escrowAuth,
        escrow: params.escrow,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();
  }

  async initTreasury(params: InitTreasuryParams): Promise<{ signature: TransactionSignature; treasuryState: PublicKey; treasuryAuth: PublicKey }> {
    const payer = params.payer ?? this.walletPubkey();
    const treasuryState = this.pdas.treasuryState(params.mint);
    const treasuryAuth = this.pdas.treasuryAuth(params.mint);

    const signature = await this.methods
      .initTreasury()
      .accounts({
        payer,
        mint: params.mint,
        treasuryState,
        treasuryAuth,
        treasury: params.treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([params.treasury])
      .rpc();

    return { signature, treasuryState, treasuryAuth };
  }

  async slashVote(params: SlashVoteParams): Promise<TransactionSignature> {
    const slasher = params.slasher ?? this.walletPubkey();
    const verifierWorker = this.pdas.worker(params.verifier);
    const stakeAuth = this.pdas.stakeAuth(verifierWorker);
    const stakeVault = this.pdas.stakeVault(params.verifier);
    const treasuryState = this.pdas.treasuryState(params.mint);
    const treasuryAuth = this.pdas.treasuryAuth(params.mint);

    return this.methods
      .slashVote()
      .accounts({
        slasher,
        job: params.job,
        fragment: params.fragment,
        vote: params.vote,
        verifierWorker,
        treasuryState,
        stakeAuth,
        stakeVault,
        treasuryAuth,
        treasury: params.treasury,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();
  }

  async initStakingPool(params: InitStakingPoolParams): Promise<{
    signature: TransactionSignature;
    pool: PublicKey;
    poolAuth: PublicKey;
    stakeVault: PublicKey;
    rewardVault: PublicKey;
  }> {
    const payer = params.payer ?? this.walletPubkey();
    const pool = this.pdas.stakingPool(params.mint);
    const poolAuth = this.pdas.stakingPoolAuth(params.mint);

    const signature = await this.methods
      .initStakingPool()
      .accounts({
        payer,
        mint: params.mint,
        pool,
        poolAuth,
        stakeVault: params.stakeVault.publicKey,
        rewardVault: params.rewardVault.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([params.stakeVault, params.rewardVault])
      .rpc();

    return {
      signature,
      pool,
      poolAuth,
      stakeVault: params.stakeVault.publicKey,
      rewardVault: params.rewardVault.publicKey,
    };
  }

  async stakeNetwork(params: StakeNetworkParams): Promise<{ signature: TransactionSignature; pool: PublicKey; staker: PublicKey }> {
    const owner = params.owner ?? this.walletPubkey();
    const pool = this.pdas.stakingPool(params.mint);
    const staker = this.pdas.networkStaker(owner, params.mint);
    const stakeVault = params.stakeVault ?? (await this.fetchStakingPool(pool) as any).stakeVault;

    let builder = this.methods
      .stakeNetwork(toBn(params.amount))
      .accounts({
        owner,
        mint: params.mint,
        pool,
        staker,
        ownerToken: params.ownerToken,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, pool, staker };
  }

  async fundStakingRewards(params: FundStakingRewardsParams): Promise<TransactionSignature> {
    const funder = params.funder ?? this.walletPubkey();
    const pool = this.pdas.stakingPool(params.mint);
    const rewardVault = params.rewardVault ?? (await this.fetchStakingPool(pool) as any).rewardVault;

    let builder = this.methods
      .fundStakingRewards(toBn(params.amount))
      .accounts({
        funder,
        mint: params.mint,
        pool,
        funderToken: params.funderToken,
        rewardVault,
        tokenProgram: TOKEN_PROGRAM_ID,
      });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async claimStakingReward(params: ClaimStakingRewardParams): Promise<TransactionSignature> {
    const owner = params.owner ?? this.walletPubkey();
    const pool = this.pdas.stakingPool(params.mint);
    const poolAuth = this.pdas.stakingPoolAuth(params.mint);
    const staker = this.pdas.networkStaker(owner, params.mint);
    const rewardVault = params.rewardVault ?? (await this.fetchStakingPool(pool) as any).rewardVault;

    let builder = this.methods
      .claimStakingReward()
      .accounts({
        owner,
        mint: params.mint,
        pool,
        poolAuth,
        staker,
        rewardVault,
        ownerRewardToken: params.ownerRewardToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async requestUnstake(params: RequestUnstakeParams): Promise<{ signature: TransactionSignature; pool: PublicKey; staker: PublicKey }> {
    const owner = params.owner ?? this.walletPubkey();
    const pool = this.pdas.stakingPool(params.mint);
    const staker = this.pdas.networkStaker(owner, params.mint);

    let builder = this.methods
      .requestUnstake(toBn(params.amount))
      .accounts({ owner, mint: params.mint, pool, staker });

    builder = appendSigners(builder, params.signers);
    const signature = await builder.rpc();
    return { signature, pool, staker };
  }

  async withdrawUnstaked(params: WithdrawUnstakedParams): Promise<TransactionSignature> {
    const owner = params.owner ?? this.walletPubkey();
    const pool = this.pdas.stakingPool(params.mint);
    const poolAuth = this.pdas.stakingPoolAuth(params.mint);
    const staker = this.pdas.networkStaker(owner, params.mint);
    const stakeVault = params.stakeVault ?? (await this.fetchStakingPool(pool) as any).stakeVault;

    let builder = this.methods
      .withdrawUnstaked()
      .accounts({
        owner,
        mint: params.mint,
        pool,
        poolAuth,
        staker,
        stakeVault,
        ownerToken: params.ownerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      });

    builder = appendSigners(builder, params.signers);
    return builder.rpc();
  }

  async fetchJob(job: PublicKey): Promise<unknown> {
    return this.accounts.job.fetch(job);
  }

  async fetchFragment(fragment: PublicKey): Promise<unknown> {
    return this.accounts.fragment.fetch(fragment);
  }

  async fetchWorker(workerOrWorkerAccount: PublicKey, isWorkerAccount = false): Promise<unknown> {
    const account = isWorkerAccount ? workerOrWorkerAccount : this.pdas.worker(workerOrWorkerAccount);
    return this.accounts.worker.fetch(account);
  }

  async fetchWorkerReputation(workerOrWorkerAccount: PublicKey, isWorkerAccount = false): Promise<{
    computeReputation: anchor.BN;
    verifyReputation: anchor.BN;
    globalReputation: anchor.BN;
    reliabilityScore?: number;
  }> {
    const worker = await this.fetchWorker(workerOrWorkerAccount, isWorkerAccount) as any;
    return {
      computeReputation: worker.computeReputation,
      verifyReputation: worker.verifyReputation,
      globalReputation: worker.globalReputation,
      reliabilityScore: worker.reliabilityScore,
    };
  }

  async fetchAllWorkers(): Promise<unknown[]> {
    return this.accounts.worker.all();
  }

  async fetchFragmentsForJob(job: PublicKey): Promise<unknown[]> {
    return this.accounts.fragment.all([
      { memcmp: { offset: 8, bytes: job.toBase58() } },
    ]);
  }

  async fetchVote(vote: PublicKey): Promise<unknown> {
    return this.accounts.fragmentVote.fetch(vote);
  }

  async fetchRoundResolution(roundResolution: PublicKey): Promise<unknown> {
    return this.accounts.fragmentResolution.fetch(roundResolution);
  }

  async fetchResult(result: PublicKey): Promise<unknown> {
    return this.accounts.jobResult.fetch(result);
  }

  async fetchTreasuryState(treasuryState: PublicKey): Promise<unknown> {
    return this.accounts.treasury.fetch(treasuryState);
  }

  async fetchSplitProposal(splitProposal: PublicKey): Promise<unknown> {
    return this.accounts.splitProposal.fetch(splitProposal);
  }

  async fetchStakingPool(pool: PublicKey): Promise<unknown> {
    return this.accounts.stakingPool.fetch(pool);
  }

  async fetchNetworkStaker(stakerOrOwner: PublicKey, mint?: PublicKey): Promise<unknown> {
    const staker = mint ? this.pdas.networkStaker(stakerOrOwner, mint) : stakerOrOwner;
    return this.accounts.networkStaker.fetch(staker);
  }
}
