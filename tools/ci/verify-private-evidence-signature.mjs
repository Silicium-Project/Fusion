import { lstatSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import {
  privateEvidenceSignatureLimitBytes,
  verifyPrivateEvidenceSignature,
} from '../lib/private-evidence-signature.mjs';
import { Failure, inside } from '../lib/process.mjs';

const trustAnchor = 'contracts/trust/private-integration-evidence-ed25519.pub.pem';

function readRegularFile(path) {
  let stat;
  try {
    stat = lstatSync(path);
  } catch {
    throw new Failure('Private evidence signature input is missing');
  }
  if (!stat.isFile() || stat.isSymbolicLink())
    throw new Failure('Private evidence signature inputs must be regular files');
  return readFileSync(path);
}

export function verifyPrivateEvidenceFiles({ receiptPath, signaturePath, publicKeyPath }) {
  const receiptBytes = readRegularFile(inside(receiptPath));
  const signatureBytes = readRegularFile(inside(signaturePath));
  if (signatureBytes.length > privateEvidenceSignatureLimitBytes)
    throw new Failure('Private evidence signature file exceeds its storage bound');
  const publicKey = readRegularFile(inside(publicKeyPath ?? trustAnchor));
  return verifyPrivateEvidenceSignature({ receiptBytes, signatureBytes, publicKey });
}

function main() {
  const [receiptPath, signaturePath] = process.argv.slice(2);
  if (!receiptPath || !signaturePath)
    throw new Failure(
      'Usage: node tools/ci/verify-private-evidence-signature.mjs RECEIPT SIGNATURE',
      2,
    );
  console.log(
    JSON.stringify({
      status: 'verified',
      ...verifyPrivateEvidenceFiles({ receiptPath, signaturePath }),
    }),
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = error.exitCode ?? 1;
  }
}
