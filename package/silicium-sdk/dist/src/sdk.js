import { AnchorProvider, Program, web3 } from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { TOKEN_PROGRAM_ID } from "@solana/spl-token";
import { SEEDS } from "./constants";
import { parseFragment, parseFragmentVote, parseJob, parseJobResult, parseTreasury, parseWorker, } from "./parsers";
import { bnToLeBuffer, bufferFromString, normalize32, normalizeBytes, numberFrom, toBN, u16ToLeBuffer, u32ToLeBuffer, } from "./utils";
export class SiliciumSdk {
    constructor(options) {
        this.provider = options.provider;
        this.program = options.program;
        this.connection = options.provider.connection;
        this.programId = options.programId;
        this.commitment = options.commitment ?? "confirmed";
    }
    static fromProgram(program, provider) {
        const resolvedProvider = provider ?? program.provider;
        return new SiliciumSdk({
            provider: resolvedProvider,
            program,
            programId: program.programId,
        });
    }
    get walletPublicKey() {
        const key = this.provider.wallet?.publicKey;
        if (!key) {
            throw new Error("Provider wallet is missing.");
        }
        return key;
    }
    // ---------------------------------------------------------------------------
    // PDA HELPERS
    // ---------------------------------------------------------------------------
    findJobPda(client, jobId) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.job), client.toBuffer(), bnToLeBuffer(jobId, 8)], this.programId);
    }
    findEscrowAuthPda(job) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.escrowAuth), job.toBuffer()], this.programId);
    }
    findResultPda(job) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.result), job.toBuffer()], this.programId);
    }
    findWorkerPda(workerWallet) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.worker), workerWallet.toBuffer()], this.programId);
    }
    findFragmentPda(job, fragmentIndex) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.fragment), job.toBuffer(), u32ToLeBuffer(fragmentIndex)], this.programId);
    }
    findFragmentVotePda(fragment, verifier, round) {
        return PublicKey.findProgramAddressSync([
            bufferFromString(SEEDS.fragmentVote),
            fragment.toBuffer(),
            verifier.toBuffer(),
            u16ToLeBuffer(round),
        ], this.programId);
    }
    findStakeAuthPda(workerAccount) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.stakeAuth), workerAccount.toBuffer()], this.programId);
    }
    findStakeVaultPda(workerWallet) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.stakeVault), workerWallet.toBuffer()], this.programId);
    }
    findTreasuryStatePda(mint) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.treasuryState), mint.toBuffer()], this.programId);
    }
    findTreasuryAuthPda(mint) {
        return PublicKey.findProgramAddressSync([bufferFromString(SEEDS.treasuryAuth), mint.toBuffer()], this.programId);
    }
    // ---------------------------------------------------------------------------
    // WRITE METHODS
    // ---------------------------------------------------------------------------
    async createJob(params) {
        const client = params.client ?? this.walletPublicKey;
        const [job] = this.findJobPda(client, params.jobId);
        const [escrowAuth] = this.findEscrowAuthPda(job);
        const escrowKeypair = params.escrowKeypair ?? web3.Keypair.generate();
        const signature = await this.program.methods
            .createJob(toBN(params.jobId), params.expectedFragments, toBN(params.rewardPerFragment), toBN(params.deadlineUnix), params.fragmentQuorum)
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
        return {
            signature,
            job,
            escrowAuth,
            escrow: escrowKeypair.publicKey,
        };
    }
    async registerWorker(params = {}) {
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
    async stakeWorker(params) {
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
    async submitFragment(params) {
        const worker = params.worker ?? this.walletPublicKey;
        const [workerAccount] = this.findWorkerPda(worker);
        const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);
        const signature = await this.program.methods
            .submitFragmentResult(params.fragmentIndex, normalize32(params.resultHash), normalize32(params.proofRef))
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
    async resubmitFragment(params) {
        const worker = params.worker ?? this.walletPublicKey;
        const [workerAccount] = this.findWorkerPda(worker);
        const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);
        const signature = await this.program.methods
            .resubmitFragmentResult(params.fragmentIndex, normalize32(params.resultHash), normalize32(params.proofRef))
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
    async voteFragment(params) {
        const verifier = params.verifier ?? this.walletPublicKey;
        const [verifierWorker] = this.findWorkerPda(verifier);
        const [fragment] = this.findFragmentPda(params.job, params.fragmentIndex);
        const [escrowAuth] = this.findEscrowAuthPda(params.job);
        const [fragmentAccount, jobAccount] = await Promise.all([
            this.program.account.fragment.fetch(fragment),
            this.program.account.job.fetch(params.job),
        ]);
        const round = numberFrom(fragmentAccount.round);
        const [vote] = this.findFragmentVotePda(fragment, verifier, round);
        const workerToken = params.workerToken ?? fragmentAccount.workerTokenAccount;
        const signature = await this.program.methods
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
    async finalizeJob(params) {
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
    async cancelJob(params) {
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
    async initTreasury(params) {
        const payer = params.payer ?? this.walletPublicKey;
        const [treasuryState] = this.findTreasuryStatePda(params.mint);
        const [treasuryAuth] = this.findTreasuryAuthPda(params.mint);
        const treasuryTokenKeypair = params.treasuryTokenKeypair ?? web3.Keypair.generate();
        const signature = await this.program.methods
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
    async slashVote(params) {
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
        const treasury = treasuryStateAccount.treasuryTokenAccount;
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
    // ---------------------------------------------------------------------------
    // READ HELPERS
    // ---------------------------------------------------------------------------
    async fetchJob(job) {
        const account = await this.program.account.job.fetchNullable(job);
        return account ? parseJob(job, account) : null;
    }
    async fetchJobById(client, jobId) {
        const [job] = this.findJobPda(client, jobId);
        return this.fetchJob(job);
    }
    async fetchWorkerByPda(workerAccount) {
        const account = await this.program.account.worker.fetchNullable(workerAccount);
        return account ? parseWorker(workerAccount, account) : null;
    }
    async fetchWorker(workerWallet) {
        const [worker] = this.findWorkerPda(workerWallet);
        return this.fetchWorkerByPda(worker);
    }
    async fetchFragment(job, fragmentIndex) {
        const [fragment] = this.findFragmentPda(job, fragmentIndex);
        const account = await this.program.account.fragment.fetchNullable(fragment);
        return account ? parseFragment(fragment, account) : null;
    }
    async fetchFragmentVote(fragment, verifier, round) {
        const [vote] = this.findFragmentVotePda(fragment, verifier, round);
        const account = await this.program.account.fragmentVote.fetchNullable(vote);
        return account ? parseFragmentVote(vote, account) : null;
    }
    async fetchJobResult(job) {
        const [result] = this.findResultPda(job);
        const account = await this.program.account.jobResult.fetchNullable(result);
        return account ? parseJobResult(result, account) : null;
    }
    async fetchTreasuryState(mint) {
        const [treasuryState] = this.findTreasuryStatePda(mint);
        const account = await this.program.account.treasury.fetchNullable(treasuryState);
        return account ? parseTreasury(treasuryState, account) : null;
    }
    async listAllJobs() {
        const rows = (await this.program.account.job.all());
        return rows.map((row) => parseJob(row.publicKey, row.account));
    }
    async listJobsByClient(client) {
        const rows = (await this.program.account.job.all([
            {
                memcmp: {
                    offset: 8 + 8,
                    bytes: client.toBase58(),
                },
            },
        ]));
        return rows.map((row) => parseJob(row.publicKey, row.account));
    }
    async listFragmentsByJob(job) {
        const rows = (await this.program.account.fragment.all([
            {
                memcmp: {
                    offset: 8,
                    bytes: job.toBase58(),
                },
            },
        ]));
        return rows.map((row) => parseFragment(row.publicKey, row.account));
    }
    async listFragmentVotesByFragment(fragment) {
        const rows = (await this.program.account.fragmentVote.all([
            {
                memcmp: {
                    offset: 8,
                    bytes: fragment.toBase58(),
                },
            },
        ]));
        return rows.map((row) => parseFragmentVote(row.publicKey, row.account));
    }
    async fetchJobAggregate(client, jobId) {
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
export async function buildSiliciumSdk(params) {
    const provider = new AnchorProvider(params.connection, params.wallet, params.opts ?? AnchorProvider.defaultOptions());
    const program = new Program(params.idl, params.programId, provider);
    return SiliciumSdk.fromProgram(program, provider);
}
