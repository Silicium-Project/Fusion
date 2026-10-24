import type { NetworkPeer, NetworkRuntimeTelemetry } from '~/types/api';

/** Missing telemetry must never become a measured zero. */
export function metricNumber(value: unknown): number | null {
  if (value === null || value === undefined || typeof value === 'boolean' || (typeof value === 'string' && !value.trim())) return null;
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function metricPercent(value: unknown): number | null {
  const number = metricNumber(value);
  return number !== null && number <= 100 ? number : null;
}

export function peerTelemetry(peer?: NetworkPeer): NetworkRuntimeTelemetry | undefined {
  if (!peer) return undefined;
  return peer.telemetry || peer.metrics?.runtime || peer.activity?.telemetry;
}

export function publishedCount(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null;
}

/** Only waiting or retryable tasks belong in the queue count. */
export function pendingTaskCount(value: unknown): number | null {
  if (!Array.isArray(value)) return null;
  return value.filter((task) => {
    if (!task || typeof task !== 'object' || Array.isArray(task)) return false;
    const status = String((task as Record<string, unknown>).status || '').trim().toLowerCase();
    return ['queued', 'proposed', 'retrying'].includes(status);
  }).length;
}

export interface TelemetrySample {
  at: number;
  cpu: number | null;
  memory: number | null;
  queue: number | null;
  active: number | null;
}
