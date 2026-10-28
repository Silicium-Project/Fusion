import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { verifyPrivateEvidenceSignature } from '../../tools/lib/private-evidence-signature.mjs';

const pair = generateKeyPairSync('ed25519');
const publicKey = pair.publicKey.export({ type: 'spki', format: 'pem' });
const keyId = `sha256:${createHash('sha256')
  .update(pair.publicKey.export({ type: 'spki', format: 'der' }))
  .digest('hex')}`;
const receiptBytes = Buffer.from(
  '{"schema_version":1,"evidence_type":"silicium.private-integration"}\n',
);
const receiptDigest = createHash('sha256').update(receiptBytes).digest('hex');

function envelopeFor(privateKey) {
  return Buffer.from(
    `${JSON.stringify({
      schema_version: 1,
      algorithm: 'Ed25519',
      key_id: keyId,
      receipt_sha256: receiptDigest,
      signature_base64: sign(null, receiptBytes, privateKey).toString('base64'),
    })}\n`,
  );
}

test('verifies an Ed25519 signature over the exact private evidence receipt bytes', () => {
  const result = verifyPrivateEvidenceSignature({
    receiptBytes,
    signatureBytes: envelopeFor(pair.privateKey),
    publicKey,
  });
  assert.equal(result.algorithm, 'Ed25519');
  assert.equal(result.receipt_sha256, receiptDigest);
});

test('rejects receipt edits, a different trust key, malformed envelopes, and oversized receipts', () => {
  const signatureBytes = envelopeFor(pair.privateKey);
  const changedReceipt = Buffer.from(`${receiptBytes.toString()} `);
  assert.throws(() =>
    verifyPrivateEvidenceSignature({ receiptBytes: changedReceipt, signatureBytes, publicKey }),
  );

  const wrongPair = generateKeyPairSync('ed25519');
  assert.throws(() =>
    verifyPrivateEvidenceSignature({
      receiptBytes,
      signatureBytes,
      publicKey: wrongPair.publicKey.export({ type: 'spki', format: 'pem' }),
    }),
  );
  assert.throws(() =>
    verifyPrivateEvidenceSignature({ receiptBytes, signatureBytes: Buffer.from('{}'), publicKey }),
  );
  assert.throws(() =>
    verifyPrivateEvidenceSignature({
      receiptBytes: Buffer.alloc(1024 ** 2 + 1),
      signatureBytes,
      publicKey,
    }),
  );
});

test('rejects a signature produced by another private key', () => {
  const wrongPair = generateKeyPairSync('ed25519');
  assert.throws(() =>
    verifyPrivateEvidenceSignature({
      receiptBytes,
      signatureBytes: envelopeFor(wrongPair.privateKey),
      publicKey,
    }),
  );
});
