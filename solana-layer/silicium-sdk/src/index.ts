import * as anchor from "@coral-xyz/anchor";
import {
  PublicKey,
  SystemProgram,
  SYSVAR_RENT_PUBKEY,
  Signer,
  TransactionSignature,
} from "@solana/web3.js";
import { TOKEN_PROGRAM_ID } from "@solana/spl-token";

import { SiliciumEventClient } from "./events";
import {
  escrowAuthPda,
  fragmentPda,
  jobPda,
  resultPda,
  roundResolutionPda,
  stakeAuthPda,
  stakeVaultPda,
  toBn,
  treasuryAuthPda,
  treasuryStatePda,
  votePda,
  workerPda,
} from "./pdas";
import type {
  CancelJobParams,
  ClaimFragmentParams,
  ClaimVerifierRewardParams,
  CreateJobParams,
  CreateSdkParams,
  FinalizeJobParams,
  Hash32,
  IdlProgram,
  InitTreasuryParams,
  ReclaimFragmentParams,
  RegisterWorkerParams,
  SlashVoteParams,
  StakeWorkerParams,
  SubmitFragmentResultParams,
  VoteFragmentParams,
} from "./types";

export * from "./pdas";
export * from "./events";
export * from "./types";

export const SOLANA_LAYER_PROGRAM_ID = new PublicKey("Ezt3UKgn7o1uoFmnG2zhKXW9NoygJMwJ3FErNUczy9jj");

function asHash32(value: Hash32): number[] {
  const arr = Array.from(value);
  if (arr.length !== 32) {
    throw new Error(`Expected a 32-byte array, got ${arr.length} bytes`);
  }
  return arr;
}

function asBytes(value: string | Uint8Array | Buffer): Buffer {
  return typeof value === "string" ? Buffer.from(value) : Buffer.from(value);
}

export class SiliciumLayerSdk {
  readonly provider: anchor.AnchorProvider;
  readonly program: IdlProgram;
  readonly programId: PublicKey;
  readonly events: SiliciumEventClient;

  constructor(params: CreateSdkParams) {
    this.provider = params.provider;
    this.program = params.program;
    this.programId = params.program.programId;
    this.events = new SiliciumEventClient(params.program);
  }

  static fromWorkspace(provider: anchor.AnchorProvider, program: IdlProgram): SiliciumLayerSdk {
    return new SiliciumLayerSdk({ provider, program });
  }

  walletPubkey(): PublicKey {
    return this.provider.wallet.publicKey;
  }

  pdas = {
    job: (client: PublicKey, jobId: anchor.BN | number | bigint | string) => jobPda(this.programId, client, jobId),
    fragment: (job: PublicKey, fragmentIndex: number) => fragmentPda(this.programId, job, fragmentIndex),
    worker: (worker: PublicKey) => workerPda(this.programId, worker),
    escrowAuth: (job: PublicKey) => escrowAuthPda(this.programId, job),
    stakeAuth: (workerAccount: PublicKey) => stakeAuthPda(this.programId, workerAccount),
    stakeVault: (worker: PublicKey) => stakeVaultPda(this.programId, worker),
    vote: (fragment: PublicKey, verifier: PublicKey, round: number) => votePda(this.programId, fragment, verifier, round),
    roundResolution: (fragment: PublicKey, round: number) => roundResolutionPda(this.programId, fragment, round),
    result: (job: PublicKey) => resultPda(this.programId, job),
    treasuryState: (mint: PublicKey) => treasuryStatePda(this.programId, mint),
    treasuryAuth: (mint: PublicKey) => treasuryAuthPda(this.programId, mint),
  };

  async registerWorker(params: RegisterWorkerParams = {}): Promise<TransactionSignature> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);

    const builder = this.program.methods
      .registerWorker()
      .accounts({
        worker,
        workerAccount,
        systemProgram: SystemProgram.programId,
      });

    if (params.signers?.length) builder.signers(params.signers);
    return builder.rpc();
  }

  async stakeWorker(params: StakeWorkerParams): Promise<TransactionSignature> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);
    const stakeAuth = this.pdas.stakeAuth(workerAccount);
    const stakeVault = this.pdas.stakeVault(worker);

    const builder = this.program.methods
      .stakeWorker(toBn(params.amount))
      .accounts({
        worker,
        workerAccount,
        mint: params.mint,
        workerToken: params.workerToken,
        stakeAuth,
        stakeVault,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      });

    if (params.signers?.length) builder.signers(params.signers);
    return builder.rpc();
  }

  async createJob(params: CreateJobParams): Promise<{ signature: TransactionSignature; job: PublicKey; escrowAuth: PublicKey }> {
    const client = params.client ?? this.walletPubkey();
    const job = this.pdas.job(client, params.jobId);
    const escrowAuth = this.pdas.escrowAuth(job);

    const builder = this.program.methods
      .createJob(
        toBn(params.jobId),
        params.expectedFragments,
        toBn(params.rewardPerFragment),
        toBn(params.verifierRewardPerVote),
        toBn(params.verifierRewardBudget),
        toBn(params.deadlineUnix),
        params.fragmentQuorum,
      )
      .accounts({
        client,
        mint: params.mint,
        job,
        escrowAuth,
        escrow: params.escrow.publicKey,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([params.escrow]);

    const signature = await builder.rpc();
    return { signature, job, escrowAuth };
  }

  async claimFragment(params: ClaimFragmentParams): Promise<{ signature: TransactionSignature; fragment: PublicKey }> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);
    const fragment = this.pdas.fragment(params.job, params.fragmentIndex);

    const builder = this.program.methods
      .claimFragment(params.fragmentIndex)
      .accounts({
        worker,
        workerAccount,
        job: params.job,
        fragment,
        workerToken: params.workerToken,
        systemProgram: SystemProgram.programId,
      });

    if (params.signers?.length) builder.signers(params.signers);
    const signature = await builder.rpc();
    return { signature, fragment };
  }

  async reclaimFragment(params: ReclaimFragmentParams): Promise<{ signature: TransactionSignature; fragment: PublicKey }> {
    const caller = params.caller ?? this.walletPubkey();
    const fragment = this.pdas.fragment(params.job, params.fragmentIndex);

    const signature = await this.program.methods
      .reclaimFragment(params.fragmentIndex)
      .accounts({
        caller,
        job: params.job,
        fragment,
      })
      .rpc();

    return { signature, fragment };
  }

  async submitFragmentResult(params: SubmitFragmentResultParams): Promise<TransactionSignature> {
    return this.sendSubmitLike("submitFragmentResult", params);
  }

  async resubmitFragmentResult(params: SubmitFragmentResultParams): Promise<TransactionSignature> {
    return this.sendSubmitLike("resubmitFragmentResult", params);
  }

  private async sendSubmitLike(method: "submitFragmentResult" | "resubmitFragmentResult", params: SubmitFragmentResultParams): Promise<TransactionSignature> {
    const worker = params.worker ?? this.walletPubkey();
    const workerAccount = this.pdas.worker(worker);
    const fragment = this.pdas.fragment(params.job, params.fragmentIndex);

    const builder = this.program.methods[method](
      params.fragmentIndex,
      asHash32(params.resultHash),
      asHash32(params.proofRef),
    ).accounts({
      worker,
      workerAccount,
      job: params.job,
      fragment,
      workerToken: params.workerToken,
    });

    if (params.signers?.length) builder.signers(params.signers);
    return builder.rpc();
  }

  async voteFragment(params: VoteFragmentParams): Promise<{ signature: TransactionSignature; vote: PublicKey; roundResolution: PublicKey }> {
    const verifier = params.verifier ?? this.walletPubkey();
    const verifierWorker = this.pdas.worker(verifier);
    const fragmentAccount = params.round === undefined
      ? await this.program.account.fragment.fetch(params.fragment)
      : undefined;
    const round = params.round ?? Number(fragmentAccount.round);
    const vote = this.pdas.vote(params.fragment, verifier, round);
    const roundResolution = this.pdas.roundResolution(params.fragment, round);
    const escrowAuth = this.pdas.escrowAuth(params.job);

    const builder = this.program.methods
      .voteFragment(params.choice)
      .accounts({
        verifier,
        job: params.job,
        fragment: params.fragment,
        verifierWorker,
        vote,
        roundResolution,
        escrowAuth,
        escrow: params.escrow,
        workerToken: params.workerToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      });

    if (params.signers?.length) builder.signers(params.signers);
    const signature = await builder.rpc();
    return { signature, vote, roundResolution };
  }

  async claimVerifierReward(params: ClaimVerifierRewardParams): Promise<TransactionSignature> {
    const verifier = params.verifier ?? this.walletPubkey();
    const verifierWorker = this.pdas.worker(verifier);
    const fragmentAccount = params.round === undefined
      ? await this.program.account.fragment.fetch(params.fragment)
      : undefined;
    const round = params.round ?? Number(fragmentAccount.round);
    const vote = this.pdas.vote(params.fragment, verifier, round);
    const roundResolution = this.pdas.roundResolution(params.fragment, round);
    const escrowAuth = this.pdas.escrowAuth(params.job);

    const builder = this.program.methods
      .claimVerifierReward()
      .accounts({
        verifier,
        job: params.job,
        fragment: params.fragment,
        roundResolution,
        vote,
        verifierWorker,
        escrowAuth,
        escrow: params.escrow,
        verifierToken: params.verifierToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      });

    if (params.signers?.length) builder.signers(params.signers);
    return builder.rpc();
  }

  async finalizeJob(params: FinalizeJobParams): Promise<{ signature: TransactionSignature; result: PublicKey }> {
    const client = params.client ?? this.walletPubkey();
    const result = this.pdas.result(params.job);
    const escrowAuth = this.pdas.escrowAuth(params.job);

    const signature = await this.program.methods
      .finalizeJob(asHash32(params.finalHash), asBytes(params.outputUri))
      .accounts({
        client,
        job: params.job,
        result,
        escrowAuth,
        escrow: params.escrow,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    return { signature, result };
  }

  async cancelJob(params: CancelJobParams): Promise<TransactionSignature> {
    const client = params.client ?? this.walletPubkey();
    const escrowAuth = this.pdas.escrowAuth(params.job);

    return this.program.methods
      .cancelJob()
      .accounts({
        client,
        job: params.job,
        escrowAuth,
        escrow: params.escrow,
        clientToken: params.clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();
  }

  async initTreasury(params: InitTreasuryParams): Promise<{ signature: TransactionSignature; treasuryState: PublicKey; treasuryAuth: PublicKey }> {
    const payer = params.payer ?? this.walletPubkey();
    const treasuryState = this.pdas.treasuryState(params.mint);
    const treasuryAuth = this.pdas.treasuryAuth(params.mint);

    const signature = await this.program.methods
      .initTreasury()
      .accounts({
        payer,
        mint: params.mint,
        treasuryState,
        treasuryAuth,
        treasury: params.treasury.publicKey,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([params.treasury])
      .rpc();

    return { signature, treasuryState, treasuryAuth };
  }

  async slashVote(params: SlashVoteParams): Promise<TransactionSignature> {
    const slasher = params.slasher ?? this.walletPubkey();
    const verifierWorker = this.pdas.worker(params.verifier);
    const stakeAuth = this.pdas.stakeAuth(verifierWorker);
    const stakeVault = this.pdas.stakeVault(params.verifier);
    const treasuryState = this.pdas.treasuryState(params.mint);
    const treasuryAuth = this.pdas.treasuryAuth(params.mint);

    return this.program.methods
      .slashVote()
      .accounts({
        slasher,
        job: params.job,
        fragment: params.fragment,
        vote: params.vote,
        verifierWorker,
        treasuryState,
        stakeAuth,
        stakeVault,
        treasuryAuth,
        treasury: params.treasury,
        tokenProgram: TOKEN_PROGRAM_ID,
      })
      .rpc();
  }

  async fetchJob(job: PublicKey): Promise<unknown> {
    return this.program.account.job.fetch(job);
  }

  async fetchFragment(fragment: PublicKey): Promise<unknown> {
    return this.program.account.fragment.fetch(fragment);
  }

  async fetchWorker(workerOrWorkerAccount: PublicKey, isWorkerAccount = false): Promise<unknown> {
    const account = isWorkerAccount ? workerOrWorkerAccount : this.pdas.worker(workerOrWorkerAccount);
    return this.program.account.worker.fetch(account);
  }

  async fetchVote(vote: PublicKey): Promise<unknown> {
    return this.program.account.fragmentVote.fetch(vote);
  }

  async fetchRoundResolution(roundResolution: PublicKey): Promise<unknown> {
    return this.program.account.fragmentResolution.fetch(roundResolution);
  }

  async fetchResult(result: PublicKey): Promise<unknown> {
    return this.program.account.jobResult.fetch(result);
  }
}
