import type { JobStatus, NetworkPeer } from '~/types/api';

const statusLabels: Record<string, string> = {
  queued: 'En attente', running: 'En cours', cancelling: 'Arrêt en cours', completed: 'Terminé',
  failed: 'Échec', cancelled: 'Annulé', canceled: 'Annulé', expired: 'Expiré', operational: 'Opérationnel',
  degraded: 'Dégradé', unavailable: 'Indisponible', current: 'À jour', outdated: 'Mise à jour requise',
  'outdated-build': 'Build obsolète', unknown: 'À vérifier', server: 'Serveur', online: 'En ligne', offline: 'Hors ligne',
};

const networkRoleLabels: Record<string, string> = {
  server: 'Orchestration', orchestrator: 'Orchestration', orchestrateur: 'Orchestration', orchestration: 'Orchestration',
  resource: 'Calcul', worker: 'Calcul', compute: 'Calcul', calcul: 'Calcul',
  verify: 'Vérification', validator: 'Vérification', validation: 'Vérification',
  storage: 'Persistance', persistence: 'Persistance', stockage: 'Persistance',
};

export function statusLabel(status?: JobStatus): string {
  const normalized = String(status || 'unknown').toLowerCase();
  return statusLabels[normalized] || normalized.replaceAll('_', ' ');
}

export function statusTone(status?: JobStatus): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  const value = String(status || '').toLowerCase();
  if (['completed', 'operational', 'online', 'current', 'verified', 'server'].includes(value)) return 'success';
  if (['queued', 'cancelling', 'degraded', 'outdated', 'outdated-build', 'expired'].includes(value)) return 'warning';
  if (['failed', 'cancelled', 'canceled', 'unavailable', 'offline'].includes(value)) return 'danger';
  if (['running', 'active', 'dispatched', 'claimed'].includes(value)) return 'info';
  return 'neutral';
}

export function networkRoleLabel(role?: string): string {
  const normalized = String(role || '').toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ');
  return networkRoleLabels[normalized] || normalized || 'Rôle non défini';
}

export function formatDate(value?: string, includeTime = true): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('fr-FR', {
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

export function compactIdentifier(value?: string, head = 7, tail = 5): string {
  if (!value) return '—';
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

export function peerId(peer: NetworkPeer): string {
  return String(peer.node_id || peer.nodeId || 'Nœud sans identifiant');
}

export function peerRoles(peer: NetworkPeer): string[] {
  const direct = Array.isArray(peer.roles) ? peer.roles : Array.isArray(peer.node_roles) ? peer.node_roles : [];
  if (direct.length) return direct.map(String);
  return peer.role ? [String(peer.role)] : peerId(peer) === 'orchestrator-1' ? ['orchestrateur'] : ['ressource'];
}
