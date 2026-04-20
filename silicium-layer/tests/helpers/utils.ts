import * as anchor from "@coral-xyz/anchor";
import { assert } from "chai";

export function bnToU64LE(n: anchor.BN): Buffer {
  return n.toArrayLike(Buffer, "le", 8);
}

export function u32LE(n: number): Buffer {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n, 0);
  return b;
}

export function u16LE(n: number): Buffer {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(n, 0);
  return b;
}

export async function expectFail(p: Promise<any>, msg?: string) {
  try {
    await p;
    assert.fail(msg ?? "Expected transaction to fail");
  } catch (_) {
    // expected
  }
}
