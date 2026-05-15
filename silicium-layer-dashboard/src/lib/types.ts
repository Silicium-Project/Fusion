export interface WorkerView {
  pubkey: string;
  owner?: string;
  status: string;
  computeReputation: number;
  verifyReputation: number;
  globalReputation: number;
  stakeAmount: number;
  activeClaims: number;
  totalSubmitted: number;
  totalVerified: number;
  totalRejected: number;
  roles: string[];
}

export interface JobView {
  pubkey: string;
  jobId?: string;
  status: string;
  client?: string;
  mint?: string;
  expectedFragments: number;
  verifiedFragments: number;
  rewardPerFragment?: number;
  verifierRewardPerVote?: number;
}

export interface FragmentView {
  pubkey: string;
  job: string;
  parentFragment?: string;
  fragmentIndex: number;
  status: string;
  isLeaf: boolean;
  depth: number;
  assignedWorker?: string;
  computeWorker?: string;
  requiredComputeReputation: number;
  requiredStake: number;
  yesVotes?: number;
  noVotes?: number;
}

export interface VoteView {
  pubkey: string;
  fragment: string;
  verifier: string;
  choice: boolean;
  round: number;
  slashed: boolean;
}

export interface SplitProposalView {
  pubkey: string;
  parentFragment: string;
  splitterWorker: string;
  childCount: number;
  createdChildren: number;
  approved: boolean;
  status?: string;
}

export interface NetworkStakerView {
  pubkey: string;
  owner?: string;
  amount: number;
  pendingRewards?: number;
}

export interface StakingPoolView {
  pubkey: string;
  totalStaked: number;
  rewardPool?: number;
}

export interface LayerSnapshot {
  source: "demo" | "solana";
  loadedAt: string;
  stats: {
    jobs: number;
    fragments: number;
    workers: number;
    votes: number;
    splitProposals: number;
    stakingPool: number;
    networkStakers: number;
  };
  jobs: JobView[];
  fragments: FragmentView[];
  workers: WorkerView[];
  votes: VoteView[];
  splitProposals: SplitProposalView[];
  networkStakers: NetworkStakerView[];
  stakingPools: StakingPoolView[];
  events: Array<{ name: string; text: string; signature?: string }>;
}
