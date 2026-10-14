import { describe, expect, it } from 'vitest';
import { clampJobPage, compactJobError, extractJobError, jobPartCount, fragmentStateLabel, fragmentVisualState, isHashWorkload, isImageWorkload, isJobCancellable, parseHashReport, resultExtension, shouldRefreshJob } from '../utils/jobs';

describe('job dashboard helpers', () => {
  it('preserves multiline traceback details while bounding oversized payloads', () => {
    const message = 'RuntimeError: worker failed\nTraceback (most recent call last):\n  worker.py:42\nValueError: invalid scene';
    expect(compactJobError(message)).toBe(message);
    expect(compactJobError('x'.repeat(20_000), 180)).toContain('détail d’erreur tronqué');
  });

  it('extracts structured submit failures without dropping the traceback', () => {
    expect(extractJobError({ data: { error: 'worker failed', traceback: 'Traceback\nValueError: bad scene' } })).toBe('worker failed\n\nTraceback\nValueError: bad scene');
    expect(extractJobError({ data: 'plain backend error' })).toBe('plain backend error');
    const nginx = '<html>\r\n<head><title>500 Internal Server Error</title></head>\r\n<body></body>\r\n</html>\r\n<!-- a padding -->';
    expect(extractJobError({ data: nginx, statusCode: 500 })).toContain('Réessayez dans quelques minutes');
    expect(extractJobError({ data: nginx })).toBe('La tâche ne peut pas être soumise pour le moment.');
    expect(extractJobError({ response: { _data: '<!DOCTYPE html><p>x</p>', status: 413 } })).toBe('Le fichier est trop volumineux pour être envoyé.');
    expect(extractJobError({ data: { message: 'Nom trop long.' }, statusCode: 400 })).toBe('Nom trop long.');
  });

  it('only offers cancellation for non-terminal jobs', () => {
    expect(isJobCancellable('running')).toBe(true);
    expect(isJobCancellable('queued')).toBe(true);
    expect(isJobCancellable('completed')).toBe(false);
    expect(isJobCancellable('failed')).toBe(false);
  });

  it('maps raytracer lifecycle states to live tile states', () => {
    expect(fragmentVisualState('planned')).toBe('planned');
    expect(fragmentVisualState('queued_compute')).toBe('computing');
    expect(fragmentVisualState('computed')).toBe('validating');
    expect(fragmentVisualState('queued_verify')).toBe('validating');
    expect(fragmentVisualState('reassembled')).toBe('done');
    expect(fragmentVisualState('verify_failed')).toBe('failed');
    expect(fragmentStateLabel('queued_verify')).toBe('Validation en cours');
  });

  it('keeps polling a prematurely completed job until its result is available', () => {
    expect(shouldRefreshJob('running', false)).toBe(true);
    expect(shouldRefreshJob('completed', false)).toBe(true);
    expect(shouldRefreshJob('completed', true)).toBe(false);
    expect(shouldRefreshJob('failed', false)).toBe(false);
  });

  it('clamps pagination after filters reduce the result set', () => {
    expect(clampJobPage(50, 41, 20)).toBe(3);
    expect(clampJobPage(0, 0, 20)).toBe(1);
  });

  it('tells image jobs from hash jobs', () => {
    expect(isImageWorkload('raytracer')).toBe(true);
    expect(isImageWorkload('')).toBe(true);
    expect(isImageWorkload('calcul/integrity/sha256')).toBe(false);
    expect(isHashWorkload('calcul/integrity/sha256')).toBe(true);
    expect(isHashWorkload('calcul/hash/sha256')).toBe(true);
    expect(isHashWorkload('raytracer')).toBe(false);
  });

  it('names downloaded results after their content type', () => {
    expect(resultExtension('image/png')).toBe('png');
    expect(resultExtension('application/json; charset=utf-8')).toBe('json');
    expect(resultExtension('image/x-portable-pixmap')).toBe('ppm');
    expect(resultExtension('application/octet-stream')).toBe('bin');
    expect(resultExtension('application/octet-stream', 'inline; filename="result.png"')).toBe('png');
    expect(resultExtension('image/png', null)).toBe('png');
  });

  it('reads the SHA-256 report written by the node', () => {
    const report = { workload: 'calcul/integrity/sha256', algorithm: 'sha256', size_bytes: 3, chunk_count: 1, chunk_list_sha256: 'l', input_hash: 'h', chunks: [{ index: 0, offset: 0, length: 3, sha256: 'h' }] };
    expect(parseHashReport(report)?.input_hash).toBe('h');
    expect(parseHashReport({ chunks: 'nope' })).toBeNull();
    expect(parseHashReport(null)).toBeNull();
  });

  it('counts the parts of a job, 0 while the network has not split it', () => {
    expect(jobPartCount(0, '8')).toBe(8);
    expect(jobPartCount(undefined, null, 3)).toBe(3);
    expect(jobPartCount(0, undefined, 0)).toBe(0);
    expect(jobPartCount('abc', -2)).toBe(0);
  });
});
