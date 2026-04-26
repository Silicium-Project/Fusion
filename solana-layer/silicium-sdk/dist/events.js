"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.SiliciumEventClient = void 0;
exports.pubkey = pubkey;
const web3_js_1 = require("@solana/web3.js");
class SiliciumEventClient {
    constructor(program) {
        this.program = program;
    }
    on(eventName, callback) {
        const listenerId = this.program.addEventListener(eventName, (event, slot, signature) => callback(event, slot, signature));
        return {
            eventName,
            listenerId,
            remove: async () => {
                await this.program.removeEventListener(listenerId);
            },
        };
    }
    onAll(callback) {
        const names = [
            "jobCreated",
            "workerRegistered",
            "workerStaked",
            "treasuryInitialized",
            "fragmentClaimed",
            "fragmentReclaimed",
            "fragmentSubmitted",
            "fragmentVerified",
            "fragmentRejected",
            "verifierRewardClaimed",
            "jobFinalized",
            "jobCancelled",
            "voteSlashed",
        ];
        return names.map((name) => this.on(name, (event, slot, signature) => callback(name, event, slot, signature)));
    }
    async remove(subscription) {
        await this.program.removeEventListener(subscription.listenerId);
    }
}
exports.SiliciumEventClient = SiliciumEventClient;
function pubkey(value) {
    return typeof value === "string" ? new web3_js_1.PublicKey(value) : value;
}
