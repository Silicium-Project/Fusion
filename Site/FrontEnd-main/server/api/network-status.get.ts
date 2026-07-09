export default defineEventHandler(async () => {
  const config = useRuntimeConfig();
  const orchestratorUrl = String(config.public.orchestratorUrl || '').replace(/\/$/, '');
  const headers: Record<string, string> = {};
  if (config.siliciumMeshKey) {
    headers.Authorization = `Bearer ${config.siliciumMeshKey}`;
  }

  const status = {
    ok: false,
    connectedNodes: null as number | null,
    orchestratorUrl,
    updatedAt: new Date().toISOString(),
  };

  if (!orchestratorUrl) {
    return status;
  }

  try {
    await $fetch(`${orchestratorUrl}/healthz`, { timeout: 2500 });
    status.ok = true;
  } catch {
    return status;
  }

  try {
    const peers = await $fetch<{ count?: number; peers?: unknown[] }>(`${orchestratorUrl}/peers`, {
      headers,
      timeout: 2500,
    });
    const peerCount = Array.isArray(peers.peers) ? peers.peers.length : Number(peers.count || 0);
    status.connectedNodes = Math.max(0, peerCount + 1);
  } catch {
    status.connectedNodes = 1;
  }

  return status;
});
