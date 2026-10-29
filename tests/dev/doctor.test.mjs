import test from 'node:test';
import assert from 'node:assert/strict';
import { toolVersion } from '../../tools/lib/doctor.mjs';
test('version discovery handles Node v and Go prefixes without dropping the major field', () => {
  assert.equal(toolVersion('v22.23.4'), '22.23.4');
  assert.equal(toolVersion('go version go1.27.3 linux/amd64'), '1.27.3');
  assert.equal(toolVersion('cargo 1.98.1 (hash 2026-10-01)'), '1.98.1');
  assert.equal(toolVersion('Python 3.11.17'), '3.11.17');
  assert.equal(toolVersion('unavailable'), null);
});
