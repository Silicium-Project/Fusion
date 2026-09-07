export interface TelemetrySnapshot {
  latencyMs: number;
  throughputTbps: number;
  utilization: number;
  queueDepth: number;
  packetsPerSecond: number;
}

const clamp = (value: number, min: number, max: number): number => Math.min(max, Math.max(min, value));

/**
 * Produces a smooth, repeatable sample for the visual telemetry layer.
 * The public surface uses this as a product preview; authenticated views
 * combine it with the latest values returned by the API.
 */
export function sampleTelemetry(tick = 0, seed = 0): TelemetrySnapshot {
  const phase = tick * 0.83 + seed;
  const latencyMs = Math.round(28 + Math.sin(phase) * 2.8 + Math.cos(phase * 0.61) * 1.4);
  const throughputTbps = Number((1.28 + Math.sin(phase * 0.74) * 0.12 + Math.cos(phase * 0.33) * 0.04).toFixed(2));
  const utilization = Math.round(clamp(61 + Math.sin(phase * 0.52) * 8 + Math.cos(phase * 0.21) * 3, 38, 86));
  const queueDepth = Math.max(1, Math.round(7 + Math.sin(phase * 0.91) * 2.5));
  const packetsPerSecond = Math.round(860 + Math.sin(phase * 0.67) * 92 + Math.cos(phase * 0.28) * 35);

  return { latencyMs, throughputTbps, utilization, queueDepth, packetsPerSecond };
}
