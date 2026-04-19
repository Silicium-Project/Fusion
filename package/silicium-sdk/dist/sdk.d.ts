import { AnchorProvider, Program } from "@coral-xyz/anchor";
import { PublicKey, type Commitment, type Connection, type TransactionSignature } from "@solana/web3.js";
import type { BuildSiliciumSdkParams, CancelJobParams, CreateJobParams, FinalizeJobParams, InitTreasuryParams, JobAggregate, ParsedFragmentAccount, ParsedFragmentVoteAccount, ParsedJobAccount, ParsedJobResultAccount, ParsedTreasuryAccount, ParsedWorkerAccount, RegisterWorkerParams, ResubmitFragmentParams, SiliciumChain, SiliciumSdkOptions, SlashVoteParams, StakeWorkerParams, SubmitFragmentParams, VoteFragmentParams } from "./types";
import { bnToLeBuffer } from "./utils";
type AnyProgram = Program<any>;
export declare class SiliciumSdk {
    readonly provider: AnchorProvider;
    readonly program: AnyProgram;
    readonly connection: Connection;
    readonly programId: PublicKey;
    readonly commitment: Commitment;
    constructor(options: SiliciumSdkOptions);
    static fromProgram(program: Program<SiliciumChain>, provider?: AnchorProvider): SiliciumSdk;
    get walletPublicKey(): PublicKey;
    private get accountApi();
    private get methodsApi();
    findJobPda(client: PublicKey, jobId: Parameters<typeof bnToLeBuffer>[0]): [PublicKey, number];
    findEscrowAuthPda(job: PublicKey): [PublicKey, number];
    findResultPda(job: PublicKey): [PublicKey, number];
    findWorkerPda(workerWallet: PublicKey): [PublicKey, number];
    findFragmentPda(job: PublicKey, fragmentIndex: number): [PublicKey, number];
    findFragmentVotePda(fragment: PublicKey, verifier: PublicKey, round: number): [PublicKey, number];
    findStakeAuthPda(workerAccount: PublicKey): [PublicKey, number];
    findStakeVaultPda(workerWallet: PublicKey): [PublicKey, number];
    findTreasuryStatePda(mint: PublicKey): [PublicKey, number];
    findTreasuryAuthPda(mint: PublicKey): [PublicKey, number];
    createJob(params: CreateJobParams): Promise<{
        signature: TransactionSignature;
        job: PublicKey;
        escrowAuth: PublicKey;
        escrow: PublicKey;
    }>;
    registerWorker(params?: RegisterWorkerParams): Promise<{
        signature: TransactionSignature;
        workerAccount: PublicKey;
    }>;
    stakeWorker(params: StakeWorkerParams): Promise<{
        signature: TransactionSignature;
        workerAccount: PublicKey;
        stakeAuth: PublicKey;
        stakeVault: PublicKey;
    }>;
    submitFragment(params: SubmitFragmentParams): Promise<{
        signature: TransactionSignature;
        workerAccount: PublicKey;
        fragment: PublicKey;
    }>;
    resubmitFragment(params: ResubmitFragmentParams): Promise<{
        signature: TransactionSignature;
        workerAccount: PublicKey;
        fragment: PublicKey;
    }>;
    voteFragment(params: VoteFragmentParams): Promise<{
        signature: TransactionSignature;
        verifierWorker: PublicKey;
        fragment: PublicKey;
        vote: PublicKey;
    }>;
    finalizeJob(params: FinalizeJobParams): Promise<{
        signature: TransactionSignature;
        result: PublicKey;
        escrowAuth: PublicKey;
    }>;
    cancelJob(params: CancelJobParams): Promise<{
        signature: TransactionSignature;
        escrowAuth: PublicKey;
    }>;
    initTreasury(params: InitTreasuryParams): Promise<{
        signature: TransactionSignature;
        treasuryState: PublicKey;
        treasuryAuth: PublicKey;
        treasury: PublicKey;
    }>;
    slashVote(params: SlashVoteParams): Promise<{
        signature: TransactionSignature;
        fragment: PublicKey;
        vote: PublicKey;
        verifierWorker: PublicKey;
        stakeAuth: PublicKey;
        stakeVault: PublicKey;
        treasuryState: PublicKey;
        treasuryAuth: PublicKey;
        treasury: PublicKey;
    }>;
    fetchJob(job: PublicKey): Promise<ParsedJobAccount | null>;
    fetchJobById(client: PublicKey, jobId: Parameters<typeof bnToLeBuffer>[0]): Promise<ParsedJobAccount | null>;
    fetchWorkerByPda(workerAccount: PublicKey): Promise<ParsedWorkerAccount | null>;
    fetchWorker(workerWallet: PublicKey): Promise<ParsedWorkerAccount | null>;
    fetchFragment(job: PublicKey, fragmentIndex: number): Promise<ParsedFragmentAccount | null>;
    fetchFragmentVote(fragment: PublicKey, verifier: PublicKey, round: number): Promise<ParsedFragmentVoteAccount | null>;
    fetchJobResult(job: PublicKey): Promise<ParsedJobResultAccount | null>;
    fetchTreasuryState(mint: PublicKey): Promise<ParsedTreasuryAccount | null>;
    listAllJobs(): Promise<ParsedJobAccount[]>;
    listJobsByClient(client: PublicKey): Promise<ParsedJobAccount[]>;
    listFragmentsByJob(job: PublicKey): Promise<ParsedFragmentAccount[]>;
    listFragmentVotesByFragment(fragment: PublicKey): Promise<ParsedFragmentVoteAccount[]>;
    fetchJobAggregate(client: PublicKey, jobId: Parameters<typeof bnToLeBuffer>[0]): Promise<JobAggregate>;
}
export declare function buildSiliciumSdk(params: BuildSiliciumSdkParams): Promise<SiliciumSdk>;
export {};
