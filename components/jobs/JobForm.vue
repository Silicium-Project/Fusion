<template>
  <form class="job-form" :aria-busy="submitting" @submit.prevent="submit">
    <ol class="wizard-progress" aria-label="Étapes de création du calcul">
      <li v-for="item in steps" :key="item.number" :class="{ 'wizard-progress__item--active': step === item.number, 'wizard-progress__item--done': step > item.number }">
        <span>{{ step > item.number ? '✓' : item.number }}</span>
        <div><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></div>
      </li>
    </ol>

    <section v-if="step === 1" class="wizard-step" aria-labelledby="job-step-file">
      <div class="wizard-step__intro"><span class="eyebrow">Étape 1 sur 3</span><h2 id="job-step-file">Quel fichier voulez-vous calculer ?</h2><p>Commencez par donner un nom à votre projet et ajouter le fichier d’entrée.</p></div>
      <div class="job-form__grid">
        <label class="field job-form__wide"><span>Nom du projet</span><input v-model.trim="form.title" class="input" maxlength="120" required placeholder="Ex. Rendu intérieur — version 4"></label>
        <label class="field job-form__wide"><span>Description <small>facultative</small></span><textarea v-model.trim="form.description" class="textarea" maxlength="1000" placeholder="Contexte, version ou objectif de ce calcul"></textarea></label>
      </div>
      <label class="job-drop" :class="{ 'job-drop--ready': file }">
        <input type="file" required accept=".cfg,.scene,.txt,text/plain" @change="onFile">
        <span class="job-drop__icon"><UiIcon :name="file ? 'check' : 'upload'"/></span>
        <span><strong>{{ file ? file.name : 'Ajouter le fichier d’entrée' }}</strong><small>{{ file ? fileSize : 'CFG, SCENE ou texte · 16 Mo maximum' }}</small></span>
        <span class="job-drop__action">{{ file ? 'Remplacer' : 'Parcourir' }}</span>
      </label>
    </section>

    <section v-else-if="step === 2" class="wizard-step" aria-labelledby="job-step-options">
      <div class="wizard-step__intro"><span class="eyebrow">Étape 2 sur 3</span><h2 id="job-step-options">Comment voulez-vous l’exécuter ?</h2><p>La configuration recommandée convient à la plupart des projets. Les réglages techniques restent disponibles si nécessaire.</p></div>
      <div class="recommended-option"><span class="recommended-option__icon"><UiIcon name="sparkle"/></span><div><strong>Configuration recommandée</strong><p>Silicium répartit automatiquement le calcul sur les machines compatibles et vérifie les résultats.</p></div><UiStatusBadge status="operational" label="Recommandé" /></div>
      <details class="advanced-options">
        <summary><span><UiIcon name="code"/>Options avancées</span><UiIcon name="chevron"/></summary>
        <div class="job-form__configuration">
          <label><span class="field-label">Nombre de parties</span><strong>{{ form.fragmentCount }}</strong><input v-model.number="form.fragmentCount" type="range" min="1" max="256" step="1" aria-label="Nombre de parties"><small>Les parties sont réparties entre les machines disponibles.</small></label>
          <label><span class="field-label">Durée maximale</span><strong>{{ runtimeLabel }}</strong><input v-model.number="form.maxRuntimeSeconds" type="range" min="60" max="14400" step="60" aria-label="Durée maximale"><small>Une demande d’arrêt est émise si cette limite est atteinte.</small></label>
          <label class="field"><span>Priorité</span><select v-model="form.priority" class="select"><option value="low">Basse</option><option value="normal">Normale</option><option value="high">Haute</option><option value="urgent">Urgente</option></select></label>
        </div>
      </details>
    </section>

    <section v-else class="wizard-step" aria-labelledby="job-step-review">
      <div class="wizard-step__intro"><span class="eyebrow">Étape 3 sur 3</span><h2 id="job-step-review">Vérifier et lancer</h2><p>Tout est prêt. Vérifiez les informations principales avant de démarrer le calcul.</p></div>
      <div class="review-card">
        <div><span>Projet</span><strong>{{ form.title || 'Sans nom' }}</strong><small>{{ form.description || 'Aucune description' }}</small></div>
        <div><span>Fichier</span><strong>{{ file?.name || 'Aucun fichier' }}</strong><small>{{ fileSize }}</small></div>
        <div><span>Exécution</span><strong>Rendu d’image</strong><small>{{ form.fragmentCount }} parties · {{ runtimeLabel }} maximum</small></div>
      </div>
      <UiNotice title="Après le lancement">Le projet apparaîtra immédiatement dans vos projets avec son état de préparation.</UiNotice>
    </section>

    <UiNotice v-if="formError" tone="danger">{{ formError }}</UiNotice>
    <div class="job-form__footer">
      <p>{{ step < 3 ? 'Vous pourrez modifier les options avant le lancement.' : 'Le réseau prendra le relais dès que le fichier sera accepté.' }}</p>
      <div class="cluster">
        <UiButton v-if="step > 1" type="button" variant="ghost" @click="step--">Retour</UiButton>
        <UiButton v-if="step < 3" type="button" icon="arrow" :disabled="step === 1 && !stepOneReady" @click="nextStep">Continuer</UiButton>
        <UiButton v-else type="submit" icon="arrow" :loading="submitting">Lancer le calcul</UiButton>
      </div>
    </div>
  </form>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';

const props = withDefaults(defineProps<{ submitting?: boolean; error?: string }>(), { submitting: false, error: '' });
const emit = defineEmits<{ submit: [input: CreateJobInput] }>();
const MAX_INPUT_BYTES = 16 * 1024 * 1024;
const step = ref(1);
const file = ref<File | null>(null);
const localError = ref('');
const form = reactive({ title: '', description: '', workload: 'raytracer', priority: 'normal', fragmentCount: 64, maxRuntimeSeconds: 3600 });
const steps = [{ number: 1, title: 'Fichier', detail: 'Entrée du projet' }, { number: 2, title: 'Options', detail: 'Configuration' }, { number: 3, title: 'Lancer', detail: 'Vérification' }];
const stepOneReady = computed(() => Boolean(form.title.trim() && file.value && !localError.value));
const runtimeLabel = computed(() => form.maxRuntimeSeconds < 3600 ? `${Math.round(form.maxRuntimeSeconds / 60)} min` : `${(form.maxRuntimeSeconds / 3600).toFixed(form.maxRuntimeSeconds % 3600 ? 1 : 0)} h`);
const fileSize = computed(() => {
  if (!file.value) return '';
  return file.value.size >= 1024 * 1024 ? `${(file.value.size / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(.1, file.value.size / 1024).toFixed(1)} Ko`;
});
const formError = computed(() => localError.value || props.error);

function onFile(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0] || null;
  localError.value = '';
  file.value = selected;
  if (!selected) return;
  if (selected.size === 0) {
    file.value = null;
    localError.value = 'Le fichier de calcul ne peut pas être vide.';
  } else if (selected.size > MAX_INPUT_BYTES) {
    file.value = null;
    localError.value = 'Le fichier ne doit pas dépasser 16 Mo.';
  }
}

function nextStep() {
  localError.value = '';
  if (step.value === 1) {
    if (!form.title.trim()) { localError.value = 'Donnez un nom à votre projet pour continuer.'; return; }
    if (!file.value) { localError.value = 'Ajoutez un fichier d’entrée pour continuer.'; return; }
  }
  step.value = Math.min(3, step.value + 1);
}

function submit() {
  if (step.value !== 3 || !file.value || props.submitting || localError.value) return;
  emit('submit', { ...form, file: file.value });
}
</script>

<style scoped>
.job-form{display:grid;gap:1.35rem}.wizard-progress{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;margin:0;padding:0 0 1.25rem;border-bottom:1px solid var(--border);list-style:none}.wizard-progress li{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.55rem;min-width:0;color:var(--ink-400)}.wizard-progress li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border:1px solid var(--border);border-radius:50%;background:var(--surface-soft);font-family:var(--font-mono);font-size:.6rem}.wizard-progress li strong,.wizard-progress li small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wizard-progress li strong{font-size:.65rem}.wizard-progress li small{margin-top:.16rem;color:var(--ink-400);font-size:.55rem}.wizard-progress__item--active{color:var(--ink-950)!important}.wizard-progress__item--active>span,.wizard-progress__item--done>span{border-color:rgba(18,191,174,.2)!important;background:var(--mint-100)!important;color:var(--mint-700)}.wizard-progress__item--done{color:var(--mint-700)!important}.wizard-step{display:grid;gap:1.25rem}.wizard-step__intro{display:grid;gap:.5rem}.wizard-step__intro h2{margin:.15rem 0 0;color:var(--ink-950);font-size:1.35rem;letter-spacing:-.045em}.wizard-step__intro p{max-width:650px;margin:0;color:var(--ink-600);font-size:.72rem;line-height:1.6}.job-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.job-form__wide{grid-column:1/-1}.field span small{color:var(--ink-500);font-weight:500}.job-drop{display:grid;min-height:92px;grid-template-columns:auto 1fr auto;align-items:center;gap:1rem;padding:1rem;border:1px dashed var(--border-strong);border-radius:var(--radius-md);background:rgba(244,245,241,.45);cursor:pointer}.job-drop:hover,.job-drop--ready{border-color:var(--mint-500);background:var(--mint-100)}.job-drop input{position:absolute;width:1px;height:1px;opacity:0}.job-drop__icon{display:grid;width:2.7rem;height:2.7rem;place-items:center;border-radius:.75rem;background:white;color:var(--mint-700);box-shadow:var(--shadow-sm)}.job-drop__icon svg{width:1.1rem}.job-drop strong,.job-drop small{display:block}.job-drop strong{font-size:.76rem}.job-drop small{margin-top:.3rem;color:var(--ink-500);font-size:.62rem}.job-drop__action{padding:.58rem .72rem;border:1px solid var(--border-strong);border-radius:.55rem;background:white;font-size:.68rem;font-weight:750}.recommended-option{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.8rem;padding:1rem;border:1px solid rgba(18,191,174,.18);border-radius:var(--radius-md);background:var(--mint-100)}.recommended-option__icon{display:grid;width:2.4rem;height:2.4rem;place-items:center;border-radius:.7rem;background:white;color:var(--mint-700)}.recommended-option__icon svg{width:1rem}.recommended-option strong,.recommended-option p{display:block}.recommended-option strong{font-size:.76rem}.recommended-option p{margin:.25rem 0 0;color:var(--ink-600);font-size:.62rem;line-height:1.45}.advanced-options{border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.advanced-options summary{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.85rem 1rem;color:var(--ink-800);font-size:.7rem;font-weight:760;cursor:pointer;list-style:none}.advanced-options summary::-webkit-details-marker{display:none}.advanced-options summary>span{display:inline-flex;align-items:center;gap:.5rem}.advanced-options summary svg{width:.85rem}.advanced-options summary>svg{color:var(--ink-400);transition:transform .2s}.advanced-options[open] summary>svg{transform:rotate(90deg)}.job-form__configuration{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;padding:0 1rem 1rem}.job-form__configuration>label{display:grid;grid-template-columns:1fr auto;gap:.5rem;padding:.85rem;border:1px solid var(--border);border-radius:.7rem;background:white}.job-form__configuration>label:last-child{grid-template-columns:1fr;align-content:start}.job-form__configuration strong{font-size:.76rem}.job-form__configuration input{grid-column:1/-1;width:100%;accent-color:var(--mint-600)}.job-form__configuration small{grid-column:1/-1;color:var(--ink-500);font-size:.58rem;line-height:1.4}.field-label{font-size:.64rem;font-weight:700}.review-card{display:grid;grid-template-columns:repeat(3,1fr);gap:.6rem}.review-card>div{min-width:0;padding:.85rem;border:1px solid var(--border);border-radius:.75rem;background:var(--surface-soft)}.review-card span,.review-card strong,.review-card small{display:block}.review-card span{color:var(--ink-500);font-size:.57rem}.review-card strong{margin-top:.35rem;overflow:hidden;color:var(--ink-900);font-size:.7rem;text-overflow:ellipsis;white-space:nowrap}.review-card small{margin-top:.28rem;overflow:hidden;color:var(--ink-500);font-size:.58rem;text-overflow:ellipsis;white-space:nowrap}.job-form__footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-top:1rem;border-top:1px solid var(--border)}.job-form__footer p{max-width:430px;margin:0;color:var(--ink-500);font-size:.65rem;line-height:1.5}
@media(max-width:700px){.review-card{grid-template-columns:1fr}.recommended-option{grid-template-columns:auto 1fr}.recommended-option :deep(.status-badge){grid-column:2;justify-self:start}.job-form__configuration{grid-template-columns:1fr}}
@media(max-width:620px){.job-form__grid{grid-template-columns:1fr}.job-form__wide{grid-column:auto}.wizard-progress li small{display:none}.job-drop{grid-template-columns:auto 1fr}.job-drop__action{display:none}.job-form__footer{align-items:stretch;flex-direction:column}.job-form__footer .cluster{justify-content:flex-end}}
</style>
