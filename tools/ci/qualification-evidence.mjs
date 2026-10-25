/** Retain the exact gate inputs in the signed release, independently of Actions expiry. */
import { mkdirSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { root, run, readJson, writeJson, Failure } from '../lib/process.mjs';
import { verifiedRun, repository } from '../lib/github.mjs';
import { validateGate, requireGate } from '../lib/gate.mjs';

export function qualificationEvidence(runRecord, plan, reports) {
  if (runRecord.event !== 'push' || runRecord.head_branch !== 'main'
    || runRecord.conclusion !== 'success' || runRecord.head_repository?.full_name !== repository) {
    throw new Failure('Permanent evidence requires a successful main push from Fusion');
  }
  const gate = requireGate(validateGate(plan, reports, { expectedSha: runRecord.head_sha }));
  return { schema_version: 1, source_sha: runRecord.head_sha,
    run: { id: runRecord.id, url: `https://github.com/${repository}/actions/runs/${runRecord.id}`,
      event: runRecord.event, branch: runRecord.head_branch, workflow: '.github/workflows/ci.yml' },
    plan, reports, gate };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const id = process.env.QUALIFICATION_RUN;
  const record = verifiedRun(id);
  const directory = resolve(root, '.artifacts/qualification-evidence');
  mkdirSync(directory, { recursive: true });
  for (const pattern of ['qualification-plan', 'report-*']) {
    run(['gh', 'run', 'download', String(id), '--repo', repository, '--pattern', pattern, '--dir', directory], { timeout: 120_000 });
  }
  const paths = readdirSync(directory, { recursive: true }).filter(file => file.endsWith('.json'));
  const documents = paths.map(file => readJson(resolve(directory, file)));
  const plans = documents.filter(value => Array.isArray(value.suites));
  if (plans.length !== 1) throw new Failure('Expected exactly one permanent qualification plan');
  const evidence = qualificationEvidence(record, plans[0], documents.filter(value => value.suite));
  writeJson(resolve(root, '.artifacts/publish/qualification.json'), evidence);
}
