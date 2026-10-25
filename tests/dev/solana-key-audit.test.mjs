import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPairSync } from 'node:crypto';
import { isSolanaKeypair,findKeypairs } from '../../tools/tasks/solana-key-audit.mjs';
test('a disposable Solana keypair is detected in JSON and embedded text',()=>{
 const {privateKey,publicKey}=generateKeyPairSync('ed25519');
 const secret=[...privateKey.export({format:'der',type:'pkcs8'}).subarray(-32),...publicKey.export({format:'der',type:'spki'}).subarray(-32)];
 assert.equal(isSolanaKeypair(secret),true);
 assert.equal(findKeypairs('example='+JSON.stringify(secret)).length,1);
});
test('hash fixtures and invalid byte arrays are not mistaken for keys',()=>{
 for(const a of [[],Array(32).fill(0),Array(64).fill(0),Array(64).fill(256)])assert.equal(isSolanaKeypair(a),false);
});
