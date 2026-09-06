<template>
  <div class="app-page new-job-page">
    <header><NuxtLink to="/jobs" class="back-link"><UiIcon name="arrow"/>Retour aux tâches</NuxtLink><span class="eyebrow">Nouvelle exécution</span><h1 class="page-title">Configurer une tâche</h1><p class="page-intro">Les paramètres restent lisibles et modifiables avant toute soumission au réseau.</p></header>
    <div class="new-job-layout"><UiCard title="Charge de travail" description="Décrivez le calcul et joignez son entrée." padded><JobForm :submitting="submitting" :error="error" @submit="submit" /></UiCard><aside class="stack"><UiCard title="Ce qui va se passer" padded><ol class="expectations"><li v-for="(item,index) in expectations" :key="item.title"><span>{{ index + 1 }}</span><div><strong>{{ item.title }}</strong><small>{{ item.text }}</small></div></li></ol></UiCard><UiNotice title="Fichier local">Le fichier est transmis à l’API au moment de la soumission. Il n’est pas conservé par le navigateur.</UiNotice></aside></div>
  </div>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
definePageMeta({ layout: 'app', middleware: 'auth' });
const router = useRouter(); const { createJob } = useJobs(); const submitting = ref(false); const error = ref('');
const expectations = [{ title: 'Validation', text: 'L’API vérifie le format et les bornes.' }, { title: 'Découpage', text: 'L’orchestrateur produit les fragments.' }, { title: 'Attribution', text: 'Les rôles compatibles reçoivent le travail.' }, { title: 'Vérification', text: 'Les reçus valides forment le résultat.' }];
async function submit(input: CreateJobInput) { submitting.value = true; error.value = ''; try { const job = await createJob(input); await router.push(`/jobs/${job.id}`); } catch (failure) { const data = failure as { data?: string | { message?: string } }; error.value = typeof data.data === 'string' ? data.data : data.data?.message || 'La tâche ne peut pas être soumise pour le moment.'; } finally { submitting.value = false; } }
useSeoMeta({ title: 'Nouvelle tâche — Silicium' });
</script>

<style scoped>
.new-job-page>header{max-width:760px}.back-link{display:inline-flex;align-items:center;gap:.4rem;margin-bottom:1.5rem;color:var(--ink-500);font-size:.65rem;font-weight:700}.back-link svg{width:.78rem;transform:rotate(180deg)}.new-job-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(280px,.65fr);gap:1rem}.expectations{display:grid;gap:.8rem;margin:0;padding:0;list-style:none}.expectations li{display:grid;grid-template-columns:1.8rem 1fr;gap:.7rem}.expectations li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border-radius:.5rem;background:var(--mint-100);color:var(--mint-700);font-size:.6rem;font-weight:850}.expectations strong,.expectations small{display:block}.expectations strong{font-size:.68rem}.expectations small{margin-top:.2rem;color:var(--ink-500);font-size:.58rem;line-height:1.45}@media(max-width:980px){.new-job-layout{grid-template-columns:1fr}}
</style>
