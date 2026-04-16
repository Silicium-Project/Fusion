import * as anchor from "@coral-xyz/anchor";
import {
  BN,
  Program,
  AnchorProvider,
  web3,
} from "@coral-xyz/anchor";
import {
  Connection,
  PublicKey,
  TransactionSignature,
  Commitment,
  ConfirmOptions,
} from "@solana/web3.js";
import {
  TOKEN_PROGRAM_ID,
  getAssociatedTokenAddressSync,
} from "@solana/spl-token";

// Replace this import with your generated Anchor type when available.
// Example:
// import { SiliciumChain } from "../target/types/silicium_chain";
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

export interface ResubmitFragmentParams extends SubmitFragmentParams {}

export interface VoteFragmentParams {
  verifier?: PublicKey;
  job: PublicKey;
  fragmentIndex: number;
  workerToken: PublicKey;
  choice: boolean;
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
  treasuryTokenAccount?: PublicKey;
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
  bump: number;
  raw: any;
}

const SEEDS = {
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

export class SiliciumSdk {
  readonly provider: AnchorProvider;
  readonly program: Program<SiliciumChain>;
  readonly connection: Connection;
  readonly programId: PublicKey;
  readonly commitment: Commitment;

  constructor(options: SiliciumSdkOptions) {
    this.provider = options.provider;
    this.program = options.program;
    this.connection = options.provider.connection;
    this.programId = options.programId;
    this.commitment = options.commitment ?? "confirmed";
  }

  static fromProgram(program: Program<SiliciumChain>, provider?: AnchorProvider): SiliciumSdk {
    const resolvedProvider = provider ?? (program.provider as AnchorProvider);
    return new SiliciumSdk({
      provider: resolvedProvider,
      program,
      programId: program.programId,
    });
  }

  get walletPublicKey(): PublicKey {
    const key = this.provider.wallet?.publicKey;
    if (!key) {
      throw new Error("Provider wallet is missing.");
    }
    return key;
  }

  // ---------------------------------------------------------------------------
  // PDA HELPERS
  // ---------------------------------------------------------------------------

  findJobPda(client: PublicKey, jobId: number | bigint | BN): [PublicKey, number] {
    const jobIdBuffer = bnToLeBuffer(jobId, 8);
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.job), client.toBuffer(), jobIdBuffer],
      this.programId,
    );
  }

  findEscrowAuthPda(job: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.escrowAuth), job.toBuffer()],
      this.programId,
    );
  }

  findResultPda(job: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.result), job.toBuffer()],
      this.programId,
    );
  }

  findWorkerPda(workerWallet: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.worker), workerWallet.toBuffer()],
      this.programId,
    );
  }

  findFragmentPda(job: PublicKey, fragmentIndex: number): [PublicKey, number] {
    const fragmentIndexBuffer = u32ToLeBuffer(fragmentIndex);
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.fragment), job.toBuffer(), fragmentIndexBuffer],
      this.programId,
    );
  }

  findFragmentVotePda(fragment: PublicKey, verifier: PublicKey, round: number): [PublicKey, number] {
    const roundBuffer = u16ToLeBuffer(round);
    return PublicKey.findProgramAddressSync(
      [
        bufferFromString(SEEDS.fragmentVote),
        fragment.toBuffer(),
        verifier.toBuffer(),
        roundBuffer,
      ],
      this.programId,
    );
  }

  findStakeAuthPda(workerAccount: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.stakeAuth), workerAccount.toBuffer()],
      this.programId,
    );
  }

  findStakeVaultPda(workerWallet: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.stakeVault), workerWallet.toBuffer()],
      this.programId,
    );
  }

  findTreasuryStatePda(mint: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.treasuryState), mint.toBuffer()],
      this.programId,
    );
  }

  findTreasuryAuthPda(mint: PublicKey): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.treasuryAuth), mint.toBuffer()],
      this.programId,
    );
  }

  // ---------------------------------------------------------------------------
  // TRANSACTION HELPERS
  // ---------------------------------------------------------------------------

  async createJob(params: CreateJobParams): Promise<{
    signature: TransactionSignature;
    job: PublicKey;
    escrowAuth: PublicKey;
  }> {
    const client = params.client ?? this.walletPublicKey;
    const [job] = this.findJobPda(client, params.jobId);
    const [escrowAuth] = this.findEscrowAuthPda(job);

    const signature = await this.program.methods
      .createJob(
        toBN(params.jobId),
        params.expectedFragments,
        toBN(params.rewardPerFragment),
        toBN(params.deadlineUnix),
        params.fragmentQuorum,
      )
      .accounts({
        client,
        mint: params.mint,
        job,
        escrowAuth,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
        rent: web3.SYSVAR_RENT_PUBKEY,
      })
      .rpc(params.confirmOptions);

    return { signature, job, escrowAuth };
  }

  async registerWorker(params: RegisterWorkerParams = {}): Promise<{
    signature: TransactionSignature;
    workerAccount: PublicKey;
  }> {
    const worker = params.worker ?? this.walletPublicKey;
    const [workerAccount] = this.findWorkerPda(worker);

    const signature = await this.program.methods
      .registerWorker()
      .accounts({
        worker,
        workerAccount,
        systemProgram: web3.SystemProgram.programId,
      })
      .rpc(params.confirmOptions);

    return { signature, workerAccount };
  }

  async stakeWorker(params: StakeWorkerParams): Promise<{
    signature: TransactionSignature;
    workerAccount: PublicKey;
    stakeAuth: PublicKey;
    stakeVault: PublicKey;
  }> {
    const worker = params.worker ?? this.walletPublicKey;
    const [workerAccount] = this.findWorkerPda(worker);
    const [stakeAuth] = this.findStakeAuthPda(workerAccount);
    const [stakeVault] = this.findStakeVaultPda(worker);

    const signature = await this.program.methods
      .stakeWorker(toBN(params.amount))
      .accounts({
        worker,
        workerAccount,
        mint: params.mint,
        workerToken: params.workerToken,
        stakeAuth,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
        rent: web3.SYSVAR_RENT_PUBKEY,
      })
      .rpc(params.confirmOptions);

    return { signature, workerAccount, stakeAuth, stakeVault };
  }

  async submitFragment(params: SubmitFragmentParams): Promise<{
    signature: TransactionSignature;
    workerAccount: PublicKey;
    fragment: PublicKey;
  }> {
    const worker = params.worker ?? this.walletPublicKey;
    const [workerAccount] = this.findWorkerPda(worker);
    const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);

    const signature = await this.program.methods
      .submitFragmentResult(
        params.fragmentIndex,
        normalize32(params.resultHash),
        normalize32(params.proofRef),
      )
      .accounts({
        worker,
        workerAccount,
        job: params.job,
        fragment,
        workerToken: params.workerToken,
        systemProgram: web3.SystemProgram.programId,
      })
      .rpc(params.confirmOptions);

    return { signature, workerAccount, fragment };
  }

  async resubmitFragment(params: ResubmitFragmentParams): Promise<{
    signature: TransactionSignature;
    workerAccount: PublicKey;
    fragment: PublicKey;
  }> {
    const worker = params.worker ?? this.walletPublicKey;
    const [workerAccount] = this.findWorkerPda(worker);
    const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);

    const signature = await this.program.methods
      .resubmitFragmentResult(
        params.fragmentIndex,
        normalize32(params.resultHash),
        normalize32(params.proofRef),
      )
      .accounts({
        worker,
        workerAccount,
        job: params.job,
        fragment,
        workerToken: params.workerToken,
      })
      .rpc(params.confirmOptions);

    return { signature, workerAccount, fragment };
  }

  async voteFragment(params: VoteFragmentParams): Promise<{
    signature: TransactionSignature;
    verifierWorker: PublicKey;
    fragment: PublicKey;
    vote: PublicKey;
  }> {
    const verifier = params.verifier ?? this.walletPublicKey;
    const [verifierWorker] = this.findWorkerPda(verifier);
    const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);

    const fragmentAccount = await this.program.account.fragment.fetch(fragment);
    const round = numberFrom(fragmentAccount.round);
    const [vote] = this.findFragmentVotePda(fragment, verifier, round);
    const [escrowAuth] = this.findEscrowAuthPda(params.job);

    const signature = await this.program.methods
      .voteFragment(params.choice)
      .accounts({
        verifier,
        job: params.job,
        fragment,
        verifierWorker,
        vote,
        escrowAuth,
        escrow: fragmentAccount.job ? (await this.program.account.job.fetch(params.job)).escrow : undefined,
        workerToken: params.workerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
      })
      .rpc(params.confirmOptions);

    return { signature, verifierWorker, fragment, vote };
  }

  async finalizeJob(params: FinalizeJobParams): Promise<{
    signature: TransactionSignature;
    result: PublicKey;
    escrowAuth: PublicKey;
  }> {
    const client = params.client ?? this.walletPublicKey;
    const [result] = this.findResultPda(params.job);
    const [escrowAuth] = this.findEscrowAuthPda(params.job);
    const job = await this.program.account.job.fetch(params.job);

    const signature = await this.program.methods
      .finalizeJob(normalize32(params.finalHash), normalizeBytes(params.outputUri))
      .accounts({
        client,
        job: params.job,
        result,
        escrowAuth,
        escrow: job.escrow,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
      })
      .rpc(params.confirmOptions);

    return { signature, result, escrowAuth };
  }

  async cancelJob(params: CancelJobParams): Promise<{
    signature: TransactionSignature;
    escrowAuth: PublicKey;
  }> {
    const client = params.client ?? this.walletPublicKey;
    const [escrowAuth] = this.findEscrowAuthPda(params.job);
    const job = await this.program.account.job.fetch(params.job);

    const signature = await this.program.methods
      .cancelJob()
      .accounts({
        client,
        job: params.job,
        escrowAuth,
        escrow: job.escrow,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc(params.confirmOptions);

    return { signature, escrowAuth };
  }

  async initTreasury(params: InitTreasuryParams): Promise<{
    signature: TransactionSignature;
    treasuryState: PublicKey;
    treasuryAuth: PublicKey;
    treasury: PublicKey;
  }> {
    const payer = params.payer ?? this.walletPublicKey;
    const [treasuryState] = this.findTreasuryStatePda(params.mint);
    const [treasuryAuth] = this.findTreasuryAuthPda(params.mint);
    const treasury = params.treasuryTokenAccount ?? getAssociatedTokenAddressSync(params.mint, treasuryAuth, true);

    const signature = await this.program.methods
      .initTreasury()
      .accounts({
        payer,
        mint: params.mint,
        treasuryState,
        treasuryAuth,
        treasury,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
        rent: web3.SYSVAR_RENT_PUBKEY,
      })
      .rpc(params.confirmOptions);

    return { signature, treasuryState, treasuryAuth, treasury };
  }

  async slashVote(params: SlashVoteParams): Promise<{
    signature: TransactionSignature;
    fragment: PublicKey;
    vote: PublicKey;
    verifierWorker: PublicKey;
    stakeVault: PublicKey;
    treasuryState: PublicKey;
    treasuryAuth: PublicKey;
  }> {
    const slasher = params.slasher ?? this.walletPublicKey;
    const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);
    const [vote] = this.findFragmentVotePda(fragment, params.verifier, params.round);
    const [verifierWorker] = this.findWorkerPda(params.verifier);
    const [stakeAuth] = this.findStakeAuthPda(verifierWorker);
    const [stakeVault] = this.findStakeVaultPda(params.verifier);

    const job = await this.program.account.job.fetch(params.job);
    const [treasuryState] = this.findTreasuryStatePda(job.mint);
    const [treasuryAuth] = this.findTreasuryAuthPda(job.mint);
    const treasuryStateAccount = await this.program.account.treasury.fetch(treasuryState);

    const signature = await this.program.methods
      .slashVote()
      .accounts({
        slasher,
        job: params.job,
        fragment,
        vote,
        verifierWorker,
        treasuryState,
        stakeAuth,
        stakeVault,
        treasuryAuth,
        treasury: treasuryStateAccount.authority ? job.mint : undefined,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc(params.confirmOptions);

    return {
      signature,
      fragment,
      vote,
      verifierWorker,
      stakeVault,
      treasuryState,
      treasuryAuth,
    };
  }

  // ---------------------------------------------------------------------------
  // FETCH HELPERS
  // ---------------------------------------------------------------------------

  async fetchJob(job: PublicKey): Promise<ParsedJobAccount | null> {
    const account = await this.program.account.job.fetchNullable(job);
    return account ? parseJob(job, account) : null;
  }

  async fetchJobById(client: PublicKey, jobId: number | bigint | BN): Promise<ParsedJobAccount | null> {
    const [job] = this.findJobPda(client, jobId);
    return this.fetchJob(job);
  }

  async fetchWorker(workerWallet: PublicKey): Promise<ParsedWorkerAccount | null> {
    const [worker] = this.findWorkerPda(workerWallet);
    const account = await this.program.account.worker.fetchNullable(worker);
    return account ? parseWorker(worker, account) : null;
  }

  async fetchFragment(job: PublicKey, fragmentIndex: number): Promise<ParsedFragmentAccount | null> {
    const [fragment] = this.findFragmentPda(job, fragmentIndex);
    const account = await this.program.account.fragment.fetchNullable(fragment);
    return account ? parseFragment(fragment, account) : null;
  }

  async fetchFragmentVote(fragment: PublicKey, verifier: PublicKey, round: number): Promise<ParsedFragmentVoteAccount | null> {
    const [vote] = this.findFragmentVotePda(fragment, verifier, round);
    const account = await this.program.account.fragmentVote.fetchNullable(vote);
    return account ? parseFragmentVote(vote, account) : null;
  }

  async fetchJobResult(job: PublicKey): Promise<ParsedJobResultAccount | null> {
    const [result] = this.findResultPda(job);
    const account = await this.program.account.jobResult.fetchNullable(result);
    return account ? parseJobResult(result, account) : null;
  }

  async fetchTreasuryState(mint: PublicKey): Promise<ParsedTreasuryAccount | null> {
    const [treasuryState] = this.findTreasuryStatePda(mint);
    const account = await this.program.account.treasury.fetchNullable(treasuryState);
    return account ? parseTreasury(treasuryState, account) : null;
  }

  async listAllJobs(): Promise<ParsedJobAccount[]> {
    const rows = await this.program.account.job.all();
    return rows.map((row: any) => parseJob(row.publicKey, row.account));
  }

  async listJobsByClient(client: PublicKey): Promise<ParsedJobAccount[]> {
    const rows = await this.program.account.job.all([
      {
        memcmp: {
          offset: 8 + 8,
          bytes: client.toBase58(),
        },
      },
    ]);
    return rows.map((row: any) => parseJob(row.publicKey, row.account));
  }

  async listFragmentsByJob(job: PublicKey): Promise<ParsedFragmentAccount[]> {
    const rows = await this.program.account.fragment.all([
      {
        memcmp: {
          offset: 8,
          bytes: job.toBase58(),
        },
      },
    ]);
    return rows.map((row: any) => parseFragment(row.publicKey, row.account));
  }

  async listFragmentVotesByFragment(fragment: PublicKey): Promise<ParsedFragmentVoteAccount[]> {
    const rows = await this.program.account.fragmentVote.all([
      {
        memcmp: {
          offset: 8,
          bytes: fragment.toBase58(),
        },
      },
    ]);
    return rows.map((row: any) => parseFragmentVote(row.publicKey, row.account));
  }

  async fetchJobAggregate(client: PublicKey, jobId: number | bigint | BN): Promise<{
    job: ParsedJobAccount | null;
    fragments: ParsedFragmentAccount[];
    result: ParsedJobResultAccount | null;
  }> {
    const job = await this.fetchJobById(client, jobId);
    if (!job) {
      return { job: null, fragments: [], result: null };
    }

    const [jobPda] = this.findJobPda(client, jobId);
    const [fragments, result] = await Promise.all([
      this.listFragmentsByJob(jobPda),
      this.fetchJobResult(jobPda),
    ]);

    return { job, fragments, result };
  }
}

// -----------------------------------------------------------------------------
// PARSERS
// -----------------------------------------------------------------------------

function parseJob(publicKey: PublicKey, raw: any): ParsedJobAccount {
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

function parseWorker(publicKey: PublicKey, raw: any): ParsedWorkerAccount {
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

function parseFragment(publicKey: PublicKey, raw: any): ParsedFragmentAccount {
  return {
    publicKey,
    job: raw.job,
    fragmentIndex: numberFrom(raw.fragmentIndex),
    worker: raw.worker,
    workerTokenAccount: raw.workerTokenAccount,
    resultHash: Array.from(raw.resultHash ?? []),
    proofRef: Array.from(raw.proofRef ?? []),
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

function parseFragmentVote(publicKey: PublicKey, raw: any): ParsedFragmentVoteAccount {
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

function parseJobResult(publicKey: PublicKey, raw: any): ParsedJobResultAccount {
  const uriLen = numberFrom(raw.uriLen);
  const uriBytes = Array.from(raw.uriBytes ?? []);
  const outputUri = bytesToUtf8(uriBytes.slice(0, uriLen));

  return {
    publicKey,
    job: raw.job,
    finalHash: Array.from(raw.finalHash ?? []),
    uriLen,
    uriBytes,
    outputUri,
    bump: numberFrom(raw.bump),
    raw,
  };
}

function parseTreasury(publicKey: PublicKey, raw: any): ParsedTreasuryAccount {
  return {
    publicKey,
    mint: raw.mint,
    authority: raw.authority,
    admin: raw.admin,
    bump: numberFrom(raw.bump),
    raw,
  };
}

// -----------------------------------------------------------------------------
// SMALL UTILITIES
// -----------------------------------------------------------------------------

export function toBN(value: number | bigint | BN): BN {
  return BN.isBN(value) ? value : new BN(value.toString());
}

export function bigintFrom(value: any): bigint {
  if (typeof value === "bigint") return value;
  if (BN.isBN(value)) return BigInt(value.toString());
  if (typeof value === "number") return BigInt(value);
  if (typeof value === "string") return BigInt(value);
  return BigInt(0);
}

export function numberFrom(value: any): number {
  if (typeof value === "number") return value;
  if (typeof value === "bigint") return Number(value);
  if (BN.isBN(value)) return value.toNumber();
  if (typeof value === "string") return Number(value);
  return 0;
}

export function normalize32(value: Uint8Array | number[]): number[] {
  const bytes = Array.from(value);
  if (bytes.length !== 32) {
    throw new Error(`Expected exactly 32 bytes, received ${bytes.length}.`);
  }
  return bytes;
}

export function normalizeBytes(value: string | Uint8Array | number[]): number[] {
  if (typeof value === "string") {
    return Array.from(new TextEncoder().encode(value));
  }
  return Array.from(value);
}

export function bytesToUtf8(bytes: number[]): string {
  return new TextDecoder().decode(new Uint8Array(bytes));
}

export function bnToLeBuffer(value: number | bigint | BN, size: number): Buffer {
  const bn = toBN(value);
  return bn.toArrayLike(Buffer, "le", size);
}

export function u32ToLeBuffer(value: number): Buffer {
  const buffer = Buffer.alloc(4);
  buffer.writeUInt32LE(value, 0);
  return buffer;
}

export function u16ToLeBuffer(value: number): Buffer {
  const buffer = Buffer.alloc(2);
  buffer.writeUInt16LE(value, 0);
  return buffer;
}

export function bufferFromString(value: string): Buffer {
  return Buffer.from(value, "utf8");
}

export function parseJobStatus(raw: any): JobStatus {
  if (!raw || typeof raw !== "object") return "unknown";
  if ("open" in raw) return "open";
  if ("cancelled" in raw) return "cancelled";
  if ("finalized" in raw) return "finalized";
  return "unknown";
}

export function parseFragmentStatus(raw: any): FragmentStatus {
  if (!raw || typeof raw !== "object") return "unknown";
  if ("submitted" in raw) return "submitted";
  if ("verified" in raw) return "verified";
  if ("rejected" in raw) return "rejected";
  return "unknown";
}

export function parseWorkerStatus(raw: any): WorkerStatus {
  if (!raw || typeof raw !== "object") return "unknown";
  if ("active" in raw) return "active";
  if ("banned" in raw) return "banned";
  return "unknown";
}

// -----------------------------------------------------------------------------
// OPTIONAL FACTORY HELPERS
// -----------------------------------------------------------------------------

export async function buildSiliciumSdk(params: {
  connection: Connection;
  wallet: WalletLike;
  idl: any;
  programId: PublicKey;
  opts?: anchor.ProviderOptions;
}): Promise<SiliciumSdk> {
  const provider = new AnchorProvider(
    params.connection,
    params.wallet,
    params.opts ?? AnchorProvider.defaultOptions(),
  );

  const program = new Program<SiliciumChain>(
    params.idl,
    params.programId,
    provider,
  );

  return SiliciumSdk.fromProgram(program, provider);
}

// -----------------------------------------------------------------------------
// USAGE EXAMPLE
// -----------------------------------------------------------------------------

/*
import { Connection, PublicKey } from "@solana/web3.js";
import { AnchorProvider, Program } from "@coral-xyz/anchor";
import idl from "./idl/silicium_chain.json";

const provider = AnchorProvider.env();
const programId = new PublicKey("4LHNxzAoaumTaJC5zC8C4tRvR71Gwi48YjLraeuVMLsU");
const program = new Program(idl as any, programId, provider);
const sdk = SiliciumSdk.fromProgram(program, provider);

const { signature, job } = await sdk.createJob({
  mint: new PublicKey("..."),
  clientToken: new PublicKey("..."),
  jobId: 1,
  expectedFragments: 8,
  rewardPerFragment: 1000,
  deadlineUnix: Math.floor(Date.now() / 1000) + 3600,
  fragmentQuorum: 2,
});

const worker = await sdk.fetchWorker(provider.wallet.publicKey);
const aggregate = await sdk.fetchJobAggregate(provider.wallet.publicKey, 1);
*/
