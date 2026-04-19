import { BN } from "@coral-xyz/anchor";
export function toBN(value) {
    return BN.isBN(value) ? value : new BN(value.toString());
}
export function bigintFrom(value) {
    if (typeof value === "bigint")
        return value;
    if (typeof value === "number")
        return BigInt(value);
    if (typeof value === "string")
        return BigInt(value);
    if (BN.isBN(value))
        return BigInt(value.toString());
    return 0n;
}
export function numberFrom(value) {
    if (typeof value === "number")
        return value;
    if (typeof value === "bigint")
        return Number(value);
    if (typeof value === "string")
        return Number(value);
    if (BN.isBN(value))
        return value.toNumber();
    return 0;
}
export function normalize32(value) {
    const bytes = Array.from(value, (v) => Number(v));
    if (bytes.length !== 32) {
        throw new Error(`Expected exactly 32 bytes, received ${bytes.length}.`);
    }
    return bytes;
}
export function normalizeBytes(value) {
    if (typeof value === "string") {
        return Array.from(new TextEncoder().encode(value), (v) => Number(v));
    }
    return Array.from(value, (v) => Number(v));
}
export function bytesToUtf8(bytes) {
    return new TextDecoder().decode(new Uint8Array(bytes));
}
export function bufferFromString(value) {
    return Buffer.from(value, "utf8");
}
export function bnToLeBuffer(value, size) {
    return toBN(value).toArrayLike(Buffer, "le", size);
}
export function u32ToLeBuffer(value) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
        throw new Error(`Invalid u32 value: ${value}`);
    }
    const buffer = Buffer.alloc(4);
    buffer.writeUInt32LE(value, 0);
    return buffer;
}
export function u16ToLeBuffer(value) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffff) {
        throw new Error(`Invalid u16 value: ${value}`);
    }
    const buffer = Buffer.alloc(2);
    buffer.writeUInt16LE(value, 0);
    return buffer;
}
