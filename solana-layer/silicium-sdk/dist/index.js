"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.SiliciumLayerSdk = exports.DEVNET_FRAGMENT_QUORUM = exports.SIL_BASE_UNITS = exports.SIL_DECIMALS = exports.SOLANA_LAYER_LOCALNET_RPC_URL = exports.SOLANA_LAYER_DEVNET_RPC_URL = exports.SOLANA_LAYER_PROGRAM_ID = exports.SOLANA_LAYER_LOCALNET_PROGRAM_ID = exports.SOLANA_LAYER_DEVNET_PROGRAM_ID = void 0;
exports.quoteDevnetSilFragments = quoteDevnetSilFragments;
exports.getSolanaLayerProgramId = getSolanaLayerProgramId;
exports.getSolanaLayerRpcUrl = getSolanaLayerRpcUrl;
exports.createSolanaLayerConnection = createSolanaLayerConnection;
const anchor = __importStar(require("@coral-xyz/anchor"));
const web3_js_1 = require("@solana/web3.js");
const spl_token_1 = require("@solana/spl-token");
const buffer_1 = require("buffer");
const events_1 = require("./events");
const pdas_1 = require("./pdas");
__exportStar(require("./pdas"), exports);
__exportStar(require("./events"), exports);
__exportStar(require("./types"), exports);
exports.SOLANA_LAYER_DEVNET_PROGRAM_ID = new web3_js_1.PublicKey("A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2");
exports.SOLANA_LAYER_LOCALNET_PROGRAM_ID = new web3_js_1.PublicKey("A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2");
exports.SOLANA_LAYER_PROGRAM_ID = exports.SOLANA_LAYER_DEVNET_PROGRAM_ID;
exports.SOLANA_LAYER_DEVNET_RPC_URL = "https://api.devnet.solana.com";
exports.SOLANA_LAYER_LOCALNET_RPC_URL = "http://127.0.0.1:8899";
/** Devnet SIL mint denomination: one SIL is 10^6 SPL base units. */
exports.SIL_DECIMALS = 6;
exports.SIL_BASE_UNITS = 1000000n;
exports.DEVNET_FRAGMENT_QUORUM = 2;
/** The selected test quote: 1 SIL compute + 1 SIL per accepted verifier. */
function quoteDevnetSilFragments(expectedFragments) {
    if (!Number.isSafeInteger(expectedFragments) || expectedFragments < 1 || expectedFragments > 1000) {
        throw new Error("expectedFragments must be an integer from 1 through 1000");
    }
    const count = BigInt(expectedFragments);
    const rewardPerFragment = exports.SIL_BASE_UNITS;
    const verifierRewardPerVote = exports.SIL_BASE_UNITS;
    const verifierRewardBudget = count * BigInt(exports.DEVNET_FRAGMENT_QUORUM) * verifierRewardPerVote;
    return {
        rewardPerFragment,
        verifierRewardPerVote,
        verifierRewardBudget,
        fragmentQuorum: exports.DEVNET_FRAGMENT_QUORUM,
        totalEscrow: count * (rewardPerFragment + BigInt(exports.DEVNET_FRAGMENT_QUORUM) * verifierRewardPerVote),
    };
}
function getSolanaLayerProgramId(cluster = "devnet") {
    return cluster === "localnet" ? exports.SOLANA_LAYER_LOCALNET_PROGRAM_ID : exports.SOLANA_LAYER_DEVNET_PROGRAM_ID;
}
function getSolanaLayerRpcUrl(cluster = "devnet") {
    return cluster === "localnet" ? exports.SOLANA_LAYER_LOCALNET_RPC_URL : exports.SOLANA_LAYER_DEVNET_RPC_URL;
}
function createSolanaLayerConnection(cluster = "devnet", commitment = "confirmed") {
    return new web3_js_1.Connection(getSolanaLayerRpcUrl(cluster), commitment);
}
function asHash32(value) {
    const arr = Array.from(value);
    if (arr.length !== 32) {
        throw new Error(`Expected a 32-byte array, got ${arr.length} bytes`);
    }
    return arr;
}
function asBytes(value) {
    return typeof value === "string" ? buffer_1.Buffer.from(value) : buffer_1.Buffer.from(value);
}
function appendSigners(builder, signers) {
    return signers?.length ? builder.signers(signers) : builder;
}
class SiliciumLayerSdk {
    constructor(params) {
        this.pdas = {
            job: (client, jobId) => (0, pdas_1.jobPda)(this.programId, client, jobId),
            jobStorage: (job) => (0, pdas_1.jobStoragePda)(this.programId, job),
            fragment: (job, fragmentIndex) => (0, pdas_1.fragmentPda)(this.programId, job, fragmentIndex),
            worker: (worker) => (0, pdas_1.workerPda)(this.programId, worker),
            workerPayout: (workerAccount) => (0, pdas_1.workerPayoutPda)(this.programId, workerAccount),
            escrowAuth: (job) => (0, pdas_1.escrowAuthPda)(this.programId, job),
            stakeAuth: (workerAccount) => (0, pdas_1.stakeAuthPda)(this.programId, workerAccount),
            stakeVault: (worker) => (0, pdas_1.stakeVaultPda)(this.programId, worker),
            vote: (fragment, verifier, round) => (0, pdas_1.votePda)(this.programId, fragment, verifier, round),
            roundResolution: (fragment, round) => (0, pdas_1.roundResolutionPda)(this.programId, fragment, round),
            splitProposal: (parentFragment, round) => (0, pdas_1.splitProposalPda)(this.programId, parentFragment, round),
            result: (job) => (0, pdas_1.resultPda)(this.programId, job),
            treasuryState: (mint) => (0, pdas_1.treasuryStatePda)(this.programId, mint),
            treasuryAuth: (mint) => (0, pdas_1.treasuryAuthPda)(this.programId, mint),
            stakingPool: (mint) => (0, pdas_1.stakingPoolPda)(this.programId, mint),
            stakingPoolAuth: (mint) => (0, pdas_1.stakingPoolAuthPda)(this.programId, mint),
            networkStaker: (owner, mint) => (0, pdas_1.networkStakerPda)(this.programId, owner, mint),
        };
        this.provider = params.provider;
        this.program = params.program;
        this.programId = params.program.programId;
        this.events = new events_1.SiliciumEventClient(params.program);
    }
    static fromWorkspace(provider, program) {
        return new SiliciumLayerSdk({ provider, program });
    }
    walletPubkey() {
        return this.provider.wallet.publicKey;
    }
    get methods() {
        return this.program.methods;
    }
    get accounts() {
        return this.program.account;
    }
    async registerWorker(params = {}) {
        const worker = params.worker ?? this.walletPubkey();
        const workerAccount = this.pdas.worker(worker);
        const workerPayout = this.pdas.workerPayout(workerAccount);
        let builder = this.methods
            .registerWorker()
            .accounts({
            worker,
            workerAccount,
            workerPayout,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async registerWorkerPayout(params) {
        const payoutWallet = params.payoutWallet ?? this.walletPubkey();
        const workerAccount = this.pdas.worker(params.worker);
        if (!payoutWallet.equals(this.walletPubkey())) {
            throw new Error("The connected wallet must be the payout wallet signer.");
        }
        const selfPayout = payoutWallet.equals(params.worker);
        const proofSignature = params.workerProofSignature;
        if (!selfPayout && (!proofSignature || !params.pairingCode || !params.nodeId || !params.peerId)) {
            throw new Error("A linked worker requires its signed account-pairing proof.");
        }
        const register = await this.methods
            .registerWorkerPayout(params.pairingCode ?? "", params.nodeId ?? "", params.peerId ?? "")
            .accounts({
            payoutWallet,
            worker: params.worker,
            workerAccount,
            workerPayout: this.pdas.workerPayout(workerAccount),
            previousPayoutWallet: params.worker,
            instructions: web3_js_1.SYSVAR_INSTRUCTIONS_PUBKEY,
            systemProgram: web3_js_1.SystemProgram.programId,
        })
            .instruction();
        const transaction = new anchor.web3.Transaction();
        if (!selfPayout && proofSignature) {
            const message = new TextEncoder().encode(`silicium-device-payout-v1\n${params.pairingCode}\n${params.nodeId}\n${params.peerId}\n${params.worker.toBase58()}\n${payoutWallet.toBase58()}`);
            transaction.add(web3_js_1.Ed25519Program.createInstructionWithPublicKey({
                publicKey: buffer_1.Buffer.from(params.worker.toBytes()),
                message: buffer_1.Buffer.from(message),
                signature: buffer_1.Buffer.from(proofSignature),
            }));
        }
        transaction.add(register);
        return this.provider.sendAndConfirm(transaction, []);
    }
    async stakeWorker(params) {
        const worker = params.worker ?? this.walletPubkey();
        const workerAccount = this.pdas.worker(worker);
        const stakeAuth = this.pdas.stakeAuth(workerAccount);
        const stakeVault = this.pdas.stakeVault(worker);
        let builder = this.methods
            .stakeWorker((0, pdas_1.toBn)(params.amount))
            .accounts({
            worker,
            workerAccount,
            mint: params.mint,
            workerToken: params.workerToken,
            stakeAuth,
            stakeVault,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
            rent: web3_js_1.SYSVAR_RENT_PUBKEY,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async createJob(params) {
        const client = params.client ?? this.walletPubkey();
        const job = this.pdas.job(client, params.jobId);
        const escrowAuth = this.pdas.escrowAuth(job);
        const builder = this.methods
            .createJob((0, pdas_1.toBn)(params.jobId), params.expectedFragments, (0, pdas_1.toBn)(params.rewardPerFragment), (0, pdas_1.toBn)(params.verifierRewardPerVote), (0, pdas_1.toBn)(params.verifierRewardBudget), (0, pdas_1.toBn)(params.deadlineUnix), params.fragmentQuorum)
            .accounts({
            client,
            mint: params.mint,
            job,
            escrowAuth,
            escrow: params.escrow.publicKey,
            clientToken: params.clientToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
            rent: web3_js_1.SYSVAR_RENT_PUBKEY,
        })
            .signers([params.escrow]);
        const signature = await builder.rpc();
        return { signature, job, escrowAuth };
    }
    async declareJobStorage(params) {
        const client = params.client ?? this.walletPubkey();
        const jobStorage = this.pdas.jobStorage(params.job);
        const encryptionRefHash = params.encryptionRefHash ?? new Uint8Array(32);
        let builder = this.methods
            .declareJobStorage(asHash32(params.manifestHash), asHash32(params.inputRootHash), asHash32(params.storageRefHash), asHash32(encryptionRefHash))
            .accounts({
            client,
            job: params.job,
            jobStorage,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, jobStorage };
    }
    async claimFragment(params) {
        const worker = params.worker ?? this.walletPubkey();
        const workerAccount = this.pdas.worker(worker);
        const fragment = this.pdas.fragment(params.job, params.fragmentIndex);
        let builder = this.methods
            .claimFragment(params.fragmentIndex)
            .accounts({
            worker,
            workerAccount,
            job: params.job,
            fragment,
            workerToken: params.workerToken,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, fragment };
    }
    async reclaimFragment(params) {
        const caller = params.caller ?? this.walletPubkey();
        const fragment = this.pdas.fragment(params.job, params.fragmentIndex);
        let builder = this.methods
            .reclaimFragment(params.fragmentIndex)
            .accounts({ caller, job: params.job, fragment });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, fragment };
    }
    async resolveParentFragmentAndRound(params) {
        const parentFragment = params.parentFragment ?? this.pdas.fragment(params.job, params.parentFragmentIndex);
        if (params.round !== undefined) {
            return { parentFragment, round: params.round };
        }
        const parentAccount = await this.accounts.fragment.fetch(parentFragment);
        return { parentFragment, round: Number(parentAccount.round) };
    }
    async proposeFragmentSplit(params) {
        const splitter = params.splitter ?? this.walletPubkey();
        const splitterWorker = this.pdas.worker(splitter);
        const { parentFragment, round } = await this.resolveParentFragmentAndRound(params);
        const splitProposal = this.pdas.splitProposal(parentFragment, round);
        let builder = this.methods
            .proposeFragmentSplit(asHash32(params.manifestHash), params.childCount)
            .accounts({
            splitter,
            splitterWorker,
            job: params.job,
            parentFragment,
            splitProposal,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, parentFragment, splitProposal };
    }
    async approveFragmentSplit(params) {
        const authority = params.authority ?? this.walletPubkey();
        const { parentFragment, round } = await this.resolveParentFragmentAndRound(params);
        const splitProposal = params.splitProposal ?? this.pdas.splitProposal(parentFragment, round);
        let builder = this.methods
            .approveFragmentSplit(params.approve)
            .accounts({
            authority,
            job: params.job,
            parentFragment,
            splitProposal,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, parentFragment, splitProposal };
    }
    async createSubFragment(params) {
        const payer = params.payer ?? this.walletPubkey();
        const { parentFragment, round } = await this.resolveParentFragmentAndRound(params);
        const splitProposal = params.splitProposal ?? this.pdas.splitProposal(parentFragment, round);
        const childFragment = this.pdas.fragment(params.job, params.childFragmentIndex);
        let builder = this.methods
            .createSubFragment(params.childFragmentIndex, (0, pdas_1.toBn)(params.requiredComputeReputation), (0, pdas_1.toBn)(params.requiredStake), params.complexityScore, asHash32(params.inputHash))
            .accounts({
            payer,
            job: params.job,
            parentFragment,
            splitProposal,
            childFragment,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, parentFragment, childFragment, splitProposal };
    }
    async submitFragmentResult(params) {
        return this.sendSubmitLike("submitFragmentResult", params);
    }
    async resubmitFragmentResult(params) {
        return this.sendSubmitLike("resubmitFragmentResult", params);
    }
    async sendSubmitLike(method, params) {
        const worker = params.worker ?? this.walletPubkey();
        const workerAccount = this.pdas.worker(worker);
        const fragment = this.pdas.fragment(params.job, params.fragmentIndex);
        let builder = this.methods[method](params.fragmentIndex, asHash32(params.resultHash), asHash32(params.proofRef)).accounts({
            worker,
            workerAccount,
            job: params.job,
            fragment,
            workerToken: params.workerToken,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async voteFragment(params) {
        const verifier = params.verifier ?? this.walletPubkey();
        const verifierWorker = this.pdas.worker(verifier);
        const fragmentAccount = await this.accounts.fragment.fetch(params.fragment);
        const round = params.round ?? Number(fragmentAccount.round);
        const computeWorkerOwner = params.computeWorker ?? fragmentAccount.worker;
        const computeWorker = this.pdas.worker(computeWorkerOwner);
        const vote = this.pdas.vote(params.fragment, verifier, round);
        const roundResolution = this.pdas.roundResolution(params.fragment, round);
        const escrowAuth = this.pdas.escrowAuth(params.job);
        const workerPayout = this.pdas.workerPayout(computeWorker);
        const payoutRecord = await this.accounts.workerPayout.fetchNullable(workerPayout);
        if (!payoutRecord)
            throw new Error("Compute worker payout is not registered on-chain.");
        const jobAccount = await this.accounts.job.fetch(params.job);
        const workerPayoutToken = params.workerPayoutToken
            ?? (0, spl_token_1.getAssociatedTokenAddressSync)(jobAccount.mint, payoutRecord.payoutWallet);
        let builder = this.methods
            .voteFragment(params.choice)
            .accounts({
            verifier,
            job: params.job,
            fragment: params.fragment,
            verifierWorker,
            computeWorker,
            vote,
            roundResolution,
            escrowAuth,
            escrow: params.escrow,
            workerToken: params.workerToken,
            workerPayout,
            workerPayoutToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, vote, roundResolution };
    }
    async claimVerifierReward(params) {
        const verifier = params.verifier ?? this.walletPubkey();
        const verifierWorker = this.pdas.worker(verifier);
        const fragmentAccount = params.round === undefined
            ? await this.accounts.fragment.fetch(params.fragment)
            : undefined;
        const round = params.round ?? Number(fragmentAccount.round);
        const vote = this.pdas.vote(params.fragment, verifier, round);
        const roundResolution = this.pdas.roundResolution(params.fragment, round);
        const escrowAuth = this.pdas.escrowAuth(params.job);
        const workerPayout = this.pdas.workerPayout(verifierWorker);
        const payoutRecord = await this.accounts.workerPayout.fetchNullable(workerPayout);
        if (!payoutRecord)
            throw new Error("Verifier payout is not registered on-chain.");
        const jobAccount = await this.accounts.job.fetch(params.job);
        const verifierPayoutToken = params.verifierPayoutToken
            ?? (0, spl_token_1.getAssociatedTokenAddressSync)(jobAccount.mint, payoutRecord.payoutWallet);
        let builder = this.methods
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
            verifierPayout: workerPayout,
            verifierPayoutToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async finalizeJob(params) {
        const client = params.client ?? this.walletPubkey();
        const result = this.pdas.result(params.job);
        const escrowAuth = this.pdas.escrowAuth(params.job);
        const signature = await this.methods
            .finalizeJob(asHash32(params.finalHash), asBytes(params.outputUri))
            .accounts({
            client,
            job: params.job,
            result,
            escrowAuth,
            escrow: params.escrow,
            clientToken: params.clientToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
        })
            .rpc();
        return { signature, result };
    }
    async cancelJob(params) {
        const client = params.client ?? this.walletPubkey();
        const escrowAuth = this.pdas.escrowAuth(params.job);
        return this.methods
            .cancelJob()
            .accounts({
            client,
            job: params.job,
            escrowAuth,
            escrow: params.escrow,
            clientToken: params.clientToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
        })
            .rpc();
    }
    async initTreasury(params) {
        const payer = params.payer ?? this.walletPubkey();
        const treasuryState = this.pdas.treasuryState(params.mint);
        const treasuryAuth = this.pdas.treasuryAuth(params.mint);
        const signature = await this.methods
            .initTreasury()
            .accounts({
            payer,
            mint: params.mint,
            treasuryState,
            treasuryAuth,
            treasury: params.treasury.publicKey,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
            rent: web3_js_1.SYSVAR_RENT_PUBKEY,
        })
            .signers([params.treasury])
            .rpc();
        return { signature, treasuryState, treasuryAuth };
    }
    async slashVote(params) {
        const slasher = params.slasher ?? this.walletPubkey();
        const verifierWorker = this.pdas.worker(params.verifier);
        const stakeAuth = this.pdas.stakeAuth(verifierWorker);
        const stakeVault = this.pdas.stakeVault(params.verifier);
        const treasuryState = this.pdas.treasuryState(params.mint);
        const treasuryAuth = this.pdas.treasuryAuth(params.mint);
        return this.methods
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
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
        })
            .rpc();
    }
    async initStakingPool(params) {
        const payer = params.payer ?? this.walletPubkey();
        const pool = this.pdas.stakingPool(params.mint);
        const poolAuth = this.pdas.stakingPoolAuth(params.mint);
        const signature = await this.methods
            .initStakingPool()
            .accounts({
            payer,
            mint: params.mint,
            pool,
            poolAuth,
            stakeVault: params.stakeVault.publicKey,
            rewardVault: params.rewardVault.publicKey,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
            rent: web3_js_1.SYSVAR_RENT_PUBKEY,
        })
            .signers([params.stakeVault, params.rewardVault])
            .rpc();
        return {
            signature,
            pool,
            poolAuth,
            stakeVault: params.stakeVault.publicKey,
            rewardVault: params.rewardVault.publicKey,
        };
    }
    async stakeNetwork(params) {
        const owner = params.owner ?? this.walletPubkey();
        const pool = this.pdas.stakingPool(params.mint);
        const staker = this.pdas.networkStaker(owner, params.mint);
        const stakeVault = params.stakeVault ?? (await this.fetchStakingPool(pool)).stakeVault;
        let builder = this.methods
            .stakeNetwork((0, pdas_1.toBn)(params.amount))
            .accounts({
            owner,
            mint: params.mint,
            pool,
            staker,
            ownerToken: params.ownerToken,
            stakeVault,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
            systemProgram: web3_js_1.SystemProgram.programId,
        });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, pool, staker };
    }
    async fundStakingRewards(params) {
        const funder = params.funder ?? this.walletPubkey();
        const pool = this.pdas.stakingPool(params.mint);
        const rewardVault = params.rewardVault ?? (await this.fetchStakingPool(pool)).rewardVault;
        let builder = this.methods
            .fundStakingRewards((0, pdas_1.toBn)(params.amount))
            .accounts({
            funder,
            mint: params.mint,
            pool,
            funderToken: params.funderToken,
            rewardVault,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async claimStakingReward(params) {
        const owner = params.owner ?? this.walletPubkey();
        const pool = this.pdas.stakingPool(params.mint);
        const poolAuth = this.pdas.stakingPoolAuth(params.mint);
        const staker = this.pdas.networkStaker(owner, params.mint);
        const rewardVault = params.rewardVault ?? (await this.fetchStakingPool(pool)).rewardVault;
        let builder = this.methods
            .claimStakingReward()
            .accounts({
            owner,
            mint: params.mint,
            pool,
            poolAuth,
            staker,
            rewardVault,
            ownerRewardToken: params.ownerRewardToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async requestUnstake(params) {
        const owner = params.owner ?? this.walletPubkey();
        const pool = this.pdas.stakingPool(params.mint);
        const staker = this.pdas.networkStaker(owner, params.mint);
        let builder = this.methods
            .requestUnstake((0, pdas_1.toBn)(params.amount))
            .accounts({ owner, mint: params.mint, pool, staker });
        builder = appendSigners(builder, params.signers);
        const signature = await builder.rpc();
        return { signature, pool, staker };
    }
    async withdrawUnstaked(params) {
        const owner = params.owner ?? this.walletPubkey();
        const pool = this.pdas.stakingPool(params.mint);
        const poolAuth = this.pdas.stakingPoolAuth(params.mint);
        const staker = this.pdas.networkStaker(owner, params.mint);
        const stakeVault = params.stakeVault ?? (await this.fetchStakingPool(pool)).stakeVault;
        let builder = this.methods
            .withdrawUnstaked()
            .accounts({
            owner,
            mint: params.mint,
            pool,
            poolAuth,
            staker,
            stakeVault,
            ownerToken: params.ownerToken,
            tokenProgram: spl_token_1.TOKEN_PROGRAM_ID,
        });
        builder = appendSigners(builder, params.signers);
        return builder.rpc();
    }
    async fetchJob(job) {
        return this.accounts.job.fetch(job);
    }
    async fetchJobStorage(jobOrJobStorage, isJobStorageAccount = false) {
        const account = isJobStorageAccount ? jobOrJobStorage : this.pdas.jobStorage(jobOrJobStorage);
        return this.accounts.jobStorage.fetch(account);
    }
    async fetchFragment(fragment) {
        return this.accounts.fragment.fetch(fragment);
    }
    async fetchWorker(workerOrWorkerAccount, isWorkerAccount = false) {
        const account = isWorkerAccount ? workerOrWorkerAccount : this.pdas.worker(workerOrWorkerAccount);
        return this.accounts.worker.fetch(account);
    }
    async fetchWorkerReputation(workerOrWorkerAccount, isWorkerAccount = false) {
        const worker = await this.fetchWorker(workerOrWorkerAccount, isWorkerAccount);
        return {
            computeReputation: worker.computeReputation,
            verifyReputation: worker.verifyReputation,
            globalReputation: worker.globalReputation,
            reliabilityScore: worker.reliabilityScore,
        };
    }
    async fetchAllWorkers() {
        return this.accounts.worker.all();
    }
    async fetchFragmentsForJob(job) {
        return this.accounts.fragment.all([
            { memcmp: { offset: 8, bytes: job.toBase58() } },
        ]);
    }
    async fetchVote(vote) {
        return this.accounts.fragmentVote.fetch(vote);
    }
    async fetchRoundResolution(roundResolution) {
        return this.accounts.fragmentResolution.fetch(roundResolution);
    }
    async fetchResult(result) {
        return this.accounts.jobResult.fetch(result);
    }
    async fetchTreasuryState(treasuryState) {
        return this.accounts.treasury.fetch(treasuryState);
    }
    async fetchSplitProposal(splitProposal) {
        return this.accounts.splitProposal.fetch(splitProposal);
    }
    async fetchStakingPool(pool) {
        return this.accounts.stakingPool.fetch(pool);
    }
    async fetchNetworkStaker(stakerOrOwner, mint) {
        const staker = mint ? this.pdas.networkStaker(stakerOrOwner, mint) : stakerOrOwner;
        return this.accounts.networkStaker.fetch(staker);
    }
}
exports.SiliciumLayerSdk = SiliciumLayerSdk;
