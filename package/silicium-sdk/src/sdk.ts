import * as anchor from "@coral-xyz/anchor";
import { AnchorProvider, Program, web3 } from "@coral-xyz/anchor";
import { PublicKey, type Commitment, type Connection, type TransactionSignature } from "@solana/web3.js";
import { TOKEN_PROGRAM_ID } from "@solana/spl-token";
import { SEEDS } from "./constants";
import {
  parseFragment,
  parseFragmentVote,
  parseJob,
  parseJobResult,
  parseTreasury,
  parseWorker,
} from "./parsers";
import type {
  BuildSiliciumSdkParams,
  CancelJobParams,
  CreateJobParams,
  FinalizeJobParams,
  InitTreasuryParams,
  JobAggregate,
  ParsedFragmentAccount,
  ParsedFragmentVoteAccount,
  ParsedJobAccount,
  ParsedJobResultAccount,
  ParsedTreasuryAccount,
  ParsedWorkerAccount,
  ProgramAccountRow,
  RegisterWorkerParams,
  ResubmitFragmentParams,
  SiliciumChain,
  SiliciumSdkOptions,
  SlashVoteParams,
  StakeWorkerParams,
  SubmitFragmentParams,
  VoteFragmentParams,
} from "./types";
import {
  bnToLeBuffer,
  bufferFromString,
  normalize32,
  normalizeBytes,
  numberFrom,
  toBN,
  u16ToLeBuffer,
  u32ToLeBuffer,
} from "./utils";

type AnyProgram = Program<any>;

export class SiliciumSdk {
  readonly provider: AnchorProvider;
  readonly program: AnyProgram;
  readonly connection: Connection;
  readonly programId: PublicKey;
  readonly commitment: Commitment;

  constructor(options: SiliciumSdkOptions) {
    this.provider = options.provider;
    this.program = options.program as AnyProgram;
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

  private get accountApi(): any {
    return (this.program as any).account;
  }

  private get methodsApi(): any {
    return (this.program as any).methods;
  }

  findJobPda(client: PublicKey, jobId: Parameters<typeof bnToLeBuffer>[0]): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.job), client.toBuffer(), bnToLeBuffer(jobId, 8)],
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
    return PublicKey.findProgramAddressSync(
      [bufferFromString(SEEDS.fragment), job.toBuffer(), u32ToLeBuffer(fragmentIndex)],
      this.programId,
    );
  }

  findFragmentVotePda(fragment: PublicKey, verifier: PublicKey, round: number): [PublicKey, number] {
    return PublicKey.findProgramAddressSync(
      [
        bufferFromString(SEEDS.fragmentVote),
        fragment.toBuffer(),
        verifier.toBuffer(),
        u16ToLeBuffer(round),
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

  async createJob(params: CreateJobParams): Promise<{
    signature: TransactionSignature;
    job: PublicKey;
    escrowAuth: PublicKey;
    escrow: PublicKey;
  }> {
    const client = params.client ?? this.walletPublicKey;
    const [job] = this.findJobPda(client, params.jobId);
    const [escrowAuth] = this.findEscrowAuthPda(job);
    const escrowKeypair = params.escrowKeypair ?? web3.Keypair.generate();

    const signature = await this.methodsApi
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
        escrow: escrowKeypair.publicKey,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
        rent: web3.SYSVAR_RENT_PUBKEY,
      })
      .signers([escrowKeypair])
      .rpc(params.confirmOptions);

    return { signature, job, escrowAuth, escrow: escrowKeypair.publicKey };
  }

  async registerWorker(params: RegisterWorkerParams = {}): Promise<{
    signature: TransactionSignature;
    workerAccount: PublicKey;
  }> {
    const worker = params.worker ?? this.walletPublicKey;
    const [workerAccount] = this.findWorkerPda(worker);

    const signature = await this.methodsApi
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

    const signature = await this.methodsApi
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

    const signature = await this.methodsApi
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

    const signature = await this.methodsApi
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
    const [escrowAuth] = this.findEscrowAuthPda(params.job);

    const [fragmentAccount, jobAccount] = await Promise.all([
      this.accountApi.fragment.fetch(fragment),
      this.accountApi.job.fetch(params.job),
    ]);

    const round = numberFrom(fragmentAccount.round);
    const [vote] = this.findFragmentVotePda(fragment, verifier, round);
    const workerToken = params.workerToken ?? fragmentAccount.workerTokenAccount;

    const signature = await this.methodsApi
      .voteFragment(params.choice)
      .accounts({
        verifier,
        job: params.job,
        fragment,
        verifierWorker,
        vote,
        escrowAuth,
        escrow: jobAccount.escrow,
        workerToken,
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
    const job = await this.accountApi.job.fetch(params.job);

    const signature = await this.methodsApi
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
    const job = await this.accountApi.job.fetch(params.job);

    const signature = await this.methodsApi
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
    const treasuryTokenKeypair = params.treasuryTokenKeypair ?? web3.Keypair.generate();

    const signature = await this.methodsApi
      .initTreasury()
      .accounts({
        payer,
        mint: params.mint,
        treasuryState,
        treasuryAuth,
        treasury: treasuryTokenKeypair.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: web3.SystemProgram.programId,
        rent: web3.SYSVAR_RENT_PUBKEY,
      })
      .signers([treasuryTokenKeypair])
      .rpc(params.confirmOptions);

    return {
      signature,
      treasuryState,
      treasuryAuth,
      treasury: treasuryTokenKeypair.publicKey,
    };
  }

  async slashVote(params: SlashVoteParams): Promise<{
    signature: TransactionSignature;
    fragment: PublicKey;
    vote: PublicKey;
    verifierWorker: PublicKey;
    stakeAuth: PublicKey;
    stakeVault: PublicKey;
    treasuryState: PublicKey;
    treasuryAuth: PublicKey;
    treasury: PublicKey;
  }> {
    const slasher = params.slasher ?? this.walletPublicKey;
    const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);
    const [vote] = this.findFragmentVotePda(fragment, params.verifier, params.round);
    const [verifierWorker] = this.findWorkerPda(params.verifier);
    const [stakeAuth] = this.findStakeAuthPda(verifierWorker);
    const [stakeVault] = this.findStakeVaultPda(params.verifier);

    const job = await this.accountApi.job.fetch(params.job);
    const [treasuryState] = this.findTreasuryStatePda(job.mint);
    const [treasuryAuth] = this.findTreasuryAuthPda(job.mint);
    const treasuryStateAccount = await this.accountApi.treasury.fetch(treasuryState);
    const treasury = treasuryStateAccount.treasuryTokenAccount;

    const signature = await this.methodsApi
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
        treasury,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc(params.confirmOptions);

    return {
      signature,
      fragment,
      vote,
      verifierWorker,
      stakeAuth,
      stakeVault,
      treasuryState,
      treasuryAuth,
      treasury,
    };
  }

  async fetchJob(job: PublicKey): Promise<ParsedJobAccount | null> {
    const account = await this.accountApi.job.fetchNullable(job);
    return account ? parseJob(job, account) : null;
  }

  async fetchJobById(client: PublicKey, jobId: Parameters<typeof bnToLeBuffer>[0]): Promise<ParsedJobAccount | null> {
    const [job] = this.findJobPda(client, jobId);
    return this.fetchJob(job);
  }

  async fetchWorkerByPda(workerAccount: PublicKey): Promise<ParsedWorkerAccount | null> {
    const account = await this.accountApi.worker.fetchNullable(workerAccount);
    return account ? parseWorker(workerAccount, account) : null;
  }

  async fetchWorker(workerWallet: PublicKey): Promise<ParsedWorkerAccount | null> {
    const [worker] = this.findWorkerPda(workerWallet);
    return this.fetchWorkerByPda(worker);
  }

  async fetchFragment(job: PublicKey, fragmentIndex: number): Promise<ParsedFragmentAccount | null> {
    const [fragment] = this.findFragmentPda(job, fragmentIndex);
    const account = await this.accountApi.fragment.fetchNullable(fragment);
    return account ? parseFragment(fragment, account) : null;
  }

  async fetchFragmentVote(fragment: PublicKey, verifier: PublicKey, round: number): Promise<ParsedFragmentVoteAccount | null> {
    const [vote] = this.findFragmentVotePda(fragment, verifier, round);
    const account = await this.accountApi.fragmentVote.fetchNullable(vote);
    return account ? parseFragmentVote(vote, account) : null;
  }

  async fetchJobResult(job: PublicKey): Promise<ParsedJobResultAccount | null> {
    const [result] = this.findResultPda(job);
    const account = await this.accountApi.jobResult.fetchNullable(result);
    return account ? parseJobResult(result, account) : null;
  }

  async fetchTreasuryState(mint: PublicKey): Promise<ParsedTreasuryAccount | null> {
    const [treasuryState] = this.findTreasuryStatePda(mint);
    const account = await this.accountApi.treasury.fetchNullable(treasuryState);
    return account ? parseTreasury(treasuryState, account) : null;
  }

  async listAllJobs(): Promise<ParsedJobAccount[]> {
    const rows = (await this.accountApi.job.all()) as ProgramAccountRow<any>[];
    return rows.map((row) => parseJob(row.publicKey, row.account));
  }

  async listJobsByClient(client: PublicKey): Promise<ParsedJobAccount[]> {
    const rows = (await this.accountApi.job.all([
      {
        memcmp: {
          offset: 8 + 8,
          bytes: client.toBase58(),
        },
      },
    ])) as ProgramAccountRow<any>[];

    return rows.map((row) => parseJob(row.publicKey, row.account));
  }

  async listFragmentsByJob(job: PublicKey): Promise<ParsedFragmentAccount[]> {
    const rows = (await this.accountApi.fragment.all([
      {
        memcmp: {
          offset: 8,
          bytes: job.toBase58(),
        },
      },
    ])) as ProgramAccountRow<any>[];

    return rows.map((row) => parseFragment(row.publicKey, row.account));
  }

  async listFragmentVotesByFragment(fragment: PublicKey): Promise<ParsedFragmentVoteAccount[]> {
    const rows = (await this.accountApi.fragmentVote.all([
      {
        memcmp: {
          offset: 8,
          bytes: fragment.toBase58(),
        },
      },
    ])) as ProgramAccountRow<any>[];

    return rows.map((row) => parseFragmentVote(row.publicKey, row.account));
  }

  async fetchJobAggregate(client: PublicKey, jobId: Parameters<typeof bnToLeBuffer>[0]): Promise<JobAggregate> {
    const [jobPda] = this.findJobPda(client, jobId);
    const [job, fragments, result] = await Promise.all([
      this.fetchJob(jobPda),
      this.listFragmentsByJob(jobPda),
      this.fetchJobResult(jobPda),
    ]);

    if (!job) {
      return { job: null, fragments: [], result: null };
    }

    return { job, fragments, result };
  }
}

export async function buildSiliciumSdk(params: BuildSiliciumSdkParams): Promise<SiliciumSdk> {
  const provider = new AnchorProvider(
    params.connection,
    params.wallet as anchor.Wallet,
    params.opts ?? AnchorProvider.defaultOptions(),
  );

  const program = new Program(params.idl, provider) as Program<SiliciumChain>;

  return SiliciumSdk.fromProgram(program, provider);
}