import * as anchor from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { SdkEventName } from "./types";

export type EventCallback<T = unknown> = (event: T, slot: number, signature: string) => void;

export interface EventSubscription {
  eventName: SdkEventName;
  listenerId: number;
  remove(): Promise<void>;
}

export class SiliciumEventClient {
  constructor(private readonly program: anchor.Program) {}

  on<T = unknown>(eventName: SdkEventName, callback: EventCallback<T>): EventSubscription {
    const listenerId = this.program.addEventListener(
      eventName,
      (event: T, slot: number, signature: string) => callback(event, slot, signature),
    );

    return {
      eventName,
      listenerId,
      remove: async () => {
        await this.program.removeEventListener(listenerId);
      },
    };
  }

  onAll(callback: (name: SdkEventName, event: unknown, slot: number, signature: string) => void): EventSubscription[] {
    const names: SdkEventName[] = [
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

  async remove(subscription: EventSubscription): Promise<void> {
    await this.program.removeEventListener(subscription.listenerId);
  }
}

export function pubkey(value: PublicKey | string): PublicKey {
  return typeof value === "string" ? new PublicKey(value) : value;
}
