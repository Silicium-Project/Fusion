import test from 'node:test';
import assert from 'node:assert/strict';
import { run, root } from '../../tools/lib/process.mjs';
import { repositoryCommands } from '../../contracts/install/repositories.mjs';
test('displayed repository snippets contain real newlines and exactly one continuation slash', () => {
  for (const manager of ['apt', 'dnf'])
    for (const channel of ['dev', 'prod']) {
      const snippets = repositoryCommands(manager, channel);
      assert.ok(snippets.setup.includes('\n'));
      assert.ok(!snippets.setup.includes('\\n'));
      for (const line of snippets.setup.split('\n').filter((line) => line.endsWith('\\')))
        assert.ok(!line.endsWith('\\\\'));
      for (const script of Object.values(snippets))
        assert.equal(
          run(['bash', '-n'], { cwd: root, input: script, allowFailure: true }).status,
          0,
        );
    }
});
test('transport overrides cannot inject commands or silently disable production HTTPS', () => {
  assert.throws(() =>
    repositoryCommands('apt', 'dev', { baseURL: 'http://example.invalid/downloads' }),
  );
  for (const baseURL of [
    'https://example.invalid/downloads;id',
    'https://user:secret@example.invalid/downloads',
    'https://example.invalid/$(id)',
  ])
    assert.throws(() => repositoryCommands('apt', 'dev', { baseURL }));
  assert.ok(
    repositoryCommands('apt', 'dev', {
      baseURL: 'http://fixture.invalid/downloads',
      testTransport: true,
    }).setup.includes('http://fixture.invalid/downloads'),
  );
});
