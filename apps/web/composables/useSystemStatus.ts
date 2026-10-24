import type { SystemStatus, UpdateManifest } from '~/types/api';
import { clientCache } from '~/services/cache';
import { translate } from '~/utils/i18n';

export function useSystemStatus() {
  const config = useRuntimeConfig();
  const status = useState<SystemStatus | null>('public:status', () => null);
  const manifest = useState<UpdateManifest | null>('public:manifest', () => null);
  const loading = useState<boolean>('public:status-loading', () => false);
  const error = useState<string>('public:status-error', () => '');

  async function refresh(force = false): Promise<void> {
    loading.value = true;
    error.value = '';
    try {
      const [nextStatus, nextManifest] = await Promise.all([
        clientCache.remember('public:status', () => $fetch<SystemStatus>(`${config.public.apiBase}/status`, { retry: 0, timeout: 8_000 }), { ttl: 10_000, force }),
        clientCache.remember('public:manifest', () => $fetch<UpdateManifest>(String(config.public.updateManifestUrl), { retry: 0, timeout: 8_000 }), { ttl: 30_000, force }).catch(() => null),
      ]);
      status.value = nextStatus;
      manifest.value = nextManifest;
    } catch {
      status.value = {
        status: 'unavailable', checkedAt: new Date().toISOString(),
        release: {
          release_channel: String(config.public.releaseChannel || 'dev'),
          release_version: String(config.public.releaseVersion || 'unknown'),
          release_build: String(config.public.releaseBuild || 'local'),
        },
        backend: { status: 'unavailable' }, network: { status: 'unavailable', peers: 0, activePeers: 0, outdatedPeers: 0 },
        blockchain: { status: 'unknown', network: 'unknown', configured: false },
      };
      error.value = translate('errors.statusLoad');
    } finally {
      loading.value = false;
    }
  }

  return { status, manifest, loading, error, refresh };
}
