import { describe, expect, it } from 'vitest';
import { clampProgress, formatElapsed, formatProgress, phaseLabel, taskStatusLabel } from './format';

describe('node telemetry presentation', () => {
  it('never renders progress outside the valid range', () => {
    expect(clampProgress(-20)).toBe(0);
    expect(clampProgress(140)).toBe(100);
    expect(formatProgress(3.25)).toBe('3.3%');
  });

  it('formats long-running work without losing elapsed time', () => {
    expect(formatElapsed(3_661_000)).toBe('1h 1m');
  });

  it('exposes cancellation and expiration states', () => {
    expect(taskStatusLabel('cancelled')).toBe('annulee');
    expect(phaseLabel('expired')).toBe('Expiree');
  });
});
