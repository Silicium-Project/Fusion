import type { JobStatus, NetworkPeer } from '~/types/api';
import { intlLocale, translate } from './i18n';

/** Statuses with a label in the catalog (`status.*`). */
const knownStatuses = new Set([
  'queued', 'running', 'cancelling', 'completed', 'planned', 'queued_compute', 'computed', 'queued_verify', 'verified', 'reassembled',
  'failed', 'cancelled', 'canceled', 'expired', 'dead_lettered', 'finalized', 'resolved', 'operational', 'degraded', 'unavailable',
  'current', 'outdated', 'outdated-build', 'unknown', 'server', 'online', 'offline',
]);

/** Role group of a network role name, as a key of `roles.*`. */
export type NetworkRoleGroup = 'orchestration' | 'compute' | 'verify' | 'storage';

const networkRoleGroups: Record<string, NetworkRoleGroup> = {
  server: 'orchestration', orchestrator: 'orchestration', orchestrateur: 'orchestration', orchestration: 'orchestration',
  resource: 'compute', worker: 'compute', compute: 'compute', calcul: 'compute',
  verify: 'verify', validator: 'verify', validation: 'verify',
  storage: 'storage', persistence: 'storage', stockage: 'storage',
};

export function statusLabel(status?: JobStatus): string {
  const normalized = String(status || 'unknown').toLowerCase();
  return knownStatuses.has(normalized) ? translate(`status.${normalized}`) : normalized.replaceAll('_', ' ');
}

export function statusTone(status?: JobStatus): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  const value = String(status || '').toLowerCase();
  if (['completed', 'operational', 'online', 'current', 'verified', 'reassembled', 'server'].includes(value)) return 'success';
  if (['queued', 'planned', 'queued_compute', 'queued_verify', 'cancelling', 'degraded', 'outdated', 'outdated-build', 'expired'].includes(value)) return 'warning';
  if (['failed', 'cancelled', 'canceled', 'unavailable', 'offline'].includes(value)) return 'danger';
  if (['running', 'active', 'dispatched', 'claimed', 'computed'].includes(value)) return 'info';
  return 'neutral';
}

export function isTerminalNetworkStatus(status?: string): boolean {
  return ['completed', 'failed', 'dead_lettered', 'cancelled', 'canceled', 'expired', 'finalized', 'resolved']
    .includes(String(status || '').toLowerCase());
}

/** The group of a role announced by a node, or undefined for another role. */
export function networkRoleGroup(role?: string): NetworkRoleGroup | undefined {
  const normalized = String(role || '').toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ');
  return networkRoleGroups[normalized];
}

export function networkRoleLabel(role?: string): string {
  const group = networkRoleGroup(role);
  if (group) return translate(`roles.${group}`);
  const normalized = String(role || '').toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ');
  return normalized || translate('roles.undefined');
}

export function formatDate(value?: string, includeTime = true): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(intlLocale(), {
    dateStyle: 'medium', ...(includeTime ? { timeStyle: 'short' as const } : {}),
  }).format(date);
}

export function formatDuration(start?: string, end?: string): string {
  if (!start) return '—';
  const from = new Date(start).getTime();
  const to = end ? new Date(end).getTime() : Date.now();
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return '—';
  const seconds = Math.round((to - from) / 1000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${seconds % 60} s`;
  return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function formatMilliseconds(value?: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const milliseconds = Number(value);
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '—';
  if (milliseconds < 1000) return `${milliseconds < 10 ? milliseconds.toFixed(1) : Math.round(milliseconds)} ms`;
  const seconds = milliseconds / 1000;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  const wholeSeconds = Math.round(seconds);
  const minutes = Math.floor(wholeSeconds / 60);
  return `${minutes} min ${wholeSeconds % 60} s`;
}

export function formatPerformancePercent(value?: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const ratio = Number(value);
  if (!Number.isFinite(ratio) || ratio < 0) return '—';
  return `${(ratio * 100).toFixed(1)} %`;
}

export function formatPerformanceMultiple(value?: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  const ratio = Number(value);
  if (!Number.isFinite(ratio) || ratio < 0) return '—';
  return `${ratio.toFixed(2)}×`;
}

export function compactIdentifier(value?: string, head = 7, tail = 5): string {
  if (!value) return '—';
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

export function peerId(peer: NetworkPeer): string {
  return String(peer.node_id || peer.nodeId || translate('nodes.unnamed'));
}

export function peerRoles(peer: NetworkPeer): string[] {
  const direct = Array.isArray(peer.roles) ? peer.roles : Array.isArray(peer.node_roles) ? peer.node_roles : [];
  if (direct.length) return direct.map(String);
  return peer.role ? [String(peer.role)] : [];
}

export function peerAvailability(peer: NetworkPeer): 'online' | 'offline' | 'unknown' {
  if (typeof peer.online === 'boolean') return peer.online ? 'online' : 'offline';
  const status = String(peer.availability_status || peer.status || '').toLowerCase();
  if (['online', 'operational', 'working', 'idle'].includes(status)) return 'online';
  if (['offline', 'disconnected'].includes(status)) return 'offline';
  return 'unknown';
}
