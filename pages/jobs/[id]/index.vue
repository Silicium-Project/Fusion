<template>
  <div class="app-page">
    <template v-if="dashboard">
      <header class="job-head">
        <div><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>{{ t('jobDetail.allProjects') }}</NuxtLink><div class="job-head__title"><span class="job-head__cube"><UiIcon name="cube"/></span><div><div class="cluster"><h1>{{ dashboard.job.title }}</h1><UiStatusBadge :status="dashboard.job.status" /></div><p>{{ dashboard.job.description || t('jobDetail.defaultDescription') }}</p></div></div></div>
        <div class="job-head__actions"><UiButton variant="secondary" icon="refresh" size="small" :loading="loading" @click="load(true)">{{ t('common.refresh') }}</UiButton><UiButton v-if="dashboard.resultReady && !documentJob" icon="download" size="small" @click="download">{{ t('common.download') }}</UiButton><UiButton v-if="cancellable" variant="danger" size="small" @click="confirmOpen = true">{{ t('jobDetail.stop') }}</UiButton></div>
      </header>
      <UiNotice v-if="jobErrorDetail" tone="danger" :title="t('jobDetail.errorTitle')">{{ compactJobError(jobErrorDetail) }}</UiNotice>
      <section class="metric-grid">
        <MetricCard :label="t('jobDetail.parts')" :value="fragmentTotal" :detail="t('jobDetail.partsDone', { count: fragmentDone })" icon="layers" tone="mint" />
        <MetricCard :label="t('jobDetail.machines')" :value="nodeCount" :detail="t('jobDetail.machinesText')" icon="nodes" tone="ink" />
        <MetricCard :label="t('jobDetail.duration')" :value="duration" :detail="t('jobDetail.sinceStart')" icon="clock" tone="violet" />
        <MetricCard :label="t('jobDetail.efficiency')" :value="computeShare" :detail="performanceDetail" icon="activity" tone="mint" />
        <MetricCard :label="t('jobDetail.proofs')" :value="dashboard.devnet?.signatures?.length || 0" :detail="dashboard.devnet?.enabled ? t('jobDetail.tracing') : t('jobDetail.noTracing')" icon="shield" :tone="dashboard.devnet?.ok ? 'mint' : 'amber'" />
      </section>
      <div class="job-detail-grid">
        <UiCard id="result" :title="documentJob ? t('jobDetail.searchTitle') : t('jobDetail.resultTitle')" :description="resultDescription" padded><RenderPreview v-if="imageJob" :dashboard="dashboard" :image-url="resultPreview" /><HashResult v-else-if="hashJob" :dashboard="dashboard" /><DocumentSearch v-else-if="documentJob" :dashboard="dashboard" /><UiEmptyState v-else :title="t('jobDetail.downloadableTitle')" :description="t('jobDetail.downloadableText')" icon="download" /></UiCard>
        <UiCard :title="t('jobDetail.steps')" :description="t('jobDetail.stepsText')" padded><ExecutionTimeline :dashboard="dashboard" /></UiCard>
      </div>
      <div class="job-detail-grid job-detail-grid--bottom">
        <UiCard :title="t('jobDetail.fragments')" :description="t('jobDetail.fragmentsText', { done: fragmentDone, active: fragmentActive, failed: fragmentFailed })">
          <div v-if="!fragments.length" class="empty-dash"><UiEmptyState :title="t('jobDetail.noFragments')" :description="t('jobDetail.noFragmentsText')" icon="layers" /></div>
          <div v-else class="table-wrap"><table class="data-table fragments-table"><thead><tr><th>{{ t('jobDetail.fragment') }}</th><th>{{ t('jobDetail.stage') }}</th><th>{{ t('jobDetail.node') }}</th><th>{{ t('jobDetail.status') }}</th></tr></thead><tbody><tr v-for="(fragment,index) in visibleFragments" :key="fragmentKey(fragment,index)"><td class="mono">#{{ fragmentIndex(fragment,index) }}</td><td>{{ fragmentStateLabel(fragment.status) }}</td><td class="mono">{{ compactIdentifier(fragmentNode(fragment) || t('jobDetail.waiting'), 10, 5) }}</td><td><UiStatusBadge :status="String(fragment.status || 'unknown')" /></td></tr></tbody></table></div>
          <footer v-if="fragments.length > visibleLimit" class="card-footer">{{ t('jobDetail.recent', { limit: visibleLimit, total: fragments.length }) }}</footer>
        </UiCard>
        <div class="stack">
          <UiCard :title="t('jobDetail.technical')" padded><TechnicalDetails :dashboard="dashboard" /></UiCard>
          <UiCard v-if="dashboard.devnet?.signatures?.length" :title="t('jobDetail.devnet')" padded><div class="transaction-list"><a v-for="signature in dashboard.devnet.signatures.slice(0,5)" :key="signature" :href="`https://explorer.solana.com/tx/${encodeURIComponent(signature)}?cluster=devnet`" target="_blank" rel="noopener noreferrer"><span class="mono">{{ compactIdentifier(signature, 10, 8) }}</span><UiIcon name="external"/></a></div></UiCard>
        </div>
      </div>
    </template>
    <div v-else-if="loading" class="detail-loading"><div class="skeleton"></div><div class="metric-grid"><div v-for="n in 5" :key="n" class="skeleton"></div></div><div class="skeleton large"></div></div>
    <UiCard v-else padded><UiEmptyState :title="t('jobDetail.notFoundTitle')" :description="error || t('jobDetail.notFoundText')" icon="alert"><UiButton to="/jobs" variant="secondary" size="small">{{ t('jobDetail.backToProjects') }}</UiButton></UiEmptyState></UiCard>
    <UiModal :open="confirmOpen" :title="t('jobDetail.stopTitle')" @close="confirmOpen = false"><p class="modal-copy">{{ t('jobDetail.stopText') }}</p><div class="modal-actions"><UiButton variant="ghost" @click="confirmOpen = false">{{ t('jobDetail.keepRunning') }}</UiButton><UiButton variant="danger" :loading="cancelling" @click="cancel">{{ t('jobDetail.stopNow') }}</UiButton></div></UiModal>
  </div>
</template>

<script setup lang="ts">
import type { JobDashboard, JobFragment } from '~/types/api';
import { compactIdentifier, formatDuration, formatPerformanceMultiple, formatPerformancePercent } from '~/utils/format';
import { isDocumentSearchWorkload } from '~/utils/documents';
import { compactJobError, fragmentStateLabel, fragmentVisualState, isHashWorkload, isImageWorkload, isJobCancellable, shouldRefreshJob } from '~/utils/jobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const { t } = useI18n();
const route = useRoute(); const jobsStore = useJobs(); const session = useSession(); const config = useRuntimeConfig();
const dashboard = ref<JobDashboard | null>(null); const loading = ref(true); const error = ref(''); const confirmOpen = ref(false); const cancelling = ref(false); const resultPreview = ref(''); const previewAttempts = ref(0);
const visibleLimit = 80;
const imageJob = computed(() => isImageWorkload(dashboard.value?.job.workload));
const hashJob = computed(() => isHashWorkload(dashboard.value?.job.workload));
const documentJob = computed(() => isDocumentSearchWorkload(dashboard.value?.job.workload));
const resultDescription = computed(() => imageJob.value ? t('jobDetail.imageDescription') : documentJob.value ? t('jobDetail.documentsDescription') : t('jobDetail.hashDescription'));
const fragments = computed(() => dashboard.value?.summary?.fragments || []);
const visibleFragments = computed(() => fragments.value.slice(-visibleLimit).reverse());
const jobErrorDetail = computed(() => dashboard.value?.job.errorMessage || dashboard.value?.summary?.failureDetail || dashboard.value?.summary?.traceback || dashboard.value?.summary?.error || '');
const fragmentTotal = computed(() => Number(dashboard.value?.summary?.fragmentCount || dashboard.value?.job.fragmentCount || fragments.value.length || 0));
const fragmentDone = computed(() => fragments.value.filter(item => fragmentVisualState(item.status) === 'done').length);
const fragmentActive = computed(() => fragments.value.filter(item => ['computing','validating'].includes(fragmentVisualState(item.status))).length);
const fragmentFailed = computed(() => fragments.value.filter(item => fragmentVisualState(item.status) === 'failed').length);
const nodeCount = computed(() => new Set(fragments.value.map(fragmentNode).filter(Boolean)).size || Number((dashboard.value?.job.network?.nodes as unknown[])?.length || 0));
const duration = computed(() => dashboard.value ? formatDuration(dashboard.value.job.startedAt, dashboard.value.job.completedAt) : '—');
const performance = computed(() => dashboard.value?.summary?.performance);
const computeShare = computed(() => formatPerformancePercent(performance.value?.compute_to_total_ratio));
const computeNetwork = computed(() => formatPerformanceMultiple(performance.value?.compute_to_network_ratio));
const performanceDetail = computed(() => computeNetwork.value === '—' ? t('jobDetail.noNetworkMeasure') : t('jobDetail.computeVsNetwork', { value: computeNetwork.value }));
const cancellable = computed(() => Boolean(dashboard.value && isJobCancellable(dashboard.value.job.status)));
const shouldPoll = computed(() => Boolean(dashboard.value && (shouldRefreshJob(dashboard.value.job.status, dashboard.value.resultReady) || (imageJob.value && dashboard.value.resultReady && !resultPreview.value && previewAttempts.value < 5))));
function fragmentIndex(fragment: JobFragment, fallback: number) { return fragment.fragment_index ?? fragment.fragmentIndex ?? fallback; }
function fragmentNode(fragment: JobFragment) { return String(fragment.handled_by || fragment.handledBy || ''); }
function fragmentKey(fragment: JobFragment, fallback: number) { return `${fragmentIndex(fragment,fallback)}-${fragmentNode(fragment)}-${fragment.status}`; }
let loadPromise: Promise<void> | undefined;
function load(force = false, background = false): Promise<void> {
  if (loadPromise) return loadPromise;
  if (!background) loading.value = true;
  error.value = '';
  loadPromise = (async () => {
    try {
      dashboard.value = await jobsStore.getJobDashboard(String(route.params.id), force);
      if (dashboard.value.resultReady && !resultPreview.value) await loadPreview();
    } catch (failure) {
      if (!dashboard.value) {
        const response = failure as { status?: number; statusCode?: number };
        error.value = response.status === 404 || response.statusCode === 404 ? t('jobDetail.notFound') : t('jobDetail.loadFailed');
      }
    } finally {
      loading.value = false;
      loadPromise = undefined;
    }
  })();
  return loadPromise;
}
async function loadPreview() { if (!dashboard.value?.resultReady || !imageJob.value || !import.meta.client) return; previewAttempts.value += 1; const token = await session.ensureAccessToken(); if (!token) return; const response = await fetch(`${config.public.apiBase}/jobs/${route.params.id}/result`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' }); if (!response.ok || !response.headers.get('content-type')?.startsWith('image/')) return; const next = URL.createObjectURL(await response.blob()); if (resultPreview.value) URL.revokeObjectURL(resultPreview.value); resultPreview.value = next; }
async function download() { if (dashboard.value) await jobsStore.downloadResult(dashboard.value.job); }
async function cancel() { if (!dashboard.value) return; cancelling.value = true; try { await jobsStore.cancelJob(dashboard.value.job.id); confirmOpen.value = false; await load(true); } finally { cancelling.value = false; } }
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => { load(); timer = setInterval(() => { if (shouldPoll.value) load(true, true); }, 2_000); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); if (resultPreview.value) URL.revokeObjectURL(resultPreview.value); });
useSeoMeta({ title: () => dashboard.value ? `${dashboard.value.job.title} — Silicium` : t('jobDetail.seoFallback') });
</script>

<style scoped>
.job-head{display:flex;align-items:flex-end;justify-content:space-between;gap:1rem}.back-link{display:inline-flex;align-items:center;gap:.4rem;margin-bottom:1rem;color:var(--ink-500);font-size:.63rem;font-weight:700}.back-link svg{width:.75rem;transform:rotate(180deg)}.job-head__title{display:flex;align-items:center;gap:.9rem}.job-head__cube{display:grid;width:3.25rem;height:3.25rem;flex:0 0 auto;place-items:center;border-radius:.9rem;background:var(--violet-100);color:var(--violet-600)}.job-head__cube svg{width:1.3rem}.job-head h1{margin:0;font-size:clamp(1.65rem,3vw,2.4rem);letter-spacing:-.05em}.job-head p{margin:.35rem 0 0;color:var(--ink-600);font-size:.7rem}.job-head__actions{display:flex;gap:.45rem}.job-detail-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:1rem}.job-detail-grid--bottom{align-items:start}.fragments-table{min-width:520px}.card-footer{padding:.75rem 1rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.6rem}.transaction-list{display:grid}.transaction-list a{display:flex;align-items:center;justify-content:space-between;padding:.65rem 0;border-bottom:1px solid var(--border);color:var(--ink-700);font-size:.62rem}.transaction-list a:last-child{border:0}.transaction-list svg{width:.8rem;color:var(--mint-700)}.modal-copy{margin:0;color:var(--ink-600);font-size:.8rem;line-height:1.7}.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}.detail-loading{display:grid;gap:1rem}.detail-loading>.skeleton:first-child{height:90px}.detail-loading .metric-grid .skeleton{height:110px}.detail-loading .large{height:420px}
@media(max-width:980px){.job-detail-grid{grid-template-columns:1fr}.job-head{align-items:stretch;flex-direction:column}.job-head__actions{justify-content:flex-end}}@media(max-width:560px){.job-head__title{align-items:flex-start}.job-head__actions{overflow-x:auto;justify-content:flex-start;padding-bottom:.2rem}.job-head__cube{width:2.7rem;height:2.7rem}.job-head__title .cluster{gap:.45rem}.modal-actions{align-items:stretch;flex-direction:column}}
</style>
