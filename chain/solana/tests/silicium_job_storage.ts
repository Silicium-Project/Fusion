import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { PublicKey, SystemProgram, SYSVAR_RENT_PUBKEY } from "@solana/web3.js";
import { assert } from "chai";
import {
  TOKEN_PROGRAM_ID,
  createAssociatedTokenAccount,
  createMint,
  mintTo,
} from "@solana/spl-token";

const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer as Program;

function asHash(byte: number): number[] {
  return Array(32).fill(byte);
}

function jobPda(client: PublicKey, jobId: anchor.BN): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("job"), client.toBuffer(), jobId.toArrayLike(Buffer, "le", 8)],
    program.programId
  )[0];
}

function escrowAuthPda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("escrow_auth"), job.toBuffer()],
    program.programId
  )[0];
}

function jobStoragePda(job: PublicKey): PublicKey {
  return PublicKey.findProgramAddressSync(
    [Buffer.from("job_storage"), job.toBuffer()],
    program.programId
  )[0];
}

describe("silicium job storage", () => {
  let mint: PublicKey;
  let clientToken: PublicKey;

  before(async () => {
    const payer = provider.wallet.payer as anchor.web3.Keypair;
    const client = provider.wallet.publicKey;

    mint = await createMint(provider.connection, payer, client, null, 6);
    clientToken = await createAssociatedTokenAccount(
      provider.connection,
      payer,
      mint,
      client
    );

    await mintTo(
      provider.connection,
      payer,
      mint,
      clientToken,
      client,
      100_000_000
    );
  });

  async function createJobForStorage() {
    const client = provider.wallet.publicKey;
    const jobId = new anchor.BN(900_000 + Math.floor(Math.random() * 100_000));
    const job = jobPda(client, jobId);
    const escrowAuth = escrowAuthPda(job);
    const escrow = anchor.web3.Keypair.generate();
    const deadlineUnix = new anchor.BN(Math.floor(Date.now() / 1000) + 3600);

    await program.methods
      .createJob(
        jobId,
        1,
        new anchor.BN(1_000_000),
        new anchor.BN(100_000),
        new anchor.BN(3_200_000),
        deadlineUnix,
        2
      )
      .accounts({
        client,
        mint,
        job,
        escrowAuth,
        escrow: escrow.publicKey,
        clientToken,
        tokenProgram: TOKEN_PROGRAM_ID,
        systemProgram: SystemProgram.programId,
        rent: SYSVAR_RENT_PUBKEY,
      })
      .signers([escrow])
      .rpc();

    return { job };
  }

  it("declares P2P storage metadata for a job", async () => {
    const client = provider.wallet.publicKey;
    const { job } = await createJobForStorage();
    const jobStorage = jobStoragePda(job);

    const manifestHash = asHash(1);
    const inputRootHash = asHash(2);
    const storageRefHash = asHash(3);
    const encryptionRefHash = asHash(0);

    await program.methods
      .declareJobStorage(
        manifestHash,
        inputRootHash,
        storageRefHash,
        encryptionRefHash
      )
      .accounts({
        client,
        job,
        jobStorage,
        systemProgram: SystemProgram.programId,
      })
      .rpc();

    const storage = await program.account.jobStorage.fetch(jobStorage);

    assert.equal(storage.job.toBase58(), job.toBase58());
    assert.deepEqual(Array.from(storage.manifestHash), manifestHash);
    assert.deepEqual(Array.from(storage.inputRootHash), inputRootHash);
    assert.deepEqual(Array.from(storage.storageRefHash), storageRefHash);
    assert.deepEqual(Array.from(storage.encryptionRefHash), encryptionRefHash);
    assert.equal(storage.declaredBy.toBase58(), client.toBase58());
    assert.isAbove(Number(storage.createdAtUnix.toString()), 0);
  });

  it("rejects zero manifest/input/storage hashes", async () => {
    const client = provider.wallet.publicKey;
    const { job } = await createJobForStorage();
    const jobStorage = jobStoragePda(job);

    try {
      await program.methods
        .declareJobStorage(asHash(0), asHash(2), asHash(3), asHash(0))
        .accounts({
          client,
          job,
          jobStorage,
          systemProgram: SystemProgram.programId,
        })
        .rpc();

      assert.fail("declareJobStorage should have failed with InvalidStorageHash");
    } catch (e: any) {
      assert.include(String(e), "InvalidStorageHash");
    }
  });
});
