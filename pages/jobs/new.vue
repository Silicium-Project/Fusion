<template>
  <div class="app-page new-job-page">
    <header><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>{{ t('newJob.back') }}</NuxtLink><span class="eyebrow">{{ t('common.newJob') }}</span><h1 class="page-title">{{ t('newJob.title') }}</h1><p class="page-intro">{{ t('newJob.intro') }}</p><p class="new-job-help">{{ t('newJob.help') }} {{ t('newJob.helpText') }} <NuxtLink to="/workloads" class="inline-link">{{ t('newJob.helpLink') }}</NuxtLink></p></header>
    <UiCard :title="t('newJob.card')" :description="t('newJob.cardText')" padded><JobForm :submitting="submitting" :error="error" :initial-workload="initialWorkload" :collection-id="collectionId" @submit="submit" /></UiCard>
  </div>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
import { extractJobError } from '~/utils/jobs';
import { DOCUMENT_SEARCH_WORKLOAD } from '~/utils/documents';
import { BATCH_AI_WORKLOAD } from '~/utils/batchAI';
definePageMeta({ layout: 'app', middleware: 'auth' });
const route = useRoute();
// `?workload=documents` opens the document search; `&collection=…` adds
// documents to an existing one ("Ajouter des documents"); `?workload=ai`
// opens the batch AI processing.
const collectionId = computed(() => typeof route.query.collection === 'string' ? route.query.collection : '');
/** `?workload=` preselects a type (from the job types page). */
const initialWorkload = computed(() => {
  if (route.query.workload === 'documents' || collectionId.value) return DOCUMENT_SEARCH_WORKLOAD;
  if (route.query.workload === 'ai') return BATCH_AI_WORKLOAD;
  return typeof route.query.workload === 'string' && ['raytracer', 'calcul/integrity/sha256'].includes(route.query.workload) ? route.query.workload : '';
});
const router = useRouter(); const { createJob } = useJobs(); const submitting = ref(false); const error = ref('');
const { t } = useI18n();
async function submit(input: CreateJobInput) { submitting.value = true; error.value = ''; try { const job = await createJob(input); await router.push(`/jobs/${job.id}`); } catch (failure) { error.value = extractJobError(failure); } finally { submitting.value = false; } }
useSeoMeta({ title: () => `${t('common.newJob')} — Silicium` });
</script>

<style scoped>
.new-job-page>header{display:grid;gap:.7rem;max-width:760px}.back-link{display:inline-flex;width:max-content;align-items:center;gap:.4rem;margin-bottom:.2rem;color:var(--ink-500);font-size:.9375rem;font-weight:700}.back-link svg{width:.78rem;transform:rotate(180deg)}.new-job-page>header .eyebrow{display:block}.new-job-help{margin:0;color:var(--ink-500);font-size:.9375rem;line-height:1.5}.inline-link{color:var(--mint-700);font-weight:750;text-decoration:underline;text-underline-offset:2px}
</style>
