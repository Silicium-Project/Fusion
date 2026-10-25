export const MAX_SIL_FRAGMENTS = 1_000;
export const MAX_SIL_FRAGMENT_NODES = 1_000;

const MAX_SIL_LEAF_MULTIPLIER = 16;

/** Computes the maximum number of paid leaves without loading Solana RPC code. */
export function maxSILFragments(initialFragments: number): number {
  if (!Number.isInteger(initialFragments) || initialFragments < 1 || initialFragments > 256) {
    throw new Error('Invalid SIL quote fragment count.');
  }
  const childSlotsPerRoot = Math.floor(
    (MAX_SIL_FRAGMENT_NODES - initialFragments) / initialFragments,
  );
  const leavesPerRoot = 1 + Math.floor(childSlotsPerRoot / 2);
  return Math.min(
    MAX_SIL_FRAGMENTS,
    initialFragments * MAX_SIL_LEAF_MULTIPLIER,
    initialFragments * leavesPerRoot,
  );
}
