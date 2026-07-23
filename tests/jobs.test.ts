import { describe, expect, it } from 'vitest';
import { clampJobPage, compactJobError, isJobCancellable } from '../utils/jobs';

describe('job dashboard helpers', () => {
  it('keeps traceback payloads compact', () => {
    const message = `RuntimeError: worker failed\n${'x'.repeat(500)}`;
    expect(compactJobError(message)).toBe('RuntimeError: worker failed');
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
