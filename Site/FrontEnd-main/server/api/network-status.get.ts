export default defineEventHandler(async () => {
  const config = useRuntimeConfig();
  const orchestratorUrl = String(config.public.orchestratorUrl || '').replace(/\/$/, '');
  const localOrchestratorUrl = 'http://127.0.0.1:46100';
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

  let reachableUrl = orchestratorUrl;
  try {
    await $fetch(`${reachableUrl}/healthz`, { timeout: 2500 });
    status.ok = true;
  } catch {
    try {
      reachableUrl = localOrchestratorUrl;
      await $fetch(`${reachableUrl}/healthz`, { timeout: 2500 });
      status.ok = true;
    } catch {
      return status;
    }
  }

  try {
    const peers = await $fetch<{ count?: number; peers?: unknown[] }>(`${reachableUrl}/peers`, {
      headers,
      timeout: 2500,
    });
    const peerCount = Array.isArray(peers.peers) ? peers.peers.length : Number(peers.count || 0);
    status.connectedNodes = Math.max(0, peerCount);
  } catch {
    status.connectedNodes = 1;
  }

  return status;
});
