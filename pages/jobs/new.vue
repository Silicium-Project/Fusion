<template>
  <div class="app-page new-job-page">
    <header><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>{{ t('newJob.back') }}</NuxtLink><span class="eyebrow">{{ t('common.newJob') }}</span><h1 class="page-title">{{ t('newJob.title') }}</h1><p class="page-intro">{{ t('newJob.intro') }}</p></header>
    <div class="new-job-layout"><UiCard :title="t('newJob.card')" :description="t('newJob.cardText')" padded><JobForm :submitting="submitting" :error="error" :initial-workload="initialWorkload" :collection-id="collectionId" @submit="submit" /></UiCard><aside class="stack"><UiCard :title="t('newJob.journey')" padded><ol class="expectations"><li v-for="(item,index) in tl<{ title: string; text: string }>('newJob.expectations')" :key="index"><span>{{ index + 1 }}</span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div></li></ol></UiCard><UiNotice :title="t('newJob.help')">{{ t('newJob.helpText') }} <NuxtLink to="/workloads" class="inline-link">{{ t('newJob.helpLink') }}</NuxtLink></UiNotice><UiNotice :title="t('newJob.after')">{{ t('newJob.afterText') }}</UiNotice></aside></div>
  </div>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
import { extractJobError } from '~/utils/jobs';
import { DOCUMENT_SEARCH_WORKLOAD } from '~/utils/documents';
definePageMeta({ layout: 'app', middleware: 'auth' });
const route = useRoute();
// `?workload=documents` opens the document search; `&collection=…` adds
// documents to an existing one ("Ajouter des documents").
const collectionId = computed(() => typeof route.query.collection === 'string' ? route.query.collection : '');
/** `?workload=` preselects a type (from the job types page). */
const initialWorkload = computed(() => {
  if (route.query.workload === 'documents' || collectionId.value) return DOCUMENT_SEARCH_WORKLOAD;
  return typeof route.query.workload === 'string' && ['raytracer', 'calcul/integrity/sha256'].includes(route.query.workload) ? route.query.workload : '';
});
const router = useRouter(); const { createJob } = useJobs(); const submitting = ref(false); const error = ref('');
const { t, tl } = useI18n();
async function submit(input: CreateJobInput) { submitting.value = true; error.value = ''; try { const job = await createJob(input); await router.push(`/jobs/${job.id}`); } catch (failure) { error.value = extractJobError(failure); } finally { submitting.value = false; } }
useSeoMeta({ title: () => `${t('common.newJob')} — Silicium` });
</script>

<style scoped>
.new-job-page>header{display:grid;gap:.7rem;max-width:760px}.back-link{display:inline-flex;width:max-content;align-items:center;gap:.4rem;margin-bottom:.2rem;color:var(--ink-500);font-size:.65rem;font-weight:700}.back-link svg{width:.78rem;transform:rotate(180deg)}.new-job-page>header .eyebrow{display:block}.new-job-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:1rem}.expectations{display:grid;gap:.8rem;margin:0;padding:0;list-style:none}.expectations li{display:grid;grid-template-columns:1.8rem 1fr;gap:.7rem}.expectations li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border-radius:.5rem;background:var(--mint-100);color:var(--mint-700);font-size:.6rem;font-weight:850}.expectations strong,.expectations small{display:block}.expectations strong{font-size:.68rem}.expectations small{margin-top:.2rem;color:var(--ink-500);font-size:.58rem;line-height:1.45}.inline-link{color:var(--mint-700);font-weight:750;text-decoration:underline;text-underline-offset:2px}@media(max-width:980px){.new-job-layout{grid-template-columns:1fr}}
</style>
