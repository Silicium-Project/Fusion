export const SEEDS = {
  job: "job",
  escrowAuth: "escrow_auth",
  result: "result",
  worker: "worker",
  fragment: "fragment",
  fragmentVote: "fragment_vote",
  stakeAuth: "stake_auth",
  stakeVault: "stake_vault",
  treasuryState: "treasury",
  treasuryAuth: "treasury_auth",
} as const;

export const ROLE_COMPUTE = 1 << 0;
export const ROLE_VERIFY = 1 << 1;
export const ROLE_ADMIN = 1 << 2;

export const URI_MAX_LEN = 128;
