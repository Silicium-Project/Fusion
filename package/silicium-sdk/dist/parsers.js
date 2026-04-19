import { bigintFrom, bytesToUtf8, numberFrom } from "./utils";
export function parseJobStatus(raw) {
    if (!raw || typeof raw !== "object")
        return "unknown";
    if ("open" in raw)
        return "open";
    if ("cancelled" in raw)
        return "cancelled";
    if ("finalized" in raw)
        return "finalized";
    return "unknown";
}
export function parseFragmentStatus(raw) {
    if (!raw || typeof raw !== "object")
        return "unknown";
    if ("submitted" in raw)
        return "submitted";
    if ("verified" in raw)
        return "verified";
    if ("rejected" in raw)
        return "rejected";
    return "unknown";
}
export function parseWorkerStatus(raw) {
    if (!raw || typeof raw !== "object")
        return "unknown";
    if ("active" in raw)
        return "active";
    if ("banned" in raw)
        return "banned";
    return "unknown";
}
export function parseJob(publicKey, raw) {
    return {
        publicKey,
        jobId: bigintFrom(raw.jobId),
        client: raw.client,
        mint: raw.mint,
        escrow: raw.escrow,
        expectedFragments: numberFrom(raw.expectedFragments),
        verifiedFragments: numberFrom(raw.verifiedFragments),
        rewardPerFragment: bigintFrom(raw.rewardPerFragment),
        depositedAmount: bigintFrom(raw.depositedAmount),
        paidAmount: bigintFrom(raw.paidAmount),
        deadlineUnix: bigintFrom(raw.deadlineUnix),
        status: parseJobStatus(raw.status),
        fragmentQuorum: numberFrom(raw.fragmentQuorum),
        verifiedAtUnix: bigintFrom(raw.verifiedAtUnix),
        bump: numberFrom(raw.bump),
        escrowAuthBump: numberFrom(raw.escrowAuthBump),
        raw,
    };
}
export function parseWorker(publicKey, raw) {
    return {
        publicKey,
        owner: raw.owner,
        stakeMint: raw.stakeMint,
        stakeVault: raw.stakeVault,
        stakeAmount: bigintFrom(raw.stakeAmount),
        reputation: bigintFrom(raw.reputation),
        totalSubmitted: numberFrom(raw.totalSubmitted),
        totalVerified: numberFrom(raw.totalVerified),
        totalRejected: numberFrom(raw.totalRejected),
        roles: numberFrom(raw.roles),
        status: parseWorkerStatus(raw.status),
        bump: numberFrom(raw.bump),
        raw,
    };
}
export function parseFragment(publicKey, raw) {
    return {
        publicKey,
        job: raw.job,
        fragmentIndex: numberFrom(raw.fragmentIndex),
        worker: raw.worker,
        workerTokenAccount: raw.workerTokenAccount,
        resultHash: Array.from(raw.resultHash ?? [], (v) => Number(v)),
        proofRef: Array.from(raw.proofRef ?? [], (v) => Number(v)),
        status: parseFragmentStatus(raw.status),
        yesVotes: numberFrom(raw.yesVotes),
        noVotes: numberFrom(raw.noVotes),
        requiredQuorum: numberFrom(raw.requiredQuorum),
        votingDeadlineUnix: bigintFrom(raw.votingDeadlineUnix),
        round: numberFrom(raw.round),
        bump: numberFrom(raw.bump),
        raw,
    };
}
export function parseFragmentVote(publicKey, raw) {
    return {
        publicKey,
        fragment: raw.fragment,
        verifier: raw.verifier,
        choice: Boolean(raw.choice),
        round: numberFrom(raw.round),
        slashed: Boolean(raw.slashed),
        bump: numberFrom(raw.bump),
        raw,
    };
}
export function parseJobResult(publicKey, raw) {
    const uriLen = numberFrom(raw.uriLen);
    const uriBytes = Array.from(raw.uriBytes ?? [], (v) => Number(v));
    const outputUri = bytesToUtf8(uriBytes.slice(0, uriLen));
    return {
        publicKey,
        job: raw.job,
        finalHash: Array.from(raw.finalHash ?? [], (v) => Number(v)),
        uriLen,
        uriBytes,
        outputUri,
        bump: numberFrom(raw.bump),
        raw,
    };
}
export function parseTreasury(publicKey, raw) {
    return {
        publicKey,
        mint: raw.mint,
        authority: raw.authority,
        admin: raw.admin,
        treasuryTokenAccount: raw.treasuryTokenAccount,
        bump: numberFrom(raw.bump),
        raw,
    };
}
