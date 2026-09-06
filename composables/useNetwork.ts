import type { NetworkPeersResponse, NetworkTasksResponse } from '~/types/api';
import { clientCache } from '~/services/cache';
import { peerRoles } from '~/utils/format';

export function useNetwork() {
  const { authorizedFetch, user } = useSession();
  const peersPayload = useState<NetworkPeersResponse>('network:peers', () => ({ peers: [] }));
  const tasksPayload = useState<NetworkTasksResponse>('network:tasks', () => ({ active: [], recent: [], workloads: [] }));
  const loading = useState<boolean>('network:loading', () => false);
  const error = useState<string>('network:error', () => '');

  const peers = computed(() => peersPayload.value.peers || []);
  const roleGroups = computed(() => {
    const groups = new Map<string, number>();
    for (const peer of peers.value) for (const role of peerRoles(peer)) groups.set(role, (groups.get(role) || 0) + 1);
    return [...groups.entries()].map(([role, count]) => ({ role, count })).sort((a, b) => b.count - a.count);
  });
  const outdatedCount = computed(() => peers.value.filter(peer => peer.outdated).length);
  const currentCount = computed(() => peers.value.filter(peer => !peer.outdated).length);

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
    } catch (failure) {
      error.value = 'La télémétrie réseau est momentanément indisponible.';
      throw failure;
    } finally {
      loading.value = false;
    }
  }

  return { peersPayload, tasksPayload, peers, roleGroups, outdatedCount, currentCount, loading, error, loadNetwork };
}
