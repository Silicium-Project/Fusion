import { Idl } from "@coral-xyz/anchor";
import { DEVNET_PROGRAM_ID, DEVNET_RPC, bytesToHex, emptyKeyToUndefined, enumName, makeReadonlyProgram, safeAll, toBase58, toNum } from "./solana";
import type { FragmentResolutionView, FragmentView, JobView, LayerSnapshot, NetworkStakerView, SplitProposalView, StakingPoolView, VoteView, WorkerView } from "./types";

function rolesFromAccount(acc: any): string[] {
  const roles = toNum(acc.roles ?? acc.roleFlags ?? acc.roleMask);
  const list: string[] = [];
  if (roles === 0) return list;
  if (roles & 1) list.push("compute");
  if (roles & 2) list.push("verify");
  if (!list.length && acc.preferredRole != null) list.push(enumName(acc.preferredRole));
  return list;
}

function mapWorker(row: any): WorkerView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    owner: toBase58(a.owner),
    status: enumName(a.status),
    computeReputation: toNum(a.computeReputation),
    verifyReputation: toNum(a.verifyReputation),
    globalReputation: toNum(a.globalReputation),
    stakeAmount: toNum(a.stakeAmount),
    activeClaims: toNum(a.activeClaims),
    totalSubmitted: toNum(a.totalSubmitted),
    totalVerified: toNum(a.totalVerified),
    totalRejected: toNum(a.totalRejected),
    roles: rolesFromAccount(a),
  };
}

function mapJob(row: any): JobView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    jobId: a.jobId?.toString?.() ?? String(a.jobId ?? ""),
    status: enumName(a.status),
    client: toBase58(a.client),
    mint: toBase58(a.mint),
    createdAtUnix: toNum(a.createdAtUnix ?? a.created_at_unix),
    expectedFragments: toNum(a.expectedFragments),
    verifiedFragments: toNum(a.verifiedFragments),
    rewardPerFragment: toNum(a.rewardPerFragment),
    verifierRewardPerVote: toNum(a.verifierRewardPerVote),
  };
}

function mapFragment(row: any): FragmentView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    job: toBase58(a.job),
    parentFragment: emptyKeyToUndefined(a.parentFragment),
    fragmentIndex: toNum(a.fragmentIndex),
    status: enumName(a.status),
    isLeaf: Boolean(a.isLeaf ?? true),
    depth: toNum(a.depth),
    assignedWorker: toBase58(a.assignedWorker) || undefined,
    computeWorker: toBase58(a.worker) || undefined,
    requiredComputeReputation: toNum(a.requiredComputeReputation ?? a.requiredReputation),
    requiredStake: toNum(a.requiredStake),
    yesVotes: toNum(a.yesVotes),
    noVotes: toNum(a.noVotes),
    resultHash: bytesToHex(a.resultHash ?? a.result_hash),
    proofRef: bytesToHex(a.proofRef ?? a.proof_ref),
    complexityScore: toNum(a.complexityScore ?? a.complexity_score),
  };
}

function mapFragmentResolution(row: any): FragmentResolutionView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    fragment: toBase58(a.fragment),
    round: toNum(a.round),
    resolved: Boolean(a.resolved),
    winningChoice: Boolean(a.winningChoice ?? a.winning_choice),
    eligibleRewards: toNum(a.eligibleRewards ?? a.eligible_rewards),
    claimedRewards: toNum(a.claimedRewards ?? a.claimed_rewards),
  };
}

function mapVote(row: any): VoteView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    fragment: toBase58(a.fragment),
    verifier: toBase58(a.verifier),
    choice: Boolean(a.choice ?? a.vote ?? false),
    round: toNum(a.round),
    slashed: Boolean(a.slashed),
  };
}

function mapSplit(row: any): SplitProposalView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    parentFragment: toBase58(a.parentFragment),
    splitterWorker: toBase58(a.splitterWorker ?? a.splitter),
    childCount: toNum(a.childCount),
    createdChildren: toNum(a.createdChildren ?? a.childrenCreated),
    approved: Boolean(a.approved),
    status: enumName(a.status),
  };
}

function mapNetworkStaker(row: any): NetworkStakerView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    owner: toBase58(a.owner),
    amount: toNum(a.amount ?? a.stakedAmount),
    pendingRewards: toNum(a.pendingRewards ?? a.rewardDebt),
  };
}

function mapPool(row: any): StakingPoolView {
  const a = row.account;
  return {
    pubkey: row.publicKey.toBase58(),
    totalStaked: toNum(a.totalStaked),
    rewardPool: toNum(a.rewardPool ?? a.totalRewards),
  };
}

export async function fetchLayerSnapshot(params: {
  idl: Idl;
  rpcUrl?: string;
  programId?: string;
}): Promise<LayerSnapshot> {
  const rpcUrl = params.rpcUrl || DEVNET_RPC;
  const programId = params.programId || DEVNET_PROGRAM_ID;
  const program = makeReadonlyProgram(params.idl, rpcUrl, programId) as any;

  const [workerRows, jobRows, fragmentRows, voteRows, resolutionRows, splitRows, stakerRows, poolRows] = await Promise.all([
    safeAll(program, "worker"),
    safeAll(program, "job"),
    safeAll(program, "fragment"),
    safeAll(program, "fragmentVote"),
    safeAll(program, "fragmentResolution"),
    safeAll(program, "splitProposal"),
    safeAll(program, "networkStaker"),
    safeAll(program, "stakingPool"),
  ]);

  const workers = workerRows.map(mapWorker);
  const jobs = jobRows.map(mapJob);
  const fragments = fragmentRows.map(mapFragment);
  const votes = voteRows.map(mapVote);
  const fragmentResolutions = resolutionRows.map(mapFragmentResolution);
  const splitProposals = splitRows.map(mapSplit);
  const networkStakers = stakerRows.map(mapNetworkStaker);
  const stakingPools = poolRows.map(mapPool);

  return {
    source: "solana",
    loadedAt: new Date().toISOString(),
    stats: {
      jobs: jobs.length,
      fragments: fragments.length,
      workers: workers.length,
      votes: votes.length,
      fragmentResolutions: fragmentResolutions.length,
      splitProposals: splitProposals.length,
      stakingPool: stakingPools.length,
      networkStakers: networkStakers.length,
    },
    jobs,
    fragments,
    workers,
    votes,
    fragmentResolutions,
    splitProposals,
    networkStakers,
    stakingPools,
    events: [],
  };
}
