<template>
  <div class="app-page">
    <header class="app-page-head"><div><span class="eyebrow">Infrastructure · flux vivant</span><h1 class="page-title">Réseau</h1><p class="page-intro">Les projets de votre émetteur et les machines disponibles, actualisés automatiquement toutes les quelques secondes.</p></div><div class="cluster"><UiStatusBadge v-if="emitterNodeId" status="operational" :label="'Émetteur · ' + compactIdentifier(emitterNodeId, 14, 6)" /><UiButton to="/nodes" variant="secondary" icon="nodes">Voir les machines</UiButton><UiButton variant="secondary" icon="refresh" :loading="loading" @click="loadNetwork(true)">Rafraîchir</UiButton></div></header>
    <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
    <NetworkSummary :connected-count="onlineCount" :role-groups="onlineRoleGroups" :outdated-count="outdatedCount" />
    <LiveNetworkMap :total-nodes="onlinePeers.length" :active-nodes="onlineCount" :active-workloads="activeCount" :role-groups="onlineRoleGroups" :network-metrics="networkMetrics" :last-updated-at="lastUpdatedAt" />
    <section class="network-flow surface">
      <div class="network-flow__copy"><span class="eyebrow">Lecture du réseau</span><h2>Du projet au résultat, par étape.</h2><p>Les machines sont regroupées par rôle. Le détail d’un projet ou d’une machine s’ouvre uniquement lorsqu’il devient utile.</p></div>
      <div class="network-flow__diagram"><div v-for="(stage,index) in flow" :key="stage.title"><span><UiIcon :name="stage.icon"/></span><strong>{{ stage.title }}</strong><small>{{ stage.detail }}</small><UiIcon v-if="index < flow.length - 1" name="arrow" class="network-flow__arrow"/></div></div>
    </section>
    <UiCard title="Projets en cours" description="Chaque projet reste lisible, même lorsque plusieurs machines travaillent ensemble.">
      <template #actions><UiStatusBadge :status="activeCount ? 'running' : 'completed'" :label="activeCount ? `${activeCount} actif${activeCount > 1 ? 's' : ''}` : 'Aucun projet actif'" /></template>
      <div v-if="loading && !workloads.length" class="workload-loading"><div v-for="n in 4" :key="n" class="skeleton"></div></div>
      <UiEmptyState v-else-if="!workloads.length" title="Aucun projet en cours" description="Les projets apparaîtront ici dès que le réseau en recevra un nouveau." icon="network" />
      <div v-else class="workload-list">
        <details v-for="workload in workloads" :key="workload.work_id">
          <summary><span class="workload-list__icon"><UiIcon name="layers"/></span><div class="workload-list__identity"><strong>{{ compactIdentifier(workload.work_id, 16, 7) }}</strong><small>{{ workload.workload || workload.kind || 'compute' }} · {{ formatDate(workload.updated_at) }}</small></div><UiStatusBadge :status="workload.status"/><div class="workload-list__counts"><span><strong>{{ workload.completed }}</strong><small>terminés</small></span><span><strong>{{ workload.active }}</strong><small>actifs</small></span><span><strong>{{ workload.failed }}</strong><small>échecs</small></span><span><strong>{{ workload.total }}</strong><small>total</small></span></div><UiIcon name="chevron" class="workload-list__chevron"/></summary>
          <div class="workload-detail"><div v-if="!workload.subtasks?.length" class="workload-detail__empty">Aucun détail de partie n’est encore disponible.</div><div v-else class="table-wrap"><table class="data-table"><thead><tr><th>Partie</th><th>Étape</th><th>Machine</th><th>Avancement</th><th>Détail</th></tr></thead><tbody><tr v-for="(task,index) in workload.subtasks.slice(0,80)" :key="String(task.task_id || task.taskId || index)"><td class="mono">{{ compactIdentifier(String(task.task_id || task.taskId || `fragment-${index}`),12,6) }}</td><td>{{ task.stage || 'calcul' }}</td><td class="mono">{{ compactIdentifier(String(task.handled_by || task.handledBy || 'En attente'),10,5) }}</td><td><UiStatusBadge :status="String(task.status || 'unknown')"/></td><td class="task-error"> <details v-if="taskFailure(task)"><summary>Voir</summary><pre>{{ compactJobError(taskFailure(task), 6_000) }}</pre></details><span v-else>—</span></td></tr></tbody></table></div></div>
        </details>
      </div>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import type { NetworkSubtask } from '~/types/api';
import { compactIdentifier, formatDate } from '~/utils/format';
import { compactJobError } from '~/utils/jobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const network = useNetwork();
const { onlinePeers, onlineRoleGroups, outdatedCount, onlineCount, loading, error, tasksPayload, networkMetrics, lastUpdatedAt, loadNetwork } = network;
const workloads = computed(() => (tasksPayload.value.workloads || []).filter(item => Number(item.active || 0) > 0));
const emitterNodeId = computed(() => tasksPayload.value.emitter_node_id || workloads.value.find(item => item.emitter_node_id)?.emitter_node_id || '');
const activeCount = computed(() => workloads.value.length);
function taskFailure(task: NetworkSubtask): string { return String(task.failureDetail || task.failure_detail || task.error || task.error_message || task.traceback || task.error_traceback || ''); }
const flow = [{ title: 'Nouveau projet', detail: 'Projet reçu', icon: 'upload' }, { title: 'Répartition', detail: 'Machines choisies', icon: 'layers' }, { title: 'Calcul', detail: 'Parties traitées', icon: 'processor' }, { title: 'Contrôle', detail: 'Résultats comparés', icon: 'shield' }, { title: 'Résultat', detail: 'Réponse réunie', icon: 'result' }];
let refreshTimer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  loadNetwork().catch(() => undefined);
  refreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible') loadNetwork().catch(() => undefined);
  }, 5_000);
});
onBeforeUnmount(() => { if (refreshTimer) clearInterval(refreshTimer); });
useSeoMeta({ title: 'Réseau — Silicium' });
</script>

<style scoped>
.network-flow{display:grid;grid-template-columns:.75fr 1.25fr;align-items:center;gap:2rem;padding:1.5rem}.network-flow__copy h2{margin:.55rem 0 0;font-size:1.55rem;line-height:1.13;letter-spacing:-.045em}.network-flow__copy p{margin:.7rem 0 0;color:var(--ink-600);font-size:.7rem;line-height:1.65}.network-flow__diagram{display:grid;grid-template-columns:repeat(5,1fr);gap:.4rem}.network-flow__diagram>div{position:relative;display:grid;justify-items:center;gap:.4rem;padding:.75rem .35rem;border:1px solid var(--border);border-radius:.75rem;background:white;text-align:center}.network-flow__diagram>div>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.55rem;background:var(--mint-100);color:var(--mint-700)}.network-flow__diagram>div:nth-child(4)>span{background:var(--violet-100);color:var(--violet-600)}.network-flow__diagram svg{width:.85rem}.network-flow__diagram strong{font-size:.58rem}.network-flow__diagram small{color:var(--ink-500);font-size:.5rem}.network-flow__arrow{position:absolute;top:50%;right:-.65rem;z-index:2;width:.7rem!important;transform:translateY(-50%);color:var(--ink-400)}
.workload-loading{display:grid;gap:.65rem;padding:1rem}.workload-loading .skeleton{height:4.2rem}.workload-list details{border-bottom:1px solid var(--border)}.workload-list details:last-child{border:0}.workload-list summary{display:grid;grid-template-columns:auto minmax(170px,1fr) auto minmax(270px,.9fr) auto;align-items:center;gap:.8rem;padding:1rem 1.2rem;cursor:pointer;list-style:none}.workload-list summary::-webkit-details-marker{display:none}.workload-list__icon{display:grid;width:2.2rem;height:2.2rem;place-items:center;border-radius:.6rem;background:var(--mint-100);color:var(--mint-700)}.workload-list__icon svg{width:.9rem}.workload-list__identity strong,.workload-list__identity small{display:block}.workload-list__identity strong{font-size:.72rem}.workload-list__identity small{margin-top:.2rem;color:var(--ink-500);font-size:.58rem}.workload-list__counts{display:grid;grid-template-columns:repeat(4,1fr);gap:.35rem}.workload-list__counts span{padding:.4rem .5rem;border-radius:.5rem;background:var(--surface-soft);text-align:center}.workload-list__counts strong,.workload-list__counts small{display:block}.workload-list__counts strong{font-size:.72rem}.workload-list__counts small{margin-top:.12rem;color:var(--ink-500);font-size:.49rem}.workload-list__chevron{width:.85rem;color:var(--ink-500);transition:transform .15s}.workload-list details[open] .workload-list__chevron{transform:rotate(90deg)}.workload-detail{padding:0 1.2rem 1rem;background:var(--surface-soft)}.workload-detail__empty{padding:1rem;color:var(--ink-500);font-size:.65rem;text-align:center}
.task-error{min-width:180px;color:var(--red-600);font-size:.62rem}.task-error details{border:0}.task-error summary{display:block;padding:0;color:var(--red-600);font-size:.62rem;font-weight:700;cursor:pointer;list-style:none}.task-error summary::-webkit-details-marker{display:none}.task-error pre{max-width:32rem;margin:.5rem 0 0;padding:.65rem;overflow:auto;border:1px solid rgba(196,71,71,.16);border-radius:.45rem;background:rgba(255,255,255,.7);color:var(--ink-800);font:500 .58rem/1.5 var(--font-mono);white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:1050px){.network-flow{grid-template-columns:1fr}.workload-list summary{grid-template-columns:auto 1fr auto auto}.workload-list__counts{grid-column:2/-1;grid-row:2}.workload-list__chevron{grid-column:4;grid-row:1}}@media(max-width:620px){.network-flow{padding:1rem}.network-flow__diagram{grid-template-columns:1fr 1fr}.network-flow__diagram>div:last-child{grid-column:1/-1}.network-flow__arrow{display:none}.workload-list summary{grid-template-columns:auto 1fr auto;padding:.85rem}.workload-list summary>:deep(.status-badge){grid-column:2}.workload-list__counts{grid-column:1/-1}.workload-list__chevron{grid-column:3}.workload-detail{padding:0 .5rem .7rem}}
</style>
