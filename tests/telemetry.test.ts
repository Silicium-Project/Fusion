import { describe, expect, it } from 'vitest';
import { sampleTelemetry } from '../services/telemetry';

describe('network telemetry samples', () => {
  it('stays deterministic for stable visual previews', () => {
    expect(sampleTelemetry(4, 8)).toEqual(sampleTelemetry(4, 8));
  });

  it('keeps operational values inside usable display bounds', () => {
    const samples = Array.from({ length: 24 }, (_, tick) => sampleTelemetry(tick, 4));
    expect(samples.every(sample => sample.latencyMs > 0 && sample.throughputTbps > 0)).toBe(true);
    expect(samples.every(sample => sample.utilization >= 38 && sample.utilization <= 86)).toBe(true);
    expect(samples.every(sample => sample.queueDepth >= 1 && sample.packetsPerSecond > 0)).toBe(true);
  });
});
