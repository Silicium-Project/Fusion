import * as anchor from "@coral-xyz/anchor";
import { PublicKey, Signer } from "@solana/web3.js";

export type IdlProgram = anchor.Program<any>;
export type Amount = anchor.BN | number | bigint | string;
export type Hash32 = number[] | Uint8Array;

export interface CreateSdkParams {
  provider: anchor.AnchorProvider;
  program: IdlProgram;
}

export interface WorkerReputationSnapshot {
  computeReputation: anchor.BN;
  verifyReputation: anchor.BN;
  globalReputation: anchor.BN;
  reliabilityScore?: number;
  computeAlphaLong?: anchor.BN;
  computeBetaLong?: anchor.BN;
  computeAlphaShort?: anchor.BN;
  computeBetaShort?: anchor.BN;
  verifyAlphaLong?: anchor.BN;
  verifyBetaLong?: anchor.BN;
  verifyAlphaShort?: anchor.BN;
  verifyBetaShort?: anchor.BN;
  computeFraudStrikes?: number;
  verifyFraudStrikes?: number;
  fraudStrikes?: number;
  errorStrikes?: number;
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


export interface DeclareJobStorageParams {
  client?: PublicKey;
  job: PublicKey;
  manifestHash: Hash32;
  inputRootHash: Hash32;
  storageRefHash: Hash32;
  encryptionRefHash?: Hash32;
  signers?: Signer[];
}

export interface RegisterWorkerParams {
  worker?: PublicKey;
  signers?: Signer[];
}

export interface RegisterWorkerPayoutParams {
  worker: PublicKey;
  pairingCode?: string;
  nodeId?: string;
  peerId?: string;
  workerProofSignature?: Uint8Array;
  payoutWallet?: PublicKey;
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
  workerPayoutToken?: PublicKey;
  choice: boolean;
  round?: number;
  computeWorker?: PublicKey;
  signers?: Signer[];
}

export interface ClaimVerifierRewardParams {
  verifier?: PublicKey;
  job: PublicKey;
  fragment: PublicKey;
  escrow: PublicKey;
  verifierToken: PublicKey;
  verifierPayoutToken?: PublicKey;
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
  signers?: Signer[];
}

export interface InitStakingPoolParams {
  payer?: PublicKey;
  mint: PublicKey;
  stakeVault: Signer;
  rewardVault: Signer;
}

export interface StakeNetworkParams {
  owner?: PublicKey;
  mint: PublicKey;
  ownerToken: PublicKey;
  amount: Amount;
  stakeVault?: PublicKey;
  signers?: Signer[];
}

export interface FundStakingRewardsParams {
  funder?: PublicKey;
  mint: PublicKey;
  funderToken: PublicKey;
  amount: Amount;
  rewardVault?: PublicKey;
  signers?: Signer[];
}

export interface ClaimStakingRewardParams {
  owner?: PublicKey;
  mint: PublicKey;
  ownerRewardToken: PublicKey;
  rewardVault?: PublicKey;
  signers?: Signer[];
}

export interface RequestUnstakeParams {
  owner?: PublicKey;
  mint: PublicKey;
  amount: Amount;
  signers?: Signer[];
}

export interface WithdrawUnstakedParams {
  owner?: PublicKey;
  mint: PublicKey;
  ownerToken: PublicKey;
  stakeVault?: PublicKey;
  signers?: Signer[];
}


export interface ProposeFragmentSplitParams {
  splitter?: PublicKey;
  job: PublicKey;
  parentFragment?: PublicKey;
  parentFragmentIndex: number;
  manifestHash: Hash32;
  childCount: number;
  round?: number;
  signers?: Signer[];
}

export interface ApproveFragmentSplitParams {
  authority?: PublicKey;
  job: PublicKey;
  parentFragment?: PublicKey;
  parentFragmentIndex: number;
  splitProposal?: PublicKey;
  round?: number;
  approve: boolean;
  signers?: Signer[];
}

export interface CreateSubFragmentParams {
  payer?: PublicKey;
  job: PublicKey;
  parentFragment?: PublicKey;
  parentFragmentIndex: number;
  splitProposal?: PublicKey;
  round?: number;
  childFragmentIndex: number;
  requiredComputeReputation: Amount;
  requiredStake: Amount;
  complexityScore: number;
  inputHash: Hash32;
  signers?: Signer[];
}

export type SdkEventName =
  | "jobCreated"
  | "jobStorageDeclared"
  | "workerRegistered"
  | "workerStaked"
  | "treasuryInitialized"
  | "fragmentClaimed"
  | "fragmentReclaimed"
  | "fragmentSubmitted"
  | "fragmentVerified"
  | "fragmentRejected"
  | "verifierRewardClaimed"
  | "jobFinalized"
  | "jobCancelled"
  | "voteSlashed"
  | "dualReputationUpdated"
  | "bayesianReputationUpdated"
  | "fragmentSplitProposed"
  | "fragmentSplitApproved"
  | "fragmentSplitRejected"
  | "subFragmentCreated"
  | "fragmentSplitCompleted"
  | "stakingPoolInitialized"
  | "networkStakeDeposited"
  | "stakingRewardsFunded"
  | "stakingRewardClaimed"
  | "networkUnstakeRequested"
  | "networkUnstakeWithdrawn";

export const SDK_EVENT_NAMES: SdkEventName[] = [
  "jobCreated",
  "jobStorageDeclared",
  "workerRegistered",
  "workerStaked",
  "treasuryInitialized",
  "fragmentClaimed",
  "fragmentReclaimed",
  "fragmentSubmitted",
  "fragmentVerified",
  "fragmentRejected",
  "verifierRewardClaimed",
  "jobFinalized",
  "jobCancelled",
  "voteSlashed",
  "dualReputationUpdated",
  "bayesianReputationUpdated",
  "fragmentSplitProposed",
  "fragmentSplitApproved",
  "fragmentSplitRejected",
  "subFragmentCreated",
  "fragmentSplitCompleted",
  "stakingPoolInitialized",
  "networkStakeDeposited",
  "stakingRewardsFunded",
  "stakingRewardClaimed",
  "networkUnstakeRequested",
  "networkUnstakeWithdrawn",
];
