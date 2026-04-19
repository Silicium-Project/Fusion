import * as anchor from "@coral-xyz/anchor";
import type { BN, Program, AnchorProvider, web3 } from "@coral-xyz/anchor";
import type { Commitment, ConfirmOptions, Connection, PublicKey, TransactionSignature } from "@solana/web3.js";
export type SiliciumChain = any;
export type WalletLike = anchor.Wallet;
export type JobStatus = "open" | "cancelled" | "finalized" | "unknown";
export type FragmentStatus = "submitted" | "verified" | "rejected" | "unknown";
export type WorkerStatus = "active" | "banned" | "unknown";
export interface SiliciumSdkOptions {
    provider: AnchorProvider;
    programId: PublicKey;
    program: Program<SiliciumChain>;
    commitment?: Commitment;
}
export interface CreateJobParams {
    client?: PublicKey;
    mint: PublicKey;
    clientToken: PublicKey;
    jobId: number | bigint | BN;
    expectedFragments: number;
    rewardPerFragment: number | bigint | BN;
    deadlineUnix: number | bigint | BN;
    fragmentQuorum: number;
    escrowKeypair?: web3.Keypair;
    confirmOptions?: ConfirmOptions;
}
export interface RegisterWorkerParams {
    worker?: PublicKey;
    confirmOptions?: ConfirmOptions;
}
export interface StakeWorkerParams {
    worker?: PublicKey;
    mint: PublicKey;
    workerToken: PublicKey;
    amount: number | bigint | BN;
    confirmOptions?: ConfirmOptions;
}
export interface SubmitFragmentParams {
    worker?: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
    workerToken: PublicKey;
    resultHash: Uint8Array | number[];
    proofRef: Uint8Array | number[];
    confirmOptions?: ConfirmOptions;
}
export interface ResubmitFragmentParams extends SubmitFragmentParams {
}
export interface VoteFragmentParams {
    verifier?: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
    choice: boolean;
    workerToken?: PublicKey;
    confirmOptions?: ConfirmOptions;
}
export interface FinalizeJobParams {
    client?: PublicKey;
    job: PublicKey;
    finalHash: Uint8Array | number[];
    outputUri: string | Uint8Array | number[];
    clientToken: PublicKey;
    confirmOptions?: ConfirmOptions;
}
export interface CancelJobParams {
    client?: PublicKey;
    job: PublicKey;
    clientToken: PublicKey;
    confirmOptions?: ConfirmOptions;
}
export interface InitTreasuryParams {
    payer?: PublicKey;
    mint: PublicKey;
    treasuryTokenKeypair?: web3.Keypair;
    confirmOptions?: ConfirmOptions;
}
export interface SlashVoteParams {
    slasher?: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
    verifier: PublicKey;
    round: number;
    confirmOptions?: ConfirmOptions;
}
export interface ParsedJobAccount {
    publicKey: PublicKey;
    jobId: bigint;
    client: PublicKey;
    mint: PublicKey;
    escrow: PublicKey;
    expectedFragments: number;
    verifiedFragments: number;
    rewardPerFragment: bigint;
    depositedAmount: bigint;
    paidAmount: bigint;
    deadlineUnix: bigint;
    status: JobStatus;
    fragmentQuorum: number;
    verifiedAtUnix: bigint;
    bump: number;
    escrowAuthBump: number;
    raw: any;
}
export interface ParsedWorkerAccount {
    publicKey: PublicKey;
    owner: PublicKey;
    stakeMint: PublicKey;
    stakeVault: PublicKey;
    stakeAmount: bigint;
    reputation: bigint;
    totalSubmitted: number;
    totalVerified: number;
    totalRejected: number;
    roles: number;
    status: WorkerStatus;
    bump: number;
    raw: any;
}
export interface ParsedFragmentAccount {
    publicKey: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
    worker: PublicKey;
    workerTokenAccount: PublicKey;
    resultHash: number[];
    proofRef: number[];
    status: FragmentStatus;
    yesVotes: number;
    noVotes: number;
    requiredQuorum: number;
    votingDeadlineUnix: bigint;
    round: number;
    bump: number;
    raw: any;
}
export interface ParsedFragmentVoteAccount {
    publicKey: PublicKey;
    fragment: PublicKey;
    verifier: PublicKey;
    choice: boolean;
    round: number;
    slashed: boolean;
    bump: number;
    raw: any;
}
export interface ParsedJobResultAccount {
    publicKey: PublicKey;
    job: PublicKey;
    finalHash: number[];
    uriLen: number;
    uriBytes: number[];
    outputUri: string;
    bump: number;
    raw: any;
}
export interface ParsedTreasuryAccount {
    publicKey: PublicKey;
    mint: PublicKey;
    authority: PublicKey;
    admin: PublicKey;
    treasuryTokenAccount: PublicKey;
    bump: number;
    raw: any;
}
export interface JobAggregate {
    job: ParsedJobAccount | null;
    fragments: ParsedFragmentAccount[];
    result: ParsedJobResultAccount | null;
}
export interface ProgramAccountRow<T> {
    publicKey: PublicKey;
    account: T;
}
export interface BuildSiliciumSdkParams {
    connection: Connection;
    wallet: WalletLike;
    idl: any;
    programId: PublicKey;
    opts?: ConfirmOptions;
}
export type { TransactionSignature };
