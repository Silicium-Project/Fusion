<template>
  <form class="job-form" :aria-busy="submitting" @submit.prevent="submit">
    <div class="job-form__grid">
      <label class="field job-form__wide"><span>Nom de la tâche</span><input v-model.trim="form.title" class="input" maxlength="120" required placeholder="Ex. Rendu intérieur — version 4"></label>
      <label class="field"><span>Type de projet</span><select v-model="form.workload" class="select"><option value="raytracer">Rendu d’image</option></select></label>
      <label class="field"><span>Priorité</span><select v-model="form.priority" class="select"><option value="low">Basse</option><option value="normal">Normale</option><option value="high">Haute</option><option value="urgent">Urgente</option></select></label>
      <label class="field job-form__wide"><span>Description <small>facultative</small></span><textarea v-model.trim="form.description" class="textarea" maxlength="1000" placeholder="Contexte, version ou objectif de cette exécution"></textarea></label>
    </div>
    <div class="job-form__configuration">
      <div><span class="field-label">Nombre de parties</span><strong>{{ form.fragmentCount }}</strong><input v-model.number="form.fragmentCount" type="range" min="1" max="256" step="1" aria-label="Nombre de parties"><small>Le réseau les répartit ensuite entre les machines disponibles.</small></div>
      <div><span class="field-label">Durée maximale</span><strong>{{ runtimeLabel }}</strong><input v-model.number="form.maxRuntimeSeconds" type="range" min="60" max="14400" step="60" aria-label="Durée maximale"><small>Une propagation d’arrêt est émise à l’échéance.</small></div>
    </div>
    <label class="job-drop" :class="{ 'job-drop--ready': file }">
      <input type="file" required accept=".json,.cfg,.txt,application/json,text/plain" @change="onFile">
      <span class="job-drop__icon"><UiIcon :name="file ? 'check' : 'upload'"/></span>
      <span><strong>{{ file ? file.name : 'Ajouter le fichier d’entrée' }}</strong><small>{{ file ? fileSize : 'JSON, CFG ou texte · 16 Mo maximum' }}</small></span>
      <span class="job-drop__action">{{ file ? 'Remplacer' : 'Parcourir' }}</span>
    </label>
    <UiNotice v-if="error" tone="danger">{{ error }}</UiNotice>
    <div class="job-form__footer"><p>Le projet sera envoyé puis réparti automatiquement par le réseau.</p><div class="cluster"><UiButton to="/jobs" variant="ghost">Annuler</UiButton><UiButton type="submit" icon="arrow" :loading="submitting">Envoyer le projet</UiButton></div></div>
  </form>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
const props = withDefaults(defineProps<{ submitting?: boolean; error?: string }>(), { submitting: false, error: '' });
const emit = defineEmits<{ submit: [input: CreateJobInput] }>();
const file = ref<File | null>(null);
const form = reactive({ title: '', description: '', workload: 'raytracer', priority: 'normal', fragmentCount: 64, maxRuntimeSeconds: 3600 });
const runtimeLabel = computed(() => form.maxRuntimeSeconds < 3600 ? `${Math.round(form.maxRuntimeSeconds / 60)} min` : `${(form.maxRuntimeSeconds / 3600).toFixed(form.maxRuntimeSeconds % 3600 ? 1 : 0)} h`);
const fileSize = computed(() => file.value ? `${Math.max(.1, file.value.size / 1024).toFixed(1)} Ko` : '');
function onFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null; }
function submit() { if (!file.value || props.submitting) return; emit('submit', { ...form, file: file.value }); }
</script>

<style scoped>
.job-form{display:grid;gap:1.35rem}.job-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.job-form__wide{grid-column:1/-1}.field span small{color:var(--ink-500);font-weight:500}.job-form__configuration{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.job-form__configuration>div{display:grid;grid-template-columns:1fr auto;gap:.55rem;padding:1rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.job-form__configuration strong{font-size:.8rem}.job-form__configuration input{grid-column:1/-1;width:100%;accent-color:var(--mint-600)}.job-form__configuration small{grid-column:1/-1;color:var(--ink-500);font-size:.62rem;line-height:1.45}
.job-drop{display:grid;min-height:92px;grid-template-columns:auto 1fr auto;align-items:center;gap:1rem;padding:1rem;border:1px dashed var(--border-strong);border-radius:var(--radius-md);background:rgba(244,245,241,.45);cursor:pointer}.job-drop:hover,.job-drop--ready{border-color:var(--mint-500);background:var(--mint-100)}.job-drop input{position:absolute;width:1px;height:1px;opacity:0}.job-drop__icon{display:grid;width:2.7rem;height:2.7rem;place-items:center;border-radius:.75rem;background:white;color:var(--mint-700);box-shadow:var(--shadow-sm)}.job-drop__icon svg{width:1.1rem}.job-drop strong,.job-drop small{display:block}.job-drop strong{font-size:.76rem}.job-drop small{margin-top:.3rem;color:var(--ink-500);font-size:.62rem}.job-drop__action{padding:.58rem .72rem;border:1px solid var(--border-strong);border-radius:.55rem;background:white;font-size:.68rem;font-weight:750}.job-form__footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-top:1rem;border-top:1px solid var(--border)}.job-form__footer p{max-width:430px;margin:0;color:var(--ink-500);font-size:.65rem;line-height:1.5}
@media(max-width:620px){.job-form__grid,.job-form__configuration{grid-template-columns:1fr}.job-drop{grid-template-columns:auto 1fr}.job-drop__action{display:none}.job-form__footer{align-items:stretch;flex-direction:column}.job-form__footer .cluster{justify-content:flex-end}}
</style>
