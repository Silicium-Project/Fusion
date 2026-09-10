import type { NetworkMetrics, NetworkPeer, NetworkPeersResponse, NetworkRuntimeTelemetry, NetworkTasksResponse } from '~/types/api';
import { clientCache } from '~/services/cache';
import { peerRoles } from '~/utils/format';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function asNumber(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function peerRuntime(peer: NetworkPeer): NetworkRuntimeTelemetry | undefined {
  if (peer.telemetry) return peer.telemetry;
  const metrics = asRecord(peer.metrics);
  const runtime = asRecord(metrics?.runtime);
  if (runtime) return runtime as NetworkRuntimeTelemetry;
  const activity = asRecord(peer.activity);
  const activityTelemetry = asRecord(activity?.telemetry);
  return activityTelemetry as NetworkRuntimeTelemetry | undefined;
}

function arrayLength(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function deriveNetworkMetrics(peers: NetworkPeer[]): NetworkMetrics {
  const telemetry = peers.map(peerRuntime).filter((value): value is NetworkRuntimeTelemetry => Boolean(value));
  const average = (key: keyof NetworkRuntimeTelemetry): number | undefined => {
    const values = telemetry.map(item => asNumber(item[key])).filter((value): value is number => value !== undefined);
    return values.length ? Number((values.reduce((total, value) => total + value, 0) / values.length).toFixed(2)) : undefined;
  };
  const activityCount = peers.reduce((total, peer) => total + arrayLength(asRecord(peer.activity)?.active_tasks), 0);
  const queueDepth = peers.reduce((total, peer) => total + arrayLength(peer.task_queue), 0);
  const logicalCpuCount = telemetry.reduce((total, item) => total + (asNumber(item.logical_cpu_count) || 0), 0);
  return {
    online_peers: peers.filter(peer => peer.online === true).length,
    telemetry_nodes: telemetry.length,
    active_tasks: activityCount,
    queue_depth: queueDepth,
    logical_cpu_count: logicalCpuCount,
    system_cpu_percent: average('system_cpu_percent'),
    system_memory_percent: average('system_memory_percent'),
    storage_used_percent: average('storage_used_percent'),
  };
}

export function useNetwork() {
  const { authorizedFetch, user } = useSession();
  const peersPayload = useState<NetworkPeersResponse>('network:peers', () => ({ peers: [] }));
  const tasksPayload = useState<NetworkTasksResponse>('network:tasks', () => ({ active: [], recent: [], workloads: [] }));
  const loading = useState<boolean>('network:loading', () => false);
  const error = useState<string>('network:error', () => '');
  const lastUpdatedAt = useState<string | null>('network:last-updated', () => null);

  const peers = computed(() => peersPayload.value.peers || []);
  const roleGroups = computed(() => {
    const groups = new Map<string, number>();
    for (const peer of peers.value) for (const role of peerRoles(peer)) groups.set(role, (groups.get(role) || 0) + 1);
    return [...groups.entries()].map(([role, count]) => ({ role, count })).sort((a, b) => b.count - a.count);
  });
  const outdatedCount = computed(() => peers.value.filter(peer => peer.outdated).length);
  const currentCount = computed(() => peers.value.filter(peer => ['current', 'server'].includes(String(peer.version_status || ''))).length);
  const onlineCount = computed(() => peers.value.filter(peer => peer.online === true).length);
  const networkMetrics = computed(() => peersPayload.value.metrics || deriveNetworkMetrics(peers.value));

  async function loadNetwork(force = false): Promise<void> {
    loading.value = true;
    error.value = '';
    const scope = String(user.value?.id || 'current');
    try {
      const [nextPeers, nextTasks] = await Promise.all([
        clientCache.remember(`network:${scope}:peers`, () => authorizedFetch<NetworkPeersResponse>('/jobs/network/peers'), { ttl: 10_000, force }),
        clientCache.remember(`network:${scope}:tasks`, () => authorizedFetch<NetworkTasksResponse>('/jobs/network/tasks'), { ttl: 6_000, force }),
      ]);
      peersPayload.value = nextPeers;
      tasksPayload.value = nextTasks;
      lastUpdatedAt.value = String(nextPeers.updated_utc || nextPeers.metrics?.updated_utc || new Date().toISOString());
    } catch (failure) {
      error.value = 'La télémétrie réseau est momentanément indisponible.';
      throw failure;
    } finally {
      loading.value = false;
    }
  }

  return { peersPayload, tasksPayload, peers, roleGroups, outdatedCount, currentCount, onlineCount, networkMetrics, loading, error, lastUpdatedAt, loadNetwork };
}
