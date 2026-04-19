import { BN } from "@coral-xyz/anchor";

export function toBN(value: number | bigint | BN): BN {
  return BN.isBN(value) ? value : new BN(value.toString());
}

export function bigintFrom(value: unknown): bigint {
  if (typeof value === "bigint") return value;
  if (typeof value === "number") return BigInt(value);
  if (typeof value === "string") return BigInt(value);
  if (BN.isBN(value as any)) return BigInt((value as BN).toString());
  return 0n;
}

export function numberFrom(value: unknown): number {
  if (typeof value === "number") return value;
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "string") return Number(value);
  if (BN.isBN(value as any)) return (value as BN).toNumber();
  return 0;
}

export function normalize32(value: Uint8Array | number[]): number[] {
  const bytes = Array.from(value, (v) => Number(v));
  if (bytes.length !== 32) {
    throw new Error(`Expected exactly 32 bytes, received ${bytes.length}.`);
  }
  return bytes;
}

export function normalizeBytes(value: string | Uint8Array | number[]): number[] {
  if (typeof value === "string") {
    return Array.from(new TextEncoder().encode(value), (v) => Number(v));
  }
  return Array.from(value, (v) => Number(v));
}

export function bytesToUtf8(bytes: number[]): string {
  return new TextDecoder().decode(new Uint8Array(bytes));
}

export function bufferFromString(value: string): Buffer {
  return Buffer.from(value, "utf8");
}

export function bnToLeBuffer(value: number | bigint | BN, size: number): Buffer {
  return toBN(value).toArrayLike(Buffer, "le", size);
}

export function u32ToLeBuffer(value: number): Buffer {
  if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
    throw new Error(`Invalid u32 value: ${value}`);
  }
  const buffer = Buffer.alloc(4);
  buffer.writeUInt32LE(value, 0);
  return buffer;
}

export function u16ToLeBuffer(value: number): Buffer {
  if (!Number.isInteger(value) || value < 0 || value > 0xffff) {
    throw new Error(`Invalid u16 value: ${value}`);
  }
  const buffer = Buffer.alloc(2);
  buffer.writeUInt16LE(value, 0);
  return buffer;
}