import * as anchor from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { SdkEventName } from "./types";
export type EventCallback<T = unknown> = (event: T, slot: number, signature: string) => void;
export interface EventSubscription {
    eventName: SdkEventName;
    listenerId: number;
    remove(): Promise<void>;
}
export declare class SiliciumEventClient {
    private readonly program;
    constructor(program: anchor.Program);
    on<T = unknown>(eventName: SdkEventName, callback: EventCallback<T>): EventSubscription;
    onAll(callback: (name: SdkEventName, event: unknown, slot: number, signature: string) => void): EventSubscription[];
    remove(subscription: EventSubscription): Promise<void>;
}
export declare function pubkey(value: PublicKey | string): PublicKey;
