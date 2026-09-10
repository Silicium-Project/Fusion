<template>
  <div class="app-page new-job-page">
    <header><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>Retour aux projets</NuxtLink><span class="eyebrow">Nouveau calcul</span><h1 class="page-title">Lancer un calcul</h1><p class="page-intro">Ajoutez votre fichier, choisissez la configuration adaptée puis suivez le résultat depuis votre espace.</p></header>
    <div class="new-job-layout"><UiCard title="Créer un projet" description="Le réseau s’occupe de la répartition et de la vérification." padded><JobForm :submitting="submitting" :error="error" @submit="submit" /></UiCard><aside class="stack"><UiCard title="Votre parcours" padded><ol class="expectations"><li v-for="(item,index) in expectations" :key="item.title"><span>{{ index + 1 }}</span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div></li></ol></UiCard><UiNotice title="Après le lancement">Vous serez redirigé vers le suivi du projet dès que le fichier sera accepté.</UiNotice></aside></div>
  </div>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
import { extractJobError } from '~/utils/jobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const router = useRouter(); const { createJob } = useJobs(); const submitting = ref(false); const error = ref('');
const expectations = [{ title: 'Ajouter le fichier', text: 'Le format et la taille sont vérifiés immédiatement.' }, { title: 'Choisir les options', text: 'La configuration recommandée est proposée par défaut.' }, { title: 'Suivre le calcul', text: 'La progression et le résultat restent visibles dans votre espace.' }];
async function submit(input: CreateJobInput) { submitting.value = true; error.value = ''; try { const job = await createJob(input); await router.push(`/jobs/${job.id}`); } catch (failure) { error.value = extractJobError(failure); } finally { submitting.value = false; } }
useSeoMeta({ title: 'Nouveau calcul — Silicium' });
</script>

<style scoped>
.new-job-page>header{display:grid;gap:.7rem;max-width:760px}.back-link{display:inline-flex;width:max-content;align-items:center;gap:.4rem;margin-bottom:.2rem;color:var(--ink-500);font-size:.65rem;font-weight:700}.back-link svg{width:.78rem;transform:rotate(180deg)}.new-job-page>header .eyebrow{display:block}.new-job-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:1rem}.expectations{display:grid;gap:.8rem;margin:0;padding:0;list-style:none}.expectations li{display:grid;grid-template-columns:1.8rem 1fr;gap:.7rem}.expectations li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border-radius:.5rem;background:var(--mint-100);color:var(--mint-700);font-size:.6rem;font-weight:850}.expectations strong,.expectations small{display:block}.expectations strong{font-size:.68rem}.expectations small{margin-top:.2rem;color:var(--ink-500);font-size:.58rem;line-height:1.45}@media(max-width:980px){.new-job-layout{grid-template-columns:1fr}}
</style>
