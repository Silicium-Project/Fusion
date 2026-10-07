<template>
  <div class="app-page">
    <header class="app-page-head"><div><span class="eyebrow">{{ t('nav.yourSpace') }}</span><h1 class="page-title">{{ t('nav.projects') }}</h1><p class="page-intro">{{ t('jobs.intro') }}</p></div><div class="jobs-page-head__actions"><UiStatusBadge status="operational" :label="t('jobs.onlyYours')" /><UiButton to="/jobs/new" icon="upload">{{ t('common.newJob') }}</UiButton></div></header>
    <UiCard>
      <template #header><div class="jobs-toolbar"><div class="jobs-search"><UiIcon name="search"/><input v-model.trim="search" type="search" maxlength="200" :placeholder="t('jobs.search')" :aria-label="t('jobs.searchAria')"></div><select v-model="status" class="select" :aria-label="t('jobs.statusFilter')"><option v-for="filter in filters" :key="filter" :value="filter">{{ t(`jobs.filters.${filter}`) }}</option></select><UiButton variant="secondary" size="small" icon="refresh" :loading="loading" @click="load(true)">{{ t('common.refresh') }}</UiButton></div></template>
      <UiNotice v-if="error" tone="warning">{{ error }}</UiNotice>
      <JobTable :jobs="filteredJobs" :loading="loading" @cancel="requestCancel" @download="download" />
      <footer v-if="totalPages > 1" class="pagination"><span>{{ t('jobs.page', { page, pages: totalPages, count: total }) }}</span><div><UiButton variant="secondary" size="small" :disabled="page <= 1" @click="page--">{{ t('common.previous') }}</UiButton><UiButton variant="secondary" size="small" :disabled="page >= totalPages" @click="page++">{{ t('common.next') }}</UiButton></div></footer>
    </UiCard>
    <UiModal :open="Boolean(cancelTarget)" :title="t('jobs.stopTitle')" @close="cancelTarget = null"><p class="modal-copy">{{ t('jobs.stopText') }}</p><div class="modal-actions"><UiButton variant="ghost" @click="cancelTarget = null">{{ t('common.back') }}</UiButton><UiButton variant="danger" :loading="cancelling" @click="confirmCancel">{{ t('jobs.confirmStop') }}</UiButton></div></UiModal>
  </div>
</template>

<script setup lang="ts">
import type { Job } from '~/types/api';
definePageMeta({ layout: 'app', middleware: 'auth' });
const { t } = useI18n();
const filters = ['all', 'running', 'queued', 'completed', 'failed', 'cancelled', 'expired'];
const store = useJobs();
const { jobs, total, loading, error } = store;
const page = ref(1); const pageSize = 20; const status = ref('all'); const search = ref('');
const cancelTarget = ref<Job | null>(null); const cancelling = ref(false);
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const filteredJobs = computed(() => { const query = search.value.toLowerCase(); return query ? jobs.value.filter(job => `${job.title} ${job.siliciumJobId} ${job.workload}`.toLowerCase().includes(query)) : jobs.value; });
async function load(force = false) { await store.loadJobs(page.value, pageSize, status.value, force).catch(() => undefined); }
function requestCancel(job: Job) { cancelTarget.value = job; }
async function confirmCancel() { if (!cancelTarget.value) return; cancelling.value = true; try { await store.cancelJob(cancelTarget.value.id); cancelTarget.value = null; await load(true); } finally { cancelling.value = false; } }
async function download(job: Job) { await store.downloadResult(job).catch(() => undefined); }
watch([page, status], () => { if (status.value !== 'all') page.value = Math.min(page.value, totalPages.value); load(); });
onMounted(() => load());
useSeoMeta({ title: () => `${t('nav.projects')} — Silicium` });
</script>

<style scoped>
.jobs-page-head__actions{display:flex;align-items:center;justify-content:flex-end;gap:.75rem}.jobs-toolbar{display:flex;width:100%;align-items:center;gap:.6rem}.jobs-search{position:relative;min-width:220px;flex:1}.jobs-search svg{position:absolute;top:50%;left:.8rem;width:.9rem;transform:translateY(-50%);color:var(--ink-500)}.jobs-search input{width:100%;height:2.45rem;padding:0 .8rem 0 2.2rem;border:1px solid var(--border);border-radius:.65rem;background:var(--surface-soft);font-size:.7rem}.jobs-toolbar .select{width:auto;min-width:155px;min-height:2.45rem;font-size:.68rem}.pagination{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 1.2rem;border-top:1px solid var(--border);color:var(--ink-500);font-size:.63rem}.pagination>div{display:flex;gap:.4rem}.modal-copy{margin:0;color:var(--ink-600);font-size:.8rem;line-height:1.7}.modal-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.5rem}
@media(max-width:650px){.jobs-toolbar{align-items:stretch;flex-wrap:wrap}.jobs-search{flex-basis:100%}.jobs-toolbar .select{flex:1}.pagination{align-items:stretch;flex-direction:column}.pagination>div{justify-content:flex-end}}
@media(max-width:640px){.jobs-page-head__actions{align-items:stretch;justify-content:space-between}.jobs-page-head__actions .ui-button{flex:1}}
</style>
