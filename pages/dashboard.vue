<template>
  <div class="app-page">
    <header class="app-page-head"><div><span class="eyebrow">{{ t('nav.yourSpace') }}</span><h1 class="page-title">{{ t('nav.home') }}</h1><p class="page-intro">{{ t('dashboard.intro') }}</p></div><UiButton to="/jobs/new" icon="upload">{{ t('common.newJob') }}</UiButton></header>
    <UiNotice v-if="loadError" tone="warning">{{ t('dashboard.partialData') }}</UiNotice>
    <section class="metric-grid" :aria-label="t('dashboard.metrics')">
      <MetricCard :label="t('dashboard.projects')" :value="total" :detail="t('dashboard.inYourSpace')" icon="jobs" tone="ink" />
      <MetricCard :label="t('dashboard.running')" :value="runningCount" :detail="t('dashboard.activeProjects')" icon="activity" tone="mint" />
      <MetricCard :label="t('dashboard.finished')" :value="completedCount" :detail="t('dashboard.resultsAvailable')" icon="check" tone="violet" />
      <MetricCard :label="t('dashboard.machinesOnline')" :value="onlineCount" :detail="t('dashboard.toUpdate', { count: outdatedCount })" icon="nodes" :tone="outdatedCount ? 'amber' : 'mint'" />
    </section>
    <div class="two-column">
      <UiCard :title="t('dashboard.recent')" :description="t('dashboard.recentText')">
        <template #actions><UiButton to="/jobs" variant="ghost" size="small" icon="arrow">{{ t('dashboard.allProjects') }}</UiButton></template>
        <JobTable :jobs="jobs.slice(0, 6)" :loading="jobsLoading" compact @cancel="requestCancel" @download="download" />
      </UiCard>
      <div class="stack">
        <UiCard :title="t('nav.networkHealth')" :description="t('dashboard.networkText')" padded interactive>
          <div class="dashboard-network"><div class="dashboard-network__head"><span class="dashboard-network__signal"><i></i></span><div><strong>{{ t('dashboard.online', { count: onlineCount }) }}</strong><small>{{ t('dashboard.upToDate', { current: currentCount, count: activeWorkloads }) }}</small></div><UiStatusBadge :status="onlineCount ? 'operational' : peers.length ? 'degraded' : 'unknown'" /></div><dl><div v-for="group in roleGroups.slice(0, 4)" :key="group.role"><dt>{{ networkRoleLabel(group.role) }}</dt><dd>{{ group.count }}</dd></div><div><dt>{{ t('dashboard.activeJobs') }}</dt><dd>{{ activeWorkloads }}</dd></div></dl><UiButton to="/network" variant="secondary" size="small" icon="arrow">{{ t('dashboard.seeNetwork') }}</UiButton></div>
        </UiCard>
        <UiCard :title="t('dashboard.quick')" padded><div class="quick-actions"><NuxtLink to="/jobs"><span><UiIcon name="activity"/></span><div><strong>{{ t('dashboard.quickJobs') }}</strong><small>{{ t('dashboard.quickJobsText') }}</small></div><UiIcon name="chevron"/></NuxtLink><NuxtLink to="/workloads"><span><UiIcon name="layers"/></span><div><strong>{{ t('dashboard.quickWorkloads') }}</strong><small>{{ t('dashboard.quickWorkloadsText') }}</small></div><UiIcon name="chevron"/></NuxtLink><NuxtLink to="/nodes"><span><UiIcon name="nodes"/></span><div><strong>{{ t('dashboard.quickNodes') }}</strong><small>{{ t('dashboard.quickNodesText') }}</small></div><UiIcon name="chevron"/></NuxtLink><NuxtLink to="/download"><span><UiIcon name="download"/></span><div><strong>{{ t('dashboard.quickInstall') }}</strong><small>{{ t('dashboard.quickInstallText') }}</small></div><UiIcon name="chevron"/></NuxtLink></div></UiCard>
      </div>
    </div>
    <UiModal :open="Boolean(cancelTarget)" :title="t('dashboard.stopTitle')" @close="cancelTarget = null"><p class="modal-copy">{{ t('dashboard.stopText') }}</p><div class="modal-actions"><UiButton variant="ghost" @click="cancelTarget = null">{{ t('common.continue') }}</UiButton><UiButton variant="danger" :loading="cancelling" @click="confirmCancel">{{ t('dashboard.stopConfirm') }}</UiButton></div></UiModal>
  </div>
</template>

<script setup lang="ts">
import type { Job } from '~/types/api';
import { networkRoleLabel } from '~/utils/format';
definePageMeta({ layout: 'app', middleware: 'auth' });
const { t } = useI18n();
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
useSeoMeta({ title: () => `${t('nav.home')} — Silicium` });
</script>

<style scoped>
.dashboard-network{display:grid;gap:1rem}.dashboard-network__head{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.75rem}.dashboard-network__signal{display:grid;width:2.8rem;height:2.8rem;place-items:center;border-radius:50%;background:var(--mint-100)}.dashboard-network__signal i{width:.58rem;height:.58rem;border-radius:50%;background:var(--mint-500);box-shadow:0 0 0 7px rgba(24,181,165,.12)}.dashboard-network__head strong,.dashboard-network__head small{display:block}.dashboard-network__head strong{font-size:.952rem}.dashboard-network__head small{margin-top:.2rem;color:var(--ink-500);font-size:.9375rem}.dashboard-network dl{margin:0}.dashboard-network dl>div{display:flex;align-items:center;justify-content:space-between;padding:.58rem 0;border-bottom:1px solid var(--border)}.dashboard-network dt{color:var(--ink-600);font-size:.9375rem;text-transform:capitalize}.dashboard-network dd{margin:0;font-size:.9375rem;font-weight:800}.dashboard-network :deep(.ui-button){width:100%}.quick-actions{display:grid;margin-top:-.25rem}.quick-actions>a{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.7rem;padding:.75rem 0;border-bottom:1px solid var(--border)}.quick-actions>a:last-child{border:0}.quick-actions>a>span{display:grid;width:2rem;height:2rem;place-items:center;border-radius:.55rem;background:var(--ink-100);color:var(--ink-700)}.quick-actions svg{width:.85rem}.quick-actions>a>svg{color:var(--ink-400)}.quick-actions strong,.quick-actions small{display:block}.quick-actions strong{font-size:.9375rem}.quick-actions small{margin-top:.17rem;color:var(--ink-500);font-size:.9375rem}.modal-copy{margin:0;color:var(--ink-600);font-size:.9375rem;line-height:1.7}.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}
</style>
