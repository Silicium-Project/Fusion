/** Verify the detached signature on a private Integration metadata receipt. */
import { createHash, createPublicKey, verify } from 'node:crypto';
import { Failure } from './process.mjs';

export const privateEvidenceSignatureName = (attempt) =>
  `private-integration-evidence-signature-${attempt}`;
export const privateEvidenceSignatureLimitBytes = 64 * 1024;

const receiptLimitBytes = 1024 ** 2;
const signatureEnvelopeLimitBytes = 16 * 1024;
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

function parseSignatureEnvelope(signatureBytes) {
  if (
    !Buffer.isBuffer(signatureBytes) ||
    signatureBytes.length < 1 ||
    signatureBytes.length > signatureEnvelopeLimitBytes
  )
    throw new Failure('Private evidence signature envelope is missing or oversized');
  let envelope;
  try {
    envelope = JSON.parse(signatureBytes.toString('utf8'));
  } catch {
    throw new Failure('Private evidence signature envelope is invalid JSON');
  }
  const keys = Object.keys(envelope ?? {}).sort();
  if (
    JSON.stringify(keys) !==
    JSON.stringify(['algorithm', 'key_id', 'receipt_sha256', 'schema_version', 'signature_base64'])
  )
    throw new Failure('Private evidence signature envelope has an unexpected schema');
  return envelope;
}

export function verifyPrivateEvidenceSignature({ receiptBytes, signatureBytes, publicKey }) {
  if (
    !Buffer.isBuffer(receiptBytes) ||
    receiptBytes.length < 1 ||
    receiptBytes.length > receiptLimitBytes
  )
    throw new Failure('Private evidence receipt is missing or oversized');
  const envelope = parseSignatureEnvelope(signatureBytes);
  let key;
  try {
    key = createPublicKey(publicKey);
  } catch {
    throw new Failure('Private evidence trust anchor is invalid');
  }
  if (key.asymmetricKeyType !== 'ed25519')
    throw new Failure('Private evidence trust anchor must use Ed25519');
  const keyId = `sha256:${sha256(key.export({ type: 'spki', format: 'der' }))}`;
  if (
    envelope.schema_version !== 1 ||
    envelope.algorithm !== 'Ed25519' ||
    envelope.key_id !== keyId ||
    envelope.receipt_sha256 !== sha256(receiptBytes) ||
    typeof envelope.signature_base64 !== 'string' ||
    !/^[A-Za-z0-9+/]{86}==$/.test(envelope.signature_base64)
  )
    throw new Failure('Private evidence signature identity or digest is invalid');
  const signature = Buffer.from(envelope.signature_base64, 'base64');
  if (signature.length !== 64 || signature.toString('base64') !== envelope.signature_base64)
    throw new Failure('Private evidence signature encoding is invalid');
  if (!verify(null, receiptBytes, key, signature))
    throw new Failure('Private evidence receipt signature verification failed');
  return { algorithm: envelope.algorithm, key_id: keyId, receipt_sha256: envelope.receipt_sha256 };
}
