import type { TelemetrySample } from '~/utils/telemetry';

/** A bounded history of observations received by this view, never simulated. */
export function useTelemetryHistory() {
  const samples = ref<TelemetrySample[]>([]);
  function record(sample: TelemetrySample): void {
    if (!Number.isFinite(sample.at) || sample.at <= 0) return;
    const last = samples.value.at(-1);
    // Identical timestamps are the same observation, not another measurement.
    if (last && sample.at <= last.at) return;
    samples.value = [
      ...samples.value.filter((item) => item.at >= sample.at - 300_000),
      sample,
    ].slice(-120);
  }
  function clear(): void {
    samples.value = [];
  }
  return { samples, record, clear };
}
