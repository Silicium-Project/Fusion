import * as anchor from '@coral-xyz/anchor';
import { PublicKey } from '@solana/web3.js';
import { SDK_EVENT_NAMES, SdkEventName } from './types';

export type EventCallback<T = unknown> = (event: T, slot: number, signature: string) => void;

export interface EventSubscription {
  eventName: SdkEventName;
  listenerId: number;
  remove(): Promise<void>;
}

export interface JobStorageDeclaredEvent {
  job: PublicKey;
  jobStorage: PublicKey;
  client: PublicKey;
  manifestHash: number[];
  inputRootHash: number[];
  storageRefHash: number[];
  encryptionRefHash: number[];
  createdAtUnix: anchor.BN;
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
  requiredComputeReputation: anchor.BN;
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

export interface DualReputationUpdatedEvent {
  worker: PublicKey;
  oldComputeReputation: anchor.BN;
  newComputeReputation: anchor.BN;
  oldVerifyReputation: anchor.BN;
  newVerifyReputation: anchor.BN;
  globalReputation: anchor.BN;
  reason: number;
  status: number;
}

export interface BayesianReputationUpdatedEvent {
  worker: PublicKey;
  reason: number;
  computeReputation: anchor.BN;
  verifyReputation: anchor.BN;
  globalReputation: anchor.BN;
  reliabilityScore: number;
  computeAlphaLong: anchor.BN;
  computeBetaLong: anchor.BN;
  computeAlphaShort: anchor.BN;
  computeBetaShort: anchor.BN;
  verifyAlphaLong: anchor.BN;
  verifyBetaLong: anchor.BN;
  verifyAlphaShort: anchor.BN;
  verifyBetaShort: anchor.BN;
  computeFraudStrikes: number;
  verifyFraudStrikes: number;
  fraudStrikes: number;
  errorStrikes: number;
}

export interface SiliciumEventMap {
  jobCreated: unknown;
  jobStorageDeclared: JobStorageDeclaredEvent;
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
  dualReputationUpdated: DualReputationUpdatedEvent;
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

export class SiliciumEventClient {
  constructor(private readonly program: anchor.Program<any>) {}

  on<K extends SdkEventName>(
    eventName: K,
    callback: EventCallback<K extends keyof SiliciumEventMap ? SiliciumEventMap[K] : unknown>,
  ): EventSubscription {
    const listenerId = this.program.addEventListener(
      eventName,
      (event: unknown, slot: number, signature: string) => callback(event as any, slot, signature),
    );

    return {
      eventName,
      listenerId,
      remove: async () => {
        await this.program.removeEventListener(listenerId);
      },
    };
  }

  onAll(
    callback: (name: SdkEventName, event: unknown, slot: number, signature: string) => void,
  ): EventSubscription[] {
    return SDK_EVENT_NAMES.map((name) =>
      this.on(name, (event, slot, signature) => callback(name, event, slot, signature)),
    );
  }

  async remove(subscription: EventSubscription): Promise<void> {
    await this.program.removeEventListener(subscription.listenerId);
  }
}

export function pubkey(value: PublicKey | string): PublicKey {
  return typeof value === 'string' ? new PublicKey(value) : value;
}
