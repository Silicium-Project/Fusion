import { describe, expect, it } from 'vitest';
import { clampJobPage, compactJobError, extractJobError, isJobCancellable } from '../utils/jobs';

describe('job dashboard helpers', () => {
  it('preserves multiline traceback details while bounding oversized payloads', () => {
    const message = 'RuntimeError: worker failed\nTraceback (most recent call last):\n  worker.py:42\nValueError: invalid scene';
    expect(compactJobError(message)).toBe(message);
    expect(compactJobError('x'.repeat(20_000), 180)).toContain('détail d’erreur tronqué');
  });

  it('extracts structured submit failures without dropping the traceback', () => {
    expect(extractJobError({ data: { error: 'worker failed', traceback: 'Traceback\nValueError: bad scene' } })).toBe('worker failed\n\nTraceback\nValueError: bad scene');
    expect(extractJobError({ data: 'plain backend error' })).toBe('plain backend error');
  });

  it('only offers cancellation for non-terminal jobs', () => {
    expect(isJobCancellable('running')).toBe(true);
    expect(isJobCancellable('queued')).toBe(true);
    expect(isJobCancellable('completed')).toBe(false);
    expect(isJobCancellable('failed')).toBe(false);
  });

  it('clamps pagination after filters reduce the result set', () => {
    expect(clampJobPage(50, 41, 20)).toBe(3);
    expect(clampJobPage(0, 0, 20)).toBe(1);
  });
});
