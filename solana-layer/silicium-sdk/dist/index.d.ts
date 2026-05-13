import * as anchor from "@coral-xyz/anchor";
import { PublicKey, TransactionSignature } from "@solana/web3.js";
import { SiliciumEventClient } from "./events";
import type { CancelJobParams, ClaimFragmentParams, ClaimStakingRewardParams, ClaimVerifierRewardParams, CreateJobParams, CreateSdkParams, FinalizeJobParams, FundStakingRewardsParams, IdlProgram, InitStakingPoolParams, InitTreasuryParams, ProposeFragmentSplitParams, ApproveFragmentSplitParams, CreateSubFragmentParams, ReclaimFragmentParams, RegisterWorkerParams, RequestUnstakeParams, SlashVoteParams, StakeNetworkParams, StakeWorkerParams, SubmitFragmentResultParams, VoteFragmentParams, WithdrawUnstakedParams } from "./types";
export * from "./pdas";
export * from "./events";
export * from "./types";
export declare const SOLANA_LAYER_PROGRAM_ID: anchor.web3.PublicKey;
export declare class SiliciumLayerSdk {
    readonly provider: anchor.AnchorProvider;
    readonly program: IdlProgram;
    readonly programId: PublicKey;
    readonly events: SiliciumEventClient;
    constructor(params: CreateSdkParams);
    static fromWorkspace(provider: anchor.AnchorProvider, program: IdlProgram): SiliciumLayerSdk;
    walletPubkey(): PublicKey;
    private get methods();
    private get accounts();
    pdas: {
        job: (client: PublicKey, jobId: anchor.BN | number | bigint | string) => anchor.web3.PublicKey;
        fragment: (job: PublicKey, fragmentIndex: number) => anchor.web3.PublicKey;
        worker: (worker: PublicKey) => anchor.web3.PublicKey;
        escrowAuth: (job: PublicKey) => anchor.web3.PublicKey;
        stakeAuth: (workerAccount: PublicKey) => anchor.web3.PublicKey;
        stakeVault: (worker: PublicKey) => anchor.web3.PublicKey;
        vote: (fragment: PublicKey, verifier: PublicKey, round: number) => anchor.web3.PublicKey;
        roundResolution: (fragment: PublicKey, round: number) => anchor.web3.PublicKey;
        splitProposal: (parentFragment: PublicKey, round: number) => anchor.web3.PublicKey;
        result: (job: PublicKey) => anchor.web3.PublicKey;
        treasuryState: (mint: PublicKey) => anchor.web3.PublicKey;
        treasuryAuth: (mint: PublicKey) => anchor.web3.PublicKey;
        stakingPool: (mint: PublicKey) => anchor.web3.PublicKey;
        stakingPoolAuth: (mint: PublicKey) => anchor.web3.PublicKey;
        networkStaker: (owner: PublicKey, mint: PublicKey) => anchor.web3.PublicKey;
    };
    registerWorker(params?: RegisterWorkerParams): Promise<TransactionSignature>;
    stakeWorker(params: StakeWorkerParams): Promise<TransactionSignature>;
    createJob(params: CreateJobParams): Promise<{
        signature: TransactionSignature;
        job: PublicKey;
        escrowAuth: PublicKey;
    }>;
    claimFragment(params: ClaimFragmentParams): Promise<{
        signature: TransactionSignature;
        fragment: PublicKey;
    }>;
    reclaimFragment(params: ReclaimFragmentParams): Promise<{
        signature: TransactionSignature;
        fragment: PublicKey;
    }>;
    private resolveParentFragmentAndRound;
    proposeFragmentSplit(params: ProposeFragmentSplitParams): Promise<{
        signature: TransactionSignature;
        parentFragment: PublicKey;
        splitProposal: PublicKey;
    }>;
    approveFragmentSplit(params: ApproveFragmentSplitParams): Promise<{
        signature: TransactionSignature;
        parentFragment: PublicKey;
        splitProposal: PublicKey;
    }>;
    createSubFragment(params: CreateSubFragmentParams): Promise<{
        signature: TransactionSignature;
        parentFragment: PublicKey;
        childFragment: PublicKey;
        splitProposal: PublicKey;
    }>;
    submitFragmentResult(params: SubmitFragmentResultParams): Promise<TransactionSignature>;
    resubmitFragmentResult(params: SubmitFragmentResultParams): Promise<TransactionSignature>;
    private sendSubmitLike;
    voteFragment(params: VoteFragmentParams): Promise<{
        signature: TransactionSignature;
        vote: PublicKey;
        roundResolution: PublicKey;
    }>;
    claimVerifierReward(params: ClaimVerifierRewardParams): Promise<TransactionSignature>;
    finalizeJob(params: FinalizeJobParams): Promise<{
        signature: TransactionSignature;
        result: PublicKey;
    }>;
    cancelJob(params: CancelJobParams): Promise<TransactionSignature>;
    initTreasury(params: InitTreasuryParams): Promise<{
        signature: TransactionSignature;
        treasuryState: PublicKey;
        treasuryAuth: PublicKey;
    }>;
    slashVote(params: SlashVoteParams): Promise<TransactionSignature>;
    initStakingPool(params: InitStakingPoolParams): Promise<{
        signature: TransactionSignature;
        pool: PublicKey;
        poolAuth: PublicKey;
        stakeVault: PublicKey;
        rewardVault: PublicKey;
    }>;
    stakeNetwork(params: StakeNetworkParams): Promise<{
        signature: TransactionSignature;
        pool: PublicKey;
        staker: PublicKey;
    }>;
    fundStakingRewards(params: FundStakingRewardsParams): Promise<TransactionSignature>;
    claimStakingReward(params: ClaimStakingRewardParams): Promise<TransactionSignature>;
    requestUnstake(params: RequestUnstakeParams): Promise<{
        signature: TransactionSignature;
        pool: PublicKey;
        staker: PublicKey;
    }>;
    withdrawUnstaked(params: WithdrawUnstakedParams): Promise<TransactionSignature>;
    fetchJob(job: PublicKey): Promise<unknown>;
    fetchFragment(fragment: PublicKey): Promise<unknown>;
    fetchWorker(workerOrWorkerAccount: PublicKey, isWorkerAccount?: boolean): Promise<unknown>;
    fetchVote(vote: PublicKey): Promise<unknown>;
    fetchRoundResolution(roundResolution: PublicKey): Promise<unknown>;
    fetchResult(result: PublicKey): Promise<unknown>;
    fetchTreasuryState(treasuryState: PublicKey): Promise<unknown>;
    fetchSplitProposal(splitProposal: PublicKey): Promise<unknown>;
    fetchStakingPool(pool: PublicKey): Promise<unknown>;
    fetchNetworkStaker(stakerOrOwner: PublicKey, mint?: PublicKey): Promise<unknown>;
}
