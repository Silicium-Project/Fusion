<template>
  <div class="app-page">
    <header class="app-page-head"><div><span class="eyebrow">Votre espace</span><h1 class="page-title">Accueil</h1><p class="page-intro">Lancez un calcul, suivez vos projets et récupérez vos résultats au même endroit.</p></div><UiButton to="/jobs/new" icon="upload">Nouveau calcul</UiButton></header>
    <UiNotice v-if="loadError" tone="warning">Certaines données ne sont pas disponibles. Vous pouvez continuer à utiliser les autres fonctions.</UiNotice>
    <section class="metric-grid" aria-label="Indicateurs clés">
      <MetricCard label="Mes projets" :value="total" detail="dans votre espace" icon="jobs" tone="ink" />
      <MetricCard label="En cours" :value="runningCount" detail="projets actifs" icon="activity" tone="mint" />
      <MetricCard label="Terminés" :value="completedCount" detail="résultats disponibles" icon="check" tone="violet" />
      <MetricCard label="Machines en ligne" :value="onlineCount" :detail="`${outdatedCount} à mettre à jour`" icon="nodes" :tone="outdatedCount ? 'amber' : 'mint'" />
    </section>
    <div class="two-column">
      <UiCard title="Mes projets récents" description="Vos derniers calculs et leur progression.">
        <template #actions><UiButton to="/jobs" variant="ghost" size="small" icon="arrow">Voir tous les projets</UiButton></template>
        <JobTable :jobs="jobs.slice(0, 6)" :loading="jobsLoading" @cancel="requestCancel" @download="download" />
      </UiCard>
      <div class="stack">
        <UiCard title="Santé du réseau" description="La capacité disponible pour vos prochains calculs." padded interactive>
          <div class="dashboard-network"><div class="dashboard-network__head"><span class="dashboard-network__signal"><i></i></span><div><strong>{{ onlineCount }} machine{{ onlineCount > 1 ? 's' : '' }} en ligne</strong><small>{{ currentCount }} à jour · {{ activeWorkloads }} calcul{{ activeWorkloads > 1 ? 's' : '' }} actif{{ activeWorkloads > 1 ? 's' : '' }}</small></div><UiStatusBadge :status="onlineCount ? 'operational' : peers.length ? 'degraded' : 'unknown'" /></div><dl><div v-for="group in roleGroups.slice(0, 4)" :key="group.role"><dt>{{ group.role }}</dt><dd>{{ group.count }}</dd></div><div><dt>Calculs actifs</dt><dd>{{ activeWorkloads }}</dd></div></dl><UiButton to="/network" variant="secondary" size="small" icon="arrow">Voir l’état du réseau</UiButton></div>
        </UiCard>
        <UiCard title="Accès rapides" padded><div class="quick-actions"><NuxtLink to="/jobs"><span><UiIcon name="activity"/></span><div><strong>Suivre mes calculs</strong><small>Avancement, résultat et historique</small></div><UiIcon name="chevron"/></NuxtLink><NuxtLink to="/nodes"><span><UiIcon name="nodes"/></span><div><strong>Gérer mes machines</strong><small>Disponibilité, versions et capacité</small></div><UiIcon name="chevron"/></NuxtLink><NuxtLink to="/download"><span><UiIcon name="download"/></span><div><strong>Installer un nœud</strong><small>Télécharger la version recommandée</small></div><UiIcon name="chevron"/></NuxtLink></div></UiCard>
      </div>
    </div>
    <UiModal :open="Boolean(cancelTarget)" title="Arrêter ce projet ?" @close="cancelTarget = null"><p class="modal-copy">Les parties encore en cours recevront une demande d’arrêt. Les résultats déjà vérifiés restent comptabilisés.</p><div class="modal-actions"><UiButton variant="ghost" @click="cancelTarget = null">Continuer</UiButton><UiButton variant="danger" :loading="cancelling" @click="confirmCancel">Arrêter le projet</UiButton></div></UiModal>
  </div>
</template>

<script setup lang="ts">
import type { Job } from '~/types/api';
definePageMeta({ layout: 'app', middleware: 'auth' });
const jobStore = useJobs();
const network = useNetwork();
const { jobs, total, loading: jobsLoading } = jobStore;
const { peers, roleGroups, outdatedCount, currentCount, onlineCount, workloads } = network;
const loadError = ref(false);
const cancelTarget = ref<Job | null>(null);
const cancelling = ref(false);
const runningCount = computed(() => jobs.value.filter(job => ['queued','running','cancelling'].includes(job.status)).length);
const completedCount = computed(() => jobs.value.filter(job => job.status === 'completed').length);
const activeWorkloads = computed(() => workloads.value.filter(task => Number(task.active || 0) > 0).length);
async function load(force = false) { const results = await Promise.allSettled([jobStore.loadJobs(1, 20, 'all', force), network.loadNetwork(force)]); loadError.value = results.some(result => result.status === 'rejected'); }
function requestCancel(job: Job) { cancelTarget.value = job; }
async function confirmCancel() { if (!cancelTarget.value) return; cancelling.value = true; try { await jobStore.cancelJob(cancelTarget.value.id); cancelTarget.value = null; await load(true); } finally { cancelling.value = false; } }
async function download(job: Job) { await jobStore.downloadResult(job).catch(() => { loadError.value = true; }); }
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { load(); timer = setInterval(() => load(), 5_000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); });
useSeoMeta({ title: 'Accueil — Silicium' });
</script>

<style scoped>
.dashboard-network{display:grid;gap:1rem}.dashboard-network__head{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.75rem}.dashboard-network__signal{display:grid;width:2.8rem;height:2.8rem;place-items:center;border-radius:50%;background:var(--mint-100)}.dashboard-network__signal i{width:.58rem;height:.58rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 7px rgba(24,181,165,.12)}.dashboard-network__head strong,.dashboard-network__head small{display:block}.dashboard-network__head strong{font-size:.86rem}.dashboard-network__head small{margin-top:.2rem;color:var(--ink-500);font-size:.6rem}.dashboard-network dl{margin:0}.dashboard-network dl>div{display:flex;align-items:center;justify-content:space-between;padding:.58rem 0;border-bottom:1px solid var(--border)}.dashboard-network dt{color:var(--ink-600);font-size:.65rem;text-transform:capitalize}.dashboard-network dd{margin:0;font-size:.7rem;font-weight:800}.dashboard-network :deep(.ui-button){width:100%}.quick-actions{display:grid;margin-top:-.25rem}.quick-actions>a{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem;padding:.75rem 0;border-bottom:1px solid var(--border)}.quick-actions>a:last-child{border:0}.quick-actions>a>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.55rem;background:var(--ink-100);color:var(--ink-700)}.quick-actions svg{width:.85rem}.quick-actions>a>svg{color:var(--ink-400)}.quick-actions strong,.quick-actions small{display:block}.quick-actions strong{font-size:.67rem}.quick-actions small{margin-top:.17rem;color:var(--ink-500);font-size:.56rem}.modal-copy{margin:0;color:var(--ink-600);font-size:.8rem;line-height:1.7}.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}
</style>
