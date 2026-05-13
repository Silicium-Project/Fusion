import * as anchor from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { SdkEventName } from "./types";
export type EventCallback<T = unknown> = (event: T, slot: number, signature: string) => void;
export interface EventSubscription {
    eventName: SdkEventName;
    listenerId: number;
    remove(): Promise<void>;
}
export interface FragmentSplitProposedEvent {
    job: PublicKey;
    parentFragment: PublicKey;
    parentFragmentIndex: number;
    proposal: PublicKey;
    splitterWorker: PublicKey;
    manifestHash: number[];
    childCount: number;
    depth: number;
    complexityScore: number;
}
export interface FragmentSplitApprovedEvent {
    job: PublicKey;
    parentFragment: PublicKey;
    parentFragmentIndex: number;
    proposal: PublicKey;
    authority: PublicKey;
    childCount: number;
    newExpectedFragments: number;
    totalFragmentsCreated: number;
}
export interface FragmentSplitRejectedEvent {
    job: PublicKey;
    parentFragment: PublicKey;
    parentFragmentIndex: number;
    proposal: PublicKey;
    authority: PublicKey;
}
export interface SubFragmentCreatedEvent {
    job: PublicKey;
    parentFragment: PublicKey;
    childFragment: PublicKey;
    childFragmentIndex: number;
    depth: number;
    requiredReputation: anchor.BN;
    requiredStake: anchor.BN;
    complexityScore: number;
    inputHash: number[];
    createdChildren: number;
    childCount: number;
}
export interface FragmentSplitCompletedEvent {
    job: PublicKey;
    parentFragment: PublicKey;
    parentFragmentIndex: number;
    proposal: PublicKey;
    childCount: number;
}
export interface BayesianReputationUpdatedEvent {
    worker: PublicKey;
    reason: number;
    reputation: anchor.BN;
    reliabilityScore: number;
    computeAlphaLong: anchor.BN;
    computeBetaLong: anchor.BN;
    computeAlphaShort: anchor.BN;
    computeBetaShort: anchor.BN;
    verifyAlphaLong: anchor.BN;
    verifyBetaLong: anchor.BN;
    verifyAlphaShort: anchor.BN;
    verifyBetaShort: anchor.BN;
    fraudStrikes: number;
    errorStrikes: number;
}
export interface SiliciumEventMap {
    jobCreated: unknown;
    workerRegistered: unknown;
    workerStaked: unknown;
    treasuryInitialized: unknown;
    fragmentClaimed: unknown;
    fragmentReclaimed: unknown;
    fragmentSubmitted: unknown;
    fragmentVerified: unknown;
    fragmentRejected: unknown;
    verifierRewardClaimed: unknown;
    jobFinalized: unknown;
    jobCancelled: unknown;
    voteSlashed: unknown;
    workerReputationUpdated: unknown;
    bayesianReputationUpdated: BayesianReputationUpdatedEvent;
    fragmentSplitProposed: FragmentSplitProposedEvent;
    fragmentSplitApproved: FragmentSplitApprovedEvent;
    fragmentSplitRejected: FragmentSplitRejectedEvent;
    subFragmentCreated: SubFragmentCreatedEvent;
    fragmentSplitCompleted: FragmentSplitCompletedEvent;
    stakingPoolInitialized: unknown;
    networkStakeDeposited: unknown;
    stakingRewardsFunded: unknown;
    stakingRewardClaimed: unknown;
    networkUnstakeRequested: unknown;
    networkUnstakeWithdrawn: unknown;
}
export declare class SiliciumEventClient {
    private readonly program;
    constructor(program: anchor.Program<any>);
    on<K extends SdkEventName>(eventName: K, callback: EventCallback<K extends keyof SiliciumEventMap ? SiliciumEventMap[K] : unknown>): EventSubscription;
    onAll(callback: (name: SdkEventName, event: unknown, slot: number, signature: string) => void): EventSubscription[];
    remove(subscription: EventSubscription): Promise<void>;
}
export declare function pubkey(value: PublicKey | string): PublicKey;
