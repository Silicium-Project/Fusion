<template>
  <div class="app-page">
    <header class="app-page-head"><div><span class="eyebrow">Infrastructure</span><h1 class="page-title">Réseau</h1><p class="page-intro">Une vue agrégée des rôles et des travaux qui reste exploitable avec des milliers de nœuds.</p></div><div class="cluster"><UiButton to="/nodes" variant="secondary" icon="nodes">Voir les nœuds</UiButton><UiButton variant="secondary" icon="refresh" :loading="loading" @click="loadNetwork(true)">Rafraîchir</UiButton></div></header>
    <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
    <NetworkSummary :peers="peers" :role-groups="roleGroups" :outdated-count="outdatedCount" />
    <section class="network-flow surface">
      <div class="network-flow__copy"><span class="eyebrow">Lecture du réseau</span><h2>De l’entrée au résultat, sans graphe de nœuds.</h2><p>Le volume se lit par groupes. Le détail d’un travail ou d’un nœud s’ouvre seulement lorsqu’il devient pertinent.</p></div>
      <div class="network-flow__diagram"><div v-for="(stage,index) in flow" :key="stage.title"><span><UiIcon :name="stage.icon"/></span><strong>{{ stage.title }}</strong><small>{{ stage.detail }}</small><UiIcon v-if="index < flow.length - 1" name="arrow" class="network-flow__arrow"/></div></div>
    </section>
    <UiCard title="Travaux réseau" description="Un travail agrège ses sous-tâches ; il ne devient pas un nuage de points.">
      <template #actions><UiStatusBadge :status="activeCount ? 'running' : 'completed'" :label="activeCount ? `${activeCount} actif${activeCount > 1 ? 's' : ''}` : 'Aucun travail actif'" /></template>
      <div v-if="loading && !workloads.length" class="workload-loading"><div v-for="n in 4" :key="n" class="skeleton"></div></div>
      <UiEmptyState v-else-if="!workloads.length" title="Aucun travail réseau" description="Les exécutions apparaîtront ici dès qu’elles seront publiées dans le registre RPC." icon="network" />
      <div v-else class="workload-list">
        <details v-for="workload in workloads" :key="workload.work_id">
          <summary><span class="workload-list__icon"><UiIcon name="layers"/></span><div class="workload-list__identity"><strong>{{ compactIdentifier(workload.work_id, 16, 7) }}</strong><small>{{ workload.workload || workload.kind || 'compute' }} · {{ formatDate(workload.updated_at) }}</small></div><UiStatusBadge :status="workload.status"/><div class="workload-list__counts"><span><strong>{{ workload.completed }}</strong><small>terminés</small></span><span><strong>{{ workload.active }}</strong><small>actifs</small></span><span><strong>{{ workload.failed }}</strong><small>échecs</small></span><span><strong>{{ workload.total }}</strong><small>total</small></span></div><UiIcon name="chevron" class="workload-list__chevron"/></summary>
          <div class="workload-detail"><div v-if="!workload.subtasks?.length" class="workload-detail__empty">Aucun détail de sous-tâche publié.</div><div v-else class="table-wrap"><table class="data-table"><thead><tr><th>Sous-tâche</th><th>Étape</th><th>Nœud</th><th>Statut</th></tr></thead><tbody><tr v-for="(task,index) in workload.subtasks.slice(0,80)" :key="String(task.task_id || task.taskId || index)"><td class="mono">{{ compactIdentifier(String(task.task_id || task.taskId || `fragment-${index}`),12,6) }}</td><td>{{ task.stage || 'calcul' }}</td><td class="mono">{{ compactIdentifier(String(task.handled_by || task.handledBy || 'En attente'),10,5) }}</td><td><UiStatusBadge :status="String(task.status || 'unknown')"/></td></tr></tbody></table></div></div>
        </details>
      </div>
    </UiCard>
  </div>
</template>

<script setup lang="ts">
import { compactIdentifier, formatDate } from '~/utils/format';
definePageMeta({ layout: 'app', middleware: 'auth' });
const network = useNetwork();
const { peers, roleGroups, outdatedCount, loading, error, tasksPayload, loadNetwork } = network;
const workloads = computed(() => tasksPayload.value.workloads || []);
const activeCount = computed(() => workloads.value.filter(item => !['completed','failed','cancelled','expired'].includes(item.status)).length);
const flow = [{ title: 'Entrée', detail: 'Charge validée', icon: 'upload' }, { title: 'Orchestration', detail: 'Plan & rôles', icon: 'layers' }, { title: 'Calcul', detail: 'Fragments', icon: 'processor' }, { title: 'Vérification', detail: 'Attestations', icon: 'shield' }, { title: 'Résultat', detail: 'Réassemblage', icon: 'result' }];
onMounted(() => loadNetwork().catch(() => undefined));
useSeoMeta({ title: 'Réseau — Silicium' });
</script>

<style scoped>
.network-flow{display:grid;grid-template-columns:.75fr 1.25fr;align-items:center;gap:2rem;padding:1.5rem}.network-flow__copy h2{margin:.55rem 0 0;font-size:1.55rem;line-height:1.13;letter-spacing:-.045em}.network-flow__copy p{margin:.7rem 0 0;color:var(--ink-600);font-size:.7rem;line-height:1.65}.network-flow__diagram{display:grid;grid-template-columns:repeat(5,1fr);gap:.4rem}.network-flow__diagram>div{position:relative;display:grid;justify-items:center;gap:.4rem;padding:.75rem .35rem;border:1px solid var(--border);border-radius:.75rem;background:white;text-align:center}.network-flow__diagram>div>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.55rem;background:var(--mint-100);color:var(--mint-700)}.network-flow__diagram>div:nth-child(4)>span{background:var(--violet-100);color:var(--violet-600)}.network-flow__diagram svg{width:.85rem}.network-flow__diagram strong{font-size:.58rem}.network-flow__diagram small{color:var(--ink-500);font-size:.5rem}.network-flow__arrow{position:absolute;top:50%;right:-.65rem;z-index:2;width:.7rem!important;transform:translateY(-50%);color:var(--ink-400)}
.workload-loading{display:grid;gap:.65rem;padding:1rem}.workload-loading .skeleton{height:4.2rem}.workload-list details{border-bottom:1px solid var(--border)}.workload-list details:last-child{border:0}.workload-list summary{display:grid;grid-template-columns:auto minmax(170px,1fr) auto minmax(270px,.9fr) auto;align-items:center;gap:.8rem;padding:1rem 1.2rem;cursor:pointer;list-style:none}.workload-list summary::-webkit-details-marker{display:none}.workload-list__icon{display:grid;width:2.2rem;height:2.2rem;place-items:center;border-radius:.6rem;background:var(--mint-100);color:var(--mint-700)}.workload-list__icon svg{width:.9rem}.workload-list__identity strong,.workload-list__identity small{display:block}.workload-list__identity strong{font-size:.72rem}.workload-list__identity small{margin-top:.2rem;color:var(--ink-500);font-size:.58rem}.workload-list__counts{display:grid;grid-template-columns:repeat(4,1fr);gap:.35rem}.workload-list__counts span{padding:.4rem .5rem;border-radius:.5rem;background:var(--surface-soft);text-align:center}.workload-list__counts strong,.workload-list__counts small{display:block}.workload-list__counts strong{font-size:.72rem}.workload-list__counts small{margin-top:.12rem;color:var(--ink-500);font-size:.49rem}.workload-list__chevron{width:.85rem;color:var(--ink-500);transition:transform .15s}.workload-list details[open] .workload-list__chevron{transform:rotate(90deg)}.workload-detail{padding:0 1.2rem 1rem;background:var(--surface-soft)}.workload-detail__empty{padding:1rem;color:var(--ink-500);font-size:.65rem;text-align:center}
@media(max-width:1050px){.network-flow{grid-template-columns:1fr}.workload-list summary{grid-template-columns:auto 1fr auto auto}.workload-list__counts{grid-column:2/-1;grid-row:2}.workload-list__chevron{grid-column:4;grid-row:1}}@media(max-width:620px){.network-flow{padding:1rem}.network-flow__diagram{grid-template-columns:1fr 1fr}.network-flow__diagram>div:last-child{grid-column:1/-1}.network-flow__arrow{display:none}.workload-list summary{grid-template-columns:auto 1fr auto;padding:.85rem}.workload-list summary>:deep(.status-badge){grid-column:2}.workload-list__counts{grid-column:1/-1}.workload-list__chevron{grid-column:3}.workload-detail{padding:0 .5rem .7rem}}
</style>
