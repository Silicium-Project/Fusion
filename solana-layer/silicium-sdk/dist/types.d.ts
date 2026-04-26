import * as anchor from "@coral-xyz/anchor";
import { PublicKey, Signer } from "@solana/web3.js";
export type IdlProgram = anchor.Program<any>;
export type Amount = anchor.BN | number | bigint | string;
export type Hash32 = number[] | Uint8Array;
export interface CreateSdkParams {
    provider: anchor.AnchorProvider;
    program: IdlProgram;
}
export interface CreateJobParams {
    client?: PublicKey;
    mint: PublicKey;
    clientToken: PublicKey;
    escrow: Signer;
    jobId: Amount;
    expectedFragments: number;
    rewardPerFragment: Amount;
    verifierRewardPerVote: Amount;
    verifierRewardBudget: Amount;
    deadlineUnix: Amount;
    fragmentQuorum: number;
}
export interface RegisterWorkerParams {
    worker?: PublicKey;
    signers?: Signer[];
}
export interface StakeWorkerParams {
    worker?: PublicKey;
    workerToken: PublicKey;
    mint: PublicKey;
    amount: Amount;
    signers?: Signer[];
}
export interface ClaimFragmentParams {
    worker?: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
    workerToken: PublicKey;
    signers?: Signer[];
}
export interface SubmitFragmentResultParams {
    worker?: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
    workerToken: PublicKey;
    resultHash: Hash32;
    proofRef: Hash32;
    signers?: Signer[];
}
export interface VoteFragmentParams {
    verifier?: PublicKey;
    job: PublicKey;
    fragment: PublicKey;
    escrow: PublicKey;
    workerToken: PublicKey;
    choice: boolean;
    round?: number;
    signers?: Signer[];
}
export interface ClaimVerifierRewardParams {
    verifier?: PublicKey;
    job: PublicKey;
    fragment: PublicKey;
    escrow: PublicKey;
    verifierToken: PublicKey;
    round?: number;
    signers?: Signer[];
}
export interface FinalizeJobParams {
    client?: PublicKey;
    job: PublicKey;
    escrow: PublicKey;
    clientToken: PublicKey;
    finalHash: Hash32;
    outputUri: string | Uint8Array | Buffer;
}
export interface CancelJobParams {
    client?: PublicKey;
    job: PublicKey;
    escrow: PublicKey;
    clientToken: PublicKey;
}
export interface InitTreasuryParams {
    payer?: PublicKey;
    mint: PublicKey;
    treasury: Signer;
}
export interface SlashVoteParams {
    slasher?: PublicKey;
    job: PublicKey;
    fragment: PublicKey;
    vote: PublicKey;
    verifier: PublicKey;
    mint: PublicKey;
    treasury: PublicKey;
}
export interface ReclaimFragmentParams {
    caller?: PublicKey;
    job: PublicKey;
    fragmentIndex: number;
}
export type SdkEventName = "jobCreated" | "workerRegistered" | "workerStaked" | "treasuryInitialized" | "fragmentClaimed" | "fragmentReclaimed" | "fragmentSubmitted" | "fragmentVerified" | "fragmentRejected" | "verifierRewardClaimed" | "jobFinalized" | "jobCancelled" | "voteSlashed";
