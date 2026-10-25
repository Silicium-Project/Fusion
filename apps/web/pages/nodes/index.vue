<template>
  <div class="app-page">
    <header class="app-page-head">
      <div>
        <span class="eyebrow">{{ t('nav.resources') }}</span>
        <h1 class="page-title">{{ t('observability.worker.nodes') }}</h1>
        <p class="page-intro">{{ t('nodes.intro') }}</p>
      </div>
      <div class="cluster">
        <UiButton to="/download" variant="secondary" icon="download">{{
          t('common.installNode')
        }}</UiButton
        ><UiButton
          variant="secondary"
          icon="refresh"
          :loading="loading"
          @click="loadNetwork(true)"
          >{{ t('common.refresh') }}</UiButton
        >
      </div>
    </header>
    <section class="metric-grid">
      <MetricCard
        :label="t('nodes.observed')"
        :value="peers.length"
        :detail="t('nodes.inRegistry')"
        icon="nodes"
        tone="ink"
      /><MetricCard
        :label="t('nodes.online')"
        :value="onlineCount"
        :detail="t('nodes.heartbeat')"
        icon="activity"
        tone="mint"
      /><MetricCard
        :label="t('nodes.current')"
        :value="currentCount"
        :detail="t('nodes.compatible')"
        icon="check"
        tone="mint"
      /><MetricCard
        :label="t('nodes.toUpdate')"
        :value="outdatedCount"
        :detail="t('nodes.versionOrBuild')"
        icon="download"
        :tone="outdatedCount ? 'amber' : 'mint'"
      />
    </section>
    <UiCard>
      <template #header
        ><div class="nodes-toolbar">
          <div class="nodes-search">
            <UiIcon name="search" /><input
              v-model.trim="search"
              type="search"
              maxlength="200"
              :placeholder="t('nodes.search')"
              :aria-label="t('nodes.searchAria')"
            />
          </div>
          <select v-model="role" class="select" :aria-label="t('nodes.roleFilter')">
            <option value="all">{{ t('nodes.allRoles') }}</option>
            <option v-for="group in roleGroups" :key="group.role" :value="group.role">
              {{ group.role }} ({{ group.count }})
            </option></select
          ><select v-model="versionState" class="select" :aria-label="t('nodes.versionFilter')">
            <option value="all">{{ t('nodes.allVersions') }}</option>
            <option value="current">{{ t('nodes.current') }}</option>
            <option value="outdated">{{ t('nodes.updateRequired') }}</option>
          </select>
        </div></template
      >
      <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
      <div v-if="loading && !peers.length" class="node-loading">
        <div v-for="n in 6" :key="n" class="skeleton"></div>
      </div>
      <UiEmptyState
        v-else-if="!filtered.length"
        :title="t('nodes.emptyTitle')"
        :description="t('nodes.emptyText')"
        icon="nodes"
      />
      <div v-else class="table-wrap">
        <table class="data-table nodes-table">
          <thead>
            <tr>
              <th>{{ t('nodes.machine') }}</th>
              <th>{{ t('nodes.rolesColumn') }}</th>
              <th>{{ t('nodes.version') }}</th>
              <th>{{ t('nodes.channel') }}</th>
              <th>{{ t('nodes.state') }}</th>
              <th>{{ t('nodes.metrics') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="peer in visiblePeers" :key="peerId(peer)">
              <td>
                <div class="node-identity">
                  <span><UiIcon name="processor" /></span>
                  <div>
                    <strong>{{ peerId(peer) }}</strong
                    ><small>{{
                      peer.last_seen_utc || peer.lastSeenUtc
                        ? t('nodes.seen', {
                            date: formatDate(String(peer.last_seen_utc || peer.lastSeenUtc)),
                          })
                        : t('nodes.neverSeen')
                    }}</small>
                  </div>
                </div>
              </td>
              <td>
                <div class="role-chips">
                  <span v-for="peerRole in peerRoles(peer)" :key="peerRole">{{ peerRole }}</span
                  ><span v-if="!peerRoles(peer).length" class="role-chips__empty">{{
                    t('nodes.notSet')
                  }}</span>
                </div>
              </td>
              <td class="mono">{{ peer.app_version || t('nodes.versionNotSet') }}</td>
              <td>{{ peer.release_channel || t('common.unknown') }}</td>
              <td><UiStatusBadge :status="peerAvailability(peer)" /></td>
              <td class="node-metrics">
                <span>{{ peerMetricSummary(peer) }}</span
                ><NuxtLink :to="{ path: '/workers/overview', query: { node: peerId(peer) } }"
                  >{{ t('observability.worker.open') }} →</NuxtLink
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer v-if="filtered.length > pageSize" class="nodes-pagination">
        <span>{{
          t('nodes.range', {
            from: start + 1,
            to: Math.min(start + pageSize, filtered.length),
            total: filtered.length,
          })
        }}</span>
        <div>
          <UiButton variant="secondary" size="small" :disabled="page === 1" @click="page--">{{
            t('common.previous')
          }}</UiButton
          ><UiButton
            variant="secondary"
            size="small"
            :disabled="start + pageSize >= filtered.length"
            @click="page++"
            >{{ t('common.next') }}</UiButton
          >
        </div>
      </footer>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import type { NetworkPeer, NetworkRuntimeTelemetry } from '~/types/api';
import { formatDate, peerAvailability, peerId, peerRoles } from '~/utils/format';
definePageMeta({ layout: 'app', middleware: 'auth' });
const { t } = useI18n();
const network = useNetwork();
const {
  peers,
  onlinePeers,
  onlineRoleGroups,
  roleGroups,
  outdatedCount,
  currentCount,
  onlineCount,
  loading,
  error,
  loadNetwork,
} = network;
const search = ref('');
const role = ref('all');
const versionState = ref('all');
const page = ref(1);
const pageSize = 25;
const filtered = computed(() =>
  peers.value
    .filter((peer) => {
      const query = search.value.toLowerCase();
      const matchesQuery =
        !query ||
        `${peerId(peer)} ${peerRoles(peer).join(' ')} ${peer.app_version || ''}`
          .toLowerCase()
          .includes(query);
      const matchesRole = role.value === 'all' || peerRoles(peer).includes(role.value);
      const matchesVersion =
        versionState.value === 'all' ||
        (versionState.value === 'outdated'
          ? Boolean(peer.outdated)
          : ['current', 'server'].includes(String(peer.version_status || '')));
      return matchesQuery && matchesRole && matchesVersion;
    })
    .sort((a, b) => peerId(a).localeCompare(peerId(b))),
);
const start = computed(() => (page.value - 1) * pageSize);
const visiblePeers = computed(() => filtered.value.slice(start.value, start.value + pageSize));
function peerRuntime(peer: NetworkPeer): NetworkRuntimeTelemetry | undefined {
  if (peer.telemetry) return peer.telemetry;
  const metrics = peer.metrics && typeof peer.metrics === 'object' ? peer.metrics : undefined;
  if (metrics?.runtime) return metrics.runtime;
  const activity = peer.activity && typeof peer.activity === 'object' ? peer.activity : undefined;
  return activity?.telemetry;
}
function peerMetricSummary(peer: NetworkPeer): string {
  const runtime = peerRuntime(peer);
  if (!runtime) return t('nodes.noTelemetry');
  const parts = [
    Number.isFinite(Number(runtime.system_cpu_percent))
      ? `CPU ${Number(runtime.system_cpu_percent).toFixed(1)}%`
      : '',
    Number.isFinite(Number(runtime.system_memory_percent))
      ? `RAM ${Number(runtime.system_memory_percent).toFixed(1)}%`
      : '',
    Number.isFinite(Number(runtime.storage_used_percent))
      ? `${t('nodes.disk')} ${Number(runtime.storage_used_percent).toFixed(1)}%`
      : '',
  ].filter(Boolean);
  return parts.join(' · ') || t('nodes.partialTelemetry');
}
watch([search, role, versionState], () => {
  page.value = 1;
});
let refreshTimer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  loadNetwork().catch(() => undefined);
  refreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible') loadNetwork().catch(() => undefined);
  }, 5_000);
});
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
useSeoMeta({ title: () => `${t('observability.worker.nodes')} — Silicium` });
</script>

<style scoped>
.node-metrics > span {
  display: block;
}
.node-metrics > a {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  white-space: normal;
  color: var(--mint-700);
  font-size: 1rem;
}

.nodes-toolbar {
  display: flex;
  width: 100%;
  gap: 0.6rem;
}
.nodes-search {
  position: relative;
  min-width: 230px;
  flex: 1;
}
.nodes-search svg {
  position: absolute;
  top: 50%;
  left: 0.8rem;
  width: 0.9rem;
  transform: translateY(-50%);
  color: var(--ink-500);
}
.nodes-search input {
  width: 100%;
  height: 2.45rem;
  padding: 0 0.8rem 0 2.2rem;
  border: 1px solid var(--border);
  border-radius: 0.65rem;
  background: var(--surface-soft);
  font-size: 0.9375rem;
}
.nodes-toolbar .select {
  width: auto;
  min-width: 155px;
  min-height: 2.45rem;
  font-size: 0.9375rem;
}
.node-loading {
  display: grid;
  gap: 0.6rem;
  padding: 1rem;
}
.node-loading .skeleton {
  height: 3.6rem;
}
.nodes-table {
  min-width: 1050px;
}
.node-identity {
  display: flex;
  min-width: 200px;
  align-items: center;
  gap: 0.7rem;
}
.node-identity > span {
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border-radius: 0.55rem;
  background: var(--mint-100);
  color: var(--mint-700);
}
.node-identity svg {
  width: 0.88rem;
}
.node-identity strong,
.node-identity small {
  display: block;
}
.node-identity strong {
  font-size: 0.9375rem;
}
.node-identity small {
  margin-top: 0.18rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.role-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
.role-chips span {
  padding: 0.27rem 0.42rem;
  border-radius: 0.38rem;
  background: var(--ink-100);
  color: var(--ink-700);
  font-size: 0.9375rem;
  text-transform: capitalize;
}
.role-chips .role-chips__empty {
  padding-inline: 0;
  background: transparent;
  color: var(--ink-500);
}
.node-metrics {
  color: var(--ink-600);
  font-size: 0.9375rem;
  white-space: nowrap;
}
.nodes-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.9rem 1.1rem;
  border-top: 1px solid var(--border);
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.nodes-pagination > div {
  display: flex;
  gap: 0.4rem;
}
@media (max-width: 700px) {
  .nodes-toolbar {
    flex-wrap: wrap;
  }
  .nodes-search {
    flex-basis: 100%;
  }
  .nodes-toolbar .select {
    min-width: 130px;
    flex: 1;
  }
}
</style>
