<template>
  <div class="app-page new-job-page">
    <header><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>Retour aux tâches</NuxtLink><span class="eyebrow">Envoi manuel</span><h1 class="page-title">Envoyer un projet</h1><p class="page-intro">Les projets sont normalement reçus automatiquement. Cette page reste disponible pour transmettre un fichier lorsqu’une intégration en a besoin.</p></header>
    <div class="new-job-layout"><UiCard title="Envoi manuel" description="Transmettez un fichier si votre intégration ne peut pas encore utiliser l’envoi automatique." padded><JobForm :submitting="submitting" :error="error" @submit="submit" /></UiCard><aside class="stack"><UiCard title="Ce qui se passe ensuite" padded><ol class="expectations"><li v-for="(item,index) in expectations" :key="item.title"><span>{{ index + 1 }}</span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div></li></ol></UiCard><UiNotice title="Transmission">Le fichier suit le même parcours que les projets reçus automatiquement.</UiNotice></aside></div>
  </div>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
import { extractJobError } from '~/utils/jobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const router = useRouter(); const { createJob } = useJobs(); const submitting = ref(false); const error = ref('');
const expectations = [{ title: 'Réception', text: 'Le format du fichier est vérifié.' }, { title: 'Mise en file', text: 'Le projet attend son tour avec un avancement visible.' }, { title: 'Attribution', text: 'Les machines compatibles prennent une partie du projet.' }, { title: 'Vérification', text: 'Les résultats valides sont réunis.' }];
async function submit(input: CreateJobInput) { submitting.value = true; error.value = ''; try { const job = await createJob(input); await router.push(`/jobs/${job.id}`); } catch (failure) { error.value = extractJobError(failure); } finally { submitting.value = false; } }
useSeoMeta({ title: 'Envoyer un projet — Silicium' });
</script>

<style scoped>
.new-job-page>header{display:grid;gap:.7rem;max-width:760px}.back-link{display:inline-flex;width:max-content;align-items:center;gap:.4rem;margin-bottom:.2rem;color:var(--ink-500);font-size:.65rem;font-weight:700}.back-link svg{width:.78rem;transform:rotate(180deg)}.new-job-page>header .eyebrow{display:block}.new-job-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:1rem}.expectations{display:grid;gap:.8rem;margin:0;padding:0;list-style:none}.expectations li{display:grid;grid-template-columns:1.8rem 1fr;gap:.7rem}.expectations li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border-radius:.5rem;background:var(--mint-100);color:var(--mint-700);font-size:.6rem;font-weight:850}.expectations strong,.expectations small{display:block}.expectations strong{font-size:.68rem}.expectations small{margin-top:.2rem;color:var(--ink-500);font-size:.58rem;line-height:1.45}@media(max-width:980px){.new-job-layout{grid-template-columns:1fr}}
</style>
