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
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.u32le = u32le;
exports.u16le = u16le;
exports.toBn = toBn;
exports.jobPda = jobPda;
exports.jobStoragePda = jobStoragePda;
exports.fragmentPda = fragmentPda;
exports.workerPda = workerPda;
exports.workerPayoutPda = workerPayoutPda;
exports.escrowAuthPda = escrowAuthPda;
exports.stakeAuthPda = stakeAuthPda;
exports.stakeVaultPda = stakeVaultPda;
exports.votePda = votePda;
exports.roundResolutionPda = roundResolutionPda;
exports.splitProposalPda = splitProposalPda;
exports.resultPda = resultPda;
exports.treasuryStatePda = treasuryStatePda;
exports.treasuryAuthPda = treasuryAuthPda;
exports.stakingPoolPda = stakingPoolPda;
exports.stakingPoolAuthPda = stakingPoolAuthPda;
exports.networkStakerPda = networkStakerPda;
const web3_js_1 = require("@solana/web3.js");
const anchor = __importStar(require("@coral-xyz/anchor"));
function u32le(value) {
    const buffer = Buffer.alloc(4);
    buffer.writeUInt32LE(value, 0);
    return buffer;
}
function u16le(value) {
    const buffer = Buffer.alloc(2);
    buffer.writeUInt16LE(value, 0);
    return buffer;
}
function toBn(value) {
    if (anchor.BN.isBN(value))
        return value;
    return new anchor.BN(value.toString());
}
function jobPda(programId, client, jobId) {
    const id = toBn(jobId);
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("job"), client.toBuffer(), id.toArrayLike(Buffer, "le", 8)], programId)[0];
}
function jobStoragePda(programId, job) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("job_storage"), job.toBuffer()], programId)[0];
}
function fragmentPda(programId, job, fragmentIndex) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("fragment"), job.toBuffer(), u32le(fragmentIndex)], programId)[0];
}
function workerPda(programId, worker) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("worker"), worker.toBuffer()], programId)[0];
}
function workerPayoutPda(programId, workerAccount) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("worker_payout"), workerAccount.toBuffer()], programId)[0];
}
function escrowAuthPda(programId, job) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("escrow_auth"), job.toBuffer()], programId)[0];
}
function stakeAuthPda(programId, workerAccount) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("stake_auth"), workerAccount.toBuffer()], programId)[0];
}
function stakeVaultPda(programId, worker) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("stake_vault"), worker.toBuffer()], programId)[0];
}
function votePda(programId, fragment, verifier, round) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("fragment_vote"), fragment.toBuffer(), verifier.toBuffer(), u16le(round)], programId)[0];
}
function roundResolutionPda(programId, fragment, round) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("fragment_resolution"), fragment.toBuffer(), u16le(round)], programId)[0];
}
function splitProposalPda(programId, parentFragment, round) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("split_proposal"), parentFragment.toBuffer(), u16le(round)], programId)[0];
}
function resultPda(programId, job) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("result"), job.toBuffer()], programId)[0];
}
function treasuryStatePda(programId, mint) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("treasury"), mint.toBuffer()], programId)[0];
}
function treasuryAuthPda(programId, mint) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("treasury_auth"), mint.toBuffer()], programId)[0];
}
function stakingPoolPda(programId, mint) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("staking_pool"), mint.toBuffer()], programId)[0];
}
function stakingPoolAuthPda(programId, mint) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("staking_pool_auth"), mint.toBuffer()], programId)[0];
}
function networkStakerPda(programId, owner, mint) {
    return web3_js_1.PublicKey.findProgramAddressSync([Buffer.from("network_staker"), owner.toBuffer(), mint.toBuffer()], programId)[0];
}
