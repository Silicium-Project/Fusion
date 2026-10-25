<template>
  <div class="app-page">
    <header class="app-page-head">
      <div>
        <span class="eyebrow">{{ t('network.eyebrow') }}</span>
        <h1 class="page-title">{{ t('nav.networkHealth') }}</h1>
        <p class="page-intro">{{ t('network.intro') }}</p>
      </div>
      <div class="cluster">
        <UiStatusBadge
          v-if="emitterNodeId"
          status="operational"
          :label="t('network.emitter', { id: compactIdentifier(emitterNodeId, 14, 6) })"
        /><UiButton to="/nodes" variant="secondary" icon="nodes">{{
          t('network.seeMachines')
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
    <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
    <LiveNetworkMap
      :total-nodes="onlinePeers.length"
      :active-nodes="onlineCount"
      :active-workloads="activeCount"
      :role-groups="onlineRoleGroups"
      :network-metrics="networkMetrics"
      :last-updated-at="lastUpdatedAt"
      :stale="Boolean(error)"
    />
    <UiNotice v-if="queueNotice" tone="warning">
      <span>{{ queueNotice }}</span>
      <ul v-if="queueDiagnostics.length" class="queue-diagnostics">
        <li v-for="item in queueDiagnostics" :key="item.workload">{{ item.message }}</li>
      </ul>
    </UiNotice>
    <section class="network-flow surface">
      <div class="network-flow__copy">
        <span class="eyebrow">{{ t('network.readKicker') }}</span>
        <h2>{{ t('network.readTitle') }}</h2>
        <p>{{ t('network.readText') }}</p>
      </div>
      <div class="network-flow__diagram">
        <div v-for="(stage, index) in flow" :key="index">
          <span><UiIcon :name="stage.icon" /></span><strong>{{ stage.title }}</strong
          ><small>{{ stage.detail }}</small
          ><UiIcon v-if="index < flow.length - 1" name="arrow" class="network-flow__arrow" />
        </div>
      </div>
    </section>
    <UiCard :title="t('network.running')" :description="t('network.runningText')">
      <template #actions
        ><UiStatusBadge
          :status="activeCount ? 'running' : 'completed'"
          :label="
            activeCount ? t('network.active', { count: activeCount }) : t('network.noActive')
          "
      /></template>
      <div v-if="loading && !workloads.length" class="workload-loading">
        <div v-for="n in 4" :key="n" class="skeleton"></div>
      </div>
      <UiEmptyState
        v-else-if="!workloads.length"
        :title="t('network.emptyTitle')"
        :description="t('network.emptyText')"
        icon="network"
      />
      <div v-else class="workload-list">
        <details v-for="workload in workloads" :key="workload.work_id">
          <summary>
            <span class="workload-list__icon"><UiIcon name="layers" /></span>
            <div class="workload-list__identity">
              <strong>{{ compactIdentifier(workload.work_id, 16, 7) }}</strong
              ><small
                >{{ workload.workload || workload.kind || 'compute' }} ·
                {{ formatDate(workload.updated_at) }}</small
              >
            </div>
            <UiStatusBadge :status="workload.status" />
            <div class="workload-list__counts">
              <span
                ><strong>{{ workload.completed }}</strong
                ><small>{{ t('network.done') }}</small></span
              ><span
                ><strong>{{ workload.active }}</strong
                ><small>{{ t('network.activeShort') }}</small></span
              ><span
                ><strong>{{ workload.failed }}</strong
                ><small>{{ t('network.failures') }}</small></span
              ><span
                ><strong>{{ workload.total }}</strong
                ><small>{{ t('network.total') }}</small></span
              >
            </div>
            <UiIcon name="chevron" class="workload-list__chevron" />
          </summary>
          <div class="workload-detail">
            <div v-if="!workload.subtasks?.length" class="workload-detail__empty">
              {{ t('network.noDetail') }}
            </div>
            <div v-else class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>{{ t('network.part') }}</th>
                    <th>{{ t('network.stage') }}</th>
                    <th>{{ t('network.machine') }}</th>
                    <th>{{ t('network.progress') }}</th>
                    <th>{{ t('network.detail') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(task, index) in workload.subtasks.slice(0, 80)"
                    :key="String(task.task_id || task.taskId || index)"
                  >
                    <td class="mono">
                      {{
                        compactIdentifier(
                          String(task.task_id || task.taskId || `fragment-${index}`),
                          12,
                          6,
                        )
                      }}
                    </td>
                    <td>{{ task.stage || t('network.computeStage') }}</td>
                    <td class="mono">
                      {{
                        compactIdentifier(
                          String(task.handled_by || task.handledBy || t('network.waiting')),
                          10,
                          5,
                        )
                      }}
                    </td>
                    <td><UiStatusBadge :status="String(task.status || 'unknown')" /></td>
                    <td class="task-error">
                      <details v-if="taskFailure(task)">
                        <summary>{{ t('network.see') }}</summary>
                        <pre>{{ compactJobError(taskFailure(task), 6_000) }}</pre>
                      </details>
                      <span v-else>—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </details>
      </div>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import type { NetworkQueueWorkloadDiagnostic, NetworkSubtask } from '~/types/api';
import { compactIdentifier, formatDate } from '~/utils/format';
import { compactJobError } from '~/utils/jobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const { t, tl } = useI18n();
const network = useNetwork();
const {
  onlinePeers,
  onlineRoleGroups,
  outdatedCount,
  onlineCount,
  loading,
  error,
  workloads: networkWorkloads,
  emitterNodeId: payloadEmitterNodeId,
  networkMetrics,
  lastUpdatedAt,
  tasksPayload,
  loadNetwork,
} = network;
const workloads = computed(() =>
  networkWorkloads.value.filter((item) => Number(item.active || 0) > 0),
);
function queueWorkloadMessage(item: NetworkQueueWorkloadDiagnostic): string {
  const values = {
    workload: item.workload,
    count: Number(item.queued || 0),
    online: Number(item.online_compute_workers || 0),
    compatible: Number(item.compatible_workers || 0),
    seconds: Number(item.oldest_wait_seconds || 0),
  };
  switch (item.reason) {
    case 'no_compute_workers':
      return t('network.queueWorkloadNoWorkers', values);
    case 'no_compatible_workers':
      return t('network.queueWorkloadNoCompatible', values);
    case 'workers_not_claiming':
      return t('network.queueWorkloadNotClaiming', values);
    default:
      return t('network.queueWorkloadUnknown', values);
  }
}
const queueDiagnostics = computed(() =>
  (tasksPayload.value.queue?.workload_diagnostics || []).map((item) => ({
    workload: item.workload,
    message: queueWorkloadMessage(item),
  })),
);
const queueNotice = computed(() => {
  const queue = tasksPayload.value.queue;
  const count = Number(queue?.queued || 0);
  if (!count) return '';
  const values = {
    count,
    online: Number(queue?.online_compute_workers || 0),
    compatible: Number(queue?.compatible_workers || 0),
    workloads: (queue?.workloads || []).join(', ') || '—',
    seconds: Number(queue?.oldest_wait_seconds || 0),
  };
  switch (queue?.reason) {
    case 'no_compute_workers':
      return t('network.queueNoWorkers', values);
    case 'no_compatible_workers':
      return t('network.queueNoCompatible', values);
    case 'workers_not_claiming':
      return t('network.queueNotClaiming', values);
    case 'mixed_workload_blockers':
      return t('network.queueMixed', values);
    default:
      return t('network.queueUnknown', values);
  }
});
const emitterNodeId = computed(
  () =>
    payloadEmitterNodeId.value ||
    workloads.value.find((item) => item.emitter_node_id)?.emitter_node_id ||
    '',
);
const activeCount = computed(() => workloads.value.length);
function taskFailure(task: NetworkSubtask): string {
  return String(
    task.failureDetail ||
      task.failure_detail ||
      task.error ||
      task.error_message ||
      task.traceback ||
      task.error_traceback ||
      '',
  );
}
const flowIcons = ['upload', 'layers', 'processor', 'shield', 'result'];
const flow = computed(() =>
  tl<{ title: string; detail: string }>('network.flow').map((stage, index) => ({
    ...stage,
    icon: flowIcons[index] || 'layers',
  })),
);
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
useSeoMeta({ title: () => `${t('nav.networkHealth')} — Silicium` });
</script>

<style scoped>
.network-flow {
  display: grid;
  grid-template-columns: 0.75fr 1.25fr;
  align-items: center;
  gap: 2rem;
  padding: 1.5rem;
}
.network-flow__copy h2 {
  margin: 0.55rem 0 0;
  font-size: 1.55rem;
  line-height: 1.13;
  letter-spacing: -0.045em;
}
.network-flow__copy p {
  margin: 0.7rem 0 0;
  color: var(--ink-600);
  font-size: 1rem;
  line-height: 1.65;
}
.network-flow__diagram {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.4rem;
}
.network-flow__diagram > div {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 0.4rem;
  padding: 0.75rem 0.35rem;
  border: 1px solid var(--border);
  border-radius: 0.75rem;
  background: white;
  text-align: center;
}
.network-flow__diagram > div > span {
  display: grid;
  width: 2rem;
  height: 2rem;
  place-items: center;
  border-radius: 0.55rem;
  background: var(--mint-100);
  color: var(--mint-700);
}
.network-flow__diagram > div:nth-child(4) > span {
  background: var(--violet-100);
  color: var(--violet-600);
}
.network-flow__diagram svg {
  width: 0.85rem;
}
.network-flow__diagram strong {
  font-size: 0.9375rem;
}
.network-flow__diagram small {
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.network-flow__arrow {
  position: absolute;
  top: 50%;
  right: -0.65rem;
  z-index: 2;
  width: 0.7rem !important;
  transform: translateY(-50%);
  color: var(--ink-400);
}
.queue-diagnostics {
  display: grid;
  gap: 0.3rem;
  margin: 0.55rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.9375rem;
  line-height: 1.5;
}
.workload-loading {
  display: grid;
  gap: 0.65rem;
  padding: 1rem;
}
.workload-loading .skeleton {
  height: 4.2rem;
}
.workload-list details {
  border-bottom: 1px solid var(--border);
}
.workload-list details:last-child {
  border: 0;
}
.workload-list summary {
  display: grid;
  grid-template-columns: auto minmax(170px, 1fr) auto minmax(270px, 0.9fr) auto;
  align-items: center;
  gap: 0.8rem;
  padding: 1rem 1.2rem;
  cursor: pointer;
  list-style: none;
}
.workload-list summary::-webkit-details-marker {
  display: none;
}
.workload-list__icon {
  display: grid;
  width: 2.2rem;
  height: 2.2rem;
  place-items: center;
  border-radius: 0.6rem;
  background: var(--mint-100);
  color: var(--mint-700);
}
.workload-list__icon svg {
  width: 0.9rem;
}
.workload-list__identity strong,
.workload-list__identity small {
  display: block;
}
.workload-list__identity strong {
  font-size: 0.9375rem;
}
.workload-list__identity small {
  margin-top: 0.2rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.workload-list__counts {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.35rem;
}
.workload-list__counts span {
  padding: 0.4rem 0.5rem;
  border-radius: 0.5rem;
  background: var(--surface-soft);
  text-align: center;
}
.workload-list__counts strong,
.workload-list__counts small {
  display: block;
}
.workload-list__counts strong {
  font-size: 0.9375rem;
}
.workload-list__counts small {
  margin-top: 0.12rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
}
.workload-list__chevron {
  width: 0.85rem;
  color: var(--ink-500);
  transition: transform 0.15s;
}
.workload-list details[open] .workload-list__chevron {
  transform: rotate(90deg);
}
.workload-detail {
  padding: 0 1.2rem 1rem;
  background: var(--surface-soft);
}
.workload-detail__empty {
  padding: 1rem;
  color: var(--ink-500);
  font-size: 0.9375rem;
  text-align: center;
}
.task-error {
  min-width: 180px;
  color: var(--red-600);
  font-size: 0.9375rem;
}
.task-error details {
  border: 0;
}
.task-error summary {
  display: block;
  padding: 0;
  color: var(--red-600);
  font-size: 0.9375rem;
  font-weight: 700;
  cursor: pointer;
  list-style: none;
}
.task-error summary::-webkit-details-marker {
  display: none;
}
.task-error pre {
  max-width: 32rem;
  margin: 0.5rem 0 0;
  padding: 0.65rem;
  overflow: auto;
  border: 1px solid rgba(196, 71, 71, 0.16);
  border-radius: 0.45rem;
  background: rgba(255, 255, 255, 0.7);
  color: var(--ink-800);
  font: 500 0.9375rem/1.5 var(--font-mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
@media (max-width: 1050px) {
  .network-flow {
    grid-template-columns: 1fr;
  }
  .workload-list summary {
    grid-template-columns: auto 1fr auto auto;
  }
  .workload-list__counts {
    grid-column: 2/-1;
    grid-row: 2;
  }
  .workload-list__chevron {
    grid-column: 4;
    grid-row: 1;
  }
}
@media (max-width: 620px) {
  .network-flow {
    padding: 1rem;
  }
  .network-flow__diagram {
    grid-template-columns: 1fr 1fr;
  }
  .network-flow__diagram > div:last-child {
    grid-column: 1/-1;
  }
  .network-flow__arrow {
    display: none;
  }
  .workload-list summary {
    grid-template-columns: auto 1fr auto;
    padding: 0.85rem;
  }
  .workload-list summary > :deep(.status-badge) {
    grid-column: 2;
  }
  .workload-list__counts {
    grid-column: 1/-1;
  }
  .workload-list__chevron {
    grid-column: 3;
  }
  .workload-detail {
    padding: 0 0.5rem 0.7rem;
  }
}
</style>
