<template>
  <form class="job-form" :aria-busy="submitting" novalidate @submit.prevent="submit">
    <ol class="wizard-progress" :aria-label="t('jobForm.stepsAria')">
      <li v-for="item in steps" :key="item.number" :class="{ 'wizard-progress__item--active': step === item.number, 'wizard-progress__item--done': step > item.number }">
        <span>{{ step > item.number ? '✓' : item.number }}</span>
        <div><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></div>
      </li>
    </ol>

    <section v-if="step === 1" class="wizard-step" aria-labelledby="job-step-file">
      <div class="wizard-step__intro"><span class="eyebrow">{{ t('jobForm.stepOf', { step: 1 }) }}</span><h2 id="job-step-file">{{ t('jobForm.fileTitle') }}</h2><p>{{ t('jobForm.fileText') }}</p></div>
      <div class="job-form__grid">
        <label class="field job-form__wide"><span>{{ t('jobForm.name') }}</span><input v-model.trim="form.title" class="input" :maxlength="LIMITS.jobTitle" required :placeholder="t('jobForm.namePlaceholder')"></label>
        <label class="field job-form__wide"><span>{{ t('jobForm.description') }} <small>{{ t('common.optional') }}</small></span><textarea v-model.trim="form.description" class="textarea" :maxlength="LIMITS.jobDescription" :placeholder="t('jobForm.descriptionPlaceholder')"></textarea></label>
        <label class="field job-form__wide"><span>{{ t('jobForm.type') }}</span><select v-model="form.workload" class="select" :disabled="Boolean(collectionId)"><option v-for="item in workloads" :key="item.id" :value="item.id">{{ item.label }}</option></select><small>{{ selectedWorkload.hint }} <NuxtLink :to="`/workloads#${selectedWorkload.anchor}`" class="job-form__help">{{ t('jobForm.typeHelp') }}</NuxtLink></small></label>
      </div>
      <template v-if="documentMode">
        <UiNotice v-if="collectionId" :title="t('jobForm.addingTitle')">{{ t('jobForm.addingText') }}</UiNotice>
        <label class="job-drop" :class="{ 'job-drop--ready': documents.length, 'job-drop--over': dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
          <input type="file" multiple :accept="DOCUMENT_ACCEPT" @change="onDocuments">
          <span class="job-drop__icon"><UiIcon :name="documents.length ? 'check' : 'upload'"/></span>
          <span><strong>{{ documents.length ? t('jobForm.documentsReady', { count: documents.length }) : t('jobForm.dropDocuments') }}</strong><small>{{ documents.length ? documentsSize : t('jobForm.documentsHint') }}</small></span>
          <span class="job-drop__action">{{ documents.length ? t('jobForm.add') : t('jobForm.browse') }}</span>
        </label>
        <ul v-if="documents.length" class="document-list" :aria-label="t('jobForm.chosen')">
          <li v-for="(document, index) in documents" :key="`${document.name}-${document.size}`"><span>{{ document.name }}</span><small>{{ formatBytes(document.size) }}</small><button type="button" :aria-label="t('jobForm.remove', { name: document.name })" @click="removeDocument(index)"><UiIcon name="x"/></button></li>
        </ul>
        <label class="sharing-consent">
          <input v-model="acknowledgeSharing" type="checkbox">
          <span><strong>{{ t('jobForm.consent') }}</strong><small>{{ t('jobForm.consentHint') }}</small></span>
        </label>
      </template>
      <template v-else>
        <div v-if="raytracerMode" class="scene-source" role="radiogroup" :aria-label="t('jobForm.sceneModes.aria')">
          <button v-for="source in (['compose', 'import'] as const)" :key="source" type="button" role="radio" class="scene-source__option" :class="{ 'scene-source__option--active': sceneSource === source }" :aria-checked="sceneSource === source" @click="setSceneSource(source)">
            <UiIcon :name="source === 'compose' ? 'sparkle' : 'upload'"/>
            <span><strong>{{ t(`jobForm.sceneModes.${source}`) }}</strong><small>{{ t(`jobForm.sceneModes.${source}Hint`) }}</small></span>
          </button>
        </div>
        <SceneEditor v-if="composeMode" v-model="scene" :title="form.title" />
        <template v-else>
          <label class="job-drop" :class="{ 'job-drop--ready': file }">
            <input type="file" required :accept="selectedWorkload.accept" @change="onFile">
            <span class="job-drop__icon"><UiIcon :name="file ? 'check' : 'upload'"/></span>
            <span><strong>{{ file ? file.name : t('jobForm.addInput') }}</strong><small>{{ file ? fileSize : t('jobForm.maxSize', { hint: selectedWorkload.fileHint }) }}</small></span>
            <span class="job-drop__action">{{ file ? t('jobForm.replace') : t('jobForm.browse') }}</span>
          </label>
          <SceneIssues v-if="raytracerMode && sceneReport" :report="sceneReport" :limits="sceneLimits" @open-editor="openInEditor" />
        </template>
      </template>
    </section>

    <section v-else-if="step === 2" class="wizard-step" aria-labelledby="job-step-options">
      <div class="wizard-step__intro"><span class="eyebrow">{{ t('jobForm.stepOf', { step: 2 }) }}</span><h2 id="job-step-options">{{ t('jobForm.optionsTitle') }}</h2><p>{{ t('jobForm.optionsText') }}</p></div>
      <div class="recommended-option"><span class="recommended-option__icon"><UiIcon name="sparkle"/></span><div><strong>{{ t('jobForm.recommended') }}</strong><p>{{ documentMode ? t('jobForm.recommendedDocuments') : t('jobForm.recommendedDefault') }}</p></div><UiStatusBadge status="operational" :label="t('jobForm.recommendedBadge')" /></div>
      <details v-if="!documentMode" class="advanced-options">
        <summary><span><UiIcon name="code"/>{{ t('jobForm.advanced') }}</span><UiIcon name="chevron"/></summary>
        <div class="job-form__configuration">
          <label><span class="field-label">{{ t('jobForm.parts') }}</span><strong>{{ form.fragmentCount }}</strong><input v-model.number="form.fragmentCount" type="range" min="1" max="256" step="1" :aria-label="t('jobForm.parts')"><small>{{ t('jobForm.partsHint') }}<template v-if="hashMode"> {{ t('jobForm.hashOnePart') }}</template></small></label>
          <label><span class="field-label">{{ t('jobForm.maxDuration') }}</span><strong>{{ runtimeLabel }}</strong><input v-model.number="form.maxRuntimeSeconds" type="range" min="60" max="14400" step="60" :aria-label="t('jobForm.maxDuration')"><small>{{ t('jobForm.maxDurationHint') }}</small></label>
          <label class="field"><span>{{ t('jobForm.priority') }}</span><select v-model="form.priority" class="select"><option v-for="priority in priorities" :key="priority" :value="priority">{{ t(`jobForm.priorities.${priority}`) }}</option></select></label>
        </div>
      </details>
    </section>

    <section v-else class="wizard-step" aria-labelledby="job-step-review">
      <div class="wizard-step__intro"><span class="eyebrow">{{ t('jobForm.stepOf', { step: 3 }) }}</span><h2 id="job-step-review">{{ t('jobForm.reviewTitle') }}</h2><p>{{ t('jobForm.reviewText') }}</p></div>
      <div class="review-card">
        <div><span>{{ t('jobForm.project') }}</span><strong>{{ form.title || t('jobForm.untitled') }}</strong><small>{{ form.description || t('jobForm.noDescription') }}</small></div>
        <div v-if="documentMode"><span>{{ t('jobForm.documents') }}</span><strong>{{ t('jobForm.documentCount', { count: documents.length }) }}</strong><small>{{ documentsSize }}</small></div>
        <div v-else><span>{{ raytracerMode ? t('jobForm.scene') : t('jobForm.file') }}</span><strong>{{ file?.name || t('jobForm.noFile') }}</strong><small>{{ reviewScene || fileSize }}</small></div>
        <div><span>{{ t('jobForm.execution') }}</span><strong>{{ selectedWorkload.label }}</strong><small>{{ documentMode ? t('jobForm.autoSplit') : t('jobForm.partCount', { count: form.fragmentCount }) }} · {{ t('jobForm.maximum', { duration: runtimeLabel }) }}</small></div>
      </div>
      <UiNotice :title="t('jobForm.afterLaunch')">{{ t('jobForm.afterLaunchText') }}</UiNotice>
    </section>

    <UiNotice v-if="formError" tone="danger">{{ formError }}</UiNotice>
    <div class="job-form__footer">
      <p>{{ step < 3 ? t('jobForm.footerEdit') : t('jobForm.footerLaunch') }}</p>
      <div class="cluster">
        <UiButton v-if="step > 1" type="button" variant="ghost" @click="step--">{{ t('common.back') }}</UiButton>
        <UiButton v-if="step < 3" type="button" icon="arrow" :disabled="step === 1 && !stepOneReady" @click="nextStep">{{ t('common.continue') }}</UiButton>
        <UiButton v-else type="submit" icon="arrow" :loading="submitting">{{ t('jobForm.launch') }}</UiButton>
      </div>
    </div>
  </form>
</template>

<script setup lang="ts">
import type { CreateJobInput } from '~/composables/useJobs';
import { DOCUMENT_ACCEPT, DOCUMENT_SEARCH_WORKLOAD, documentSelectionError, isDocumentSearchWorkload, mergeDocumentSelection } from '~/utils/documents';
import { isHashWorkload, sceneSummaryText } from '~/utils/jobs';
import { editorLimits, sceneFileName, sceneFromText, sceneToCfg, type SceneModel } from '~/utils/scene';
import { checkScene } from '~/utils/sceneCheck';
import { sceneTemplate } from '~/utils/sceneTemplates';
import { firstProblem, jobDescriptionProblem, jobTitleProblem, LIMITS } from '~/utils/validation';

const props = withDefaults(defineProps<{ submitting?: boolean; error?: string; initialWorkload?: string; collectionId?: string }>(), { submitting: false, error: '', initialWorkload: '', collectionId: '' });
const emit = defineEmits<{ submit: [input: CreateJobInput] }>();
const { t, tl, formatBytes } = useI18n();
const MAX_INPUT_BYTES = 16 * 1024 * 1024;
const priorities = ['low', 'normal', 'high', 'urgent'];
const step = ref(1);
const file = ref<File | null>(null);
const localError = ref('');
const form = reactive({ title: '', description: '', workload: props.collectionId ? DOCUMENT_SEARCH_WORKLOAD : (props.initialWorkload || 'raytracer'), priority: 'normal', fragmentCount: 8, maxRuntimeSeconds: 3600 });
const documents = ref<File[]>([]);
const acknowledgeSharing = ref(false);
const dragging = ref(false);
/** Raytracer jobs: the scene is composed in the editor, or imported as a `.cfg`. */
const sceneSource = ref<'compose' | 'import'>('compose');
const scene = ref<SceneModel>(sceneTemplate('demo'));
/** Text of the imported `.cfg`, checked before it is sent. */
const sceneText = ref('');
/** Workloads the Rust node runs (BackEnd `ValidateWorkload`); `anchor` is their section of /workloads. */
const workloads = computed(() => [
  { id: 'raytracer', anchor: 'raytracer', ...workloadCopy('raytracer'), accept: '.cfg,.scene,.txt,text/plain' },
  { id: 'calcul/integrity/sha256', anchor: 'sha256', ...workloadCopy('sha256'), accept: '' },
  { id: DOCUMENT_SEARCH_WORKLOAD, anchor: 'documents', ...workloadCopy('documents'), accept: DOCUMENT_ACCEPT },
]);
function workloadCopy(key: string) {
  return { label: t(`jobForm.workloads.${key}.label`), hint: t(`jobForm.workloads.${key}.hint`), fileHint: t(`jobForm.workloads.${key}.fileHint`) };
}
const documentMode = computed(() => isDocumentSearchWorkload(form.workload));
const hashMode = computed(() => isHashWorkload(form.workload));
const raytracerMode = computed(() => form.workload === 'raytracer');
const composeMode = computed(() => raytracerMode.value && sceneSource.value === 'compose');
const sceneReport = computed(() => (raytracerMode.value && sceneText.value ? checkScene(sceneText.value) : null));
const sceneReady = computed(() => (composeMode.value ? scene.value.objects.length > 0 : !raytracerMode.value || !sceneReport.value || sceneReport.value.valid));
/** Resolution, objects and lights of the scene, for the review step. */
const reviewScene = computed(() => {
  if (!raytracerMode.value) return null;
  const report = composeMode.value ? checkScene(sceneToCfg(scene.value)) : sceneReport.value;
  return report ? sceneSummaryText(report.scene) : null;
});
/** What the imported file uses that the editor cannot show. */
const sceneLimits = computed(() => (sceneText.value ? editorLimits(sceneText.value) : []));
const selectedWorkload = computed(() => workloads.value.find((item) => item.id === form.workload) || workloads.value[0]!);
const steps = computed(() => tl<{ title: string; detail: string }>('jobForm.steps').map((item, index) => ({ ...item, number: index + 1 })));
const textProblem = computed(() => firstProblem(jobTitleProblem(form.title), jobDescriptionProblem(form.description)));
const stepOneReady = computed(() => Boolean(form.title.trim() && !localError.value && !textProblem.value && sceneReady.value && (documentMode.value ? documents.value.length && acknowledgeSharing.value : composeMode.value || file.value)));
const documentsSize = computed(() => formatBytes(documents.value.reduce((total, document) => total + document.size, 0)));
const runtimeLabel = computed(() => form.maxRuntimeSeconds < 3600 ? `${Math.round(form.maxRuntimeSeconds / 60)} min` : `${(form.maxRuntimeSeconds / 3600).toFixed(form.maxRuntimeSeconds % 3600 ? 1 : 0)} h`);
const fileSize = computed(() => (file.value ? formatBytes(file.value.size) : ''));
const formError = computed(() => localError.value || (textProblem.value ? t(textProblem.value) : '') || props.error);

function onFile(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0] || null;
  localError.value = '';
  sceneText.value = '';
  file.value = selected;
  if (!selected) return;
  if (selected.size === 0) {
    file.value = null;
    localError.value = t('jobForm.emptyFile');
  } else if (selected.size > MAX_INPUT_BYTES) {
    file.value = null;
    localError.value = t('jobForm.tooLarge');
  } else if (raytracerMode.value) {
    selected.text().then((text) => { if (file.value === selected) sceneText.value = text; }).catch(() => {});
  }
}

function setSceneSource(source: 'compose' | 'import') {
  if (sceneSource.value === source) return;
  sceneSource.value = source;
  file.value = null;
  sceneText.value = '';
  localError.value = '';
}

/** Imported file → editor: keeps what the engine reads from it. */
function openInEditor() {
  if (!sceneText.value) return;
  try {
    scene.value = sceneFromText(sceneText.value);
  } catch {
    return;
  }
  setSceneSource('compose');
}

function addDocuments(added: File[]) {
  const next = mergeDocumentSelection(documents.value, added);
  localError.value = documentSelectionError(next);
  if (!localError.value) documents.value = next;
}

function onDocuments(event: Event) {
  const input = event.target as HTMLInputElement;
  addDocuments(Array.from(input.files || []));
  input.value = '';
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  addDocuments(Array.from(event.dataTransfer?.files || []));
}

function removeDocument(index: number) {
  documents.value = documents.value.filter((_, position) => position !== index);
  localError.value = '';
}

watch(() => form.workload, () => { localError.value = ''; });

function nextStep() {
  localError.value = '';
  if (step.value === 1) {
    if (!form.title.trim()) { localError.value = t('jobForm.nameRequired'); return; }
    if (textProblem.value) return;
    if (documentMode.value) {
      localError.value = documentSelectionError(documents.value);
      if (localError.value) return;
      if (!acknowledgeSharing.value) { localError.value = t('jobForm.consentRequired'); return; }
    } else if (composeMode.value) {
      if (!scene.value.objects.length) { localError.value = t('jobForm.sceneEmpty'); return; }
      file.value = new File([sceneToCfg(scene.value, form.title)], sceneFileName(form.title), { type: 'text/plain' });
    } else if (!file.value) { localError.value = t('jobForm.fileRequired'); return; }
    else if (sceneReport.value && !sceneReport.value.valid) { localError.value = t('jobForm.sceneInvalid'); return; }
  }
  step.value = Math.min(3, step.value + 1);
}

function submit() {
  if (step.value !== 3 || props.submitting || localError.value || textProblem.value) return;
  if (documentMode.value) {
    if (!documents.value.length || !acknowledgeSharing.value) return;
    emit('submit', { ...form, files: documents.value, acknowledgeSharing: true, collectionId: props.collectionId || undefined });
    return;
  }
  if (!file.value) return;
  emit('submit', { ...form, file: file.value });
}
</script>

<style scoped>
.job-form{display:grid;gap:1.35rem}.wizard-progress{display:grid;grid-template-columns:repeat(3,1fr);gap:.5rem;margin:0;padding:0 0 1.25rem;border-bottom:1px solid var(--border);list-style:none}.wizard-progress li{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.55rem;min-width:0;color:var(--ink-500)}.wizard-progress li>span{display:grid;width:1.8rem;height:1.8rem;place-items:center;border:1px solid var(--border);border-radius:50%;background:var(--surface-soft);font-family:var(--font-mono);font-size:.864rem}.wizard-progress li strong,.wizard-progress li small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.wizard-progress li strong{font-size:.881rem}.wizard-progress li small{margin-top:.16rem;color:var(--ink-500);font-size:.847rem}.wizard-progress__item--active{color:var(--ink-950)!important}.wizard-progress__item--active>span,.wizard-progress__item--done>span{border-color:rgba(18,191,174,.2)!important;background:var(--mint-100)!important;color:var(--mint-700)}.wizard-progress__item--done{color:var(--mint-700)!important}.wizard-step{display:grid;gap:1.25rem}.wizard-step__intro{display:grid;gap:.5rem}.wizard-step__intro h2{margin:.15rem 0 0;color:var(--ink-950);font-size:1.35rem;letter-spacing:-.045em}.wizard-step__intro p{max-width:650px;margin:0;color:var(--ink-600);font-size:.905rem;line-height:1.6}.job-form__grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.job-form__wide{grid-column:1/-1}.field span small{color:var(--ink-500);font-weight:500}.job-form__help{color:var(--mint-700);font-weight:700;text-decoration:underline;text-underline-offset:2px}.job-drop{display:grid;min-height:92px;grid-template-columns:auto 1fr auto;align-items:center;gap:1rem;padding:1rem;border:1px dashed var(--border-strong);border-radius:var(--radius-md);background:rgba(244,245,241,.45);cursor:pointer}.job-drop:hover,.job-drop--ready,.job-drop--over{border-color:var(--mint-500);background:var(--mint-100)}.document-list{display:grid;gap:.35rem;margin:0;padding:0;list-style:none}.document-list li{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:.7rem;padding:.5rem .7rem;border:1px solid var(--border);border-radius:.6rem;background:white;font-size:.884rem}.document-list span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.document-list small{color:var(--ink-500);font-size:.857rem}.document-list button{display:grid;width:1.6rem;height:1.6rem;place-items:center;border:0;border-radius:.4rem;background:transparent;color:var(--ink-500);cursor:pointer}.document-list button:hover{background:var(--surface-soft);color:var(--ink-900)}.document-list svg{width:.75rem}.sharing-consent{display:grid;grid-template-columns:auto 1fr;gap:.7rem;padding:.85rem 1rem;border:1px solid rgba(217,119,6,.25);border-radius:var(--radius-md);background:#fff8eb;cursor:pointer}.sharing-consent input{margin-top:.15rem;accent-color:var(--mint-600)}.sharing-consent strong,.sharing-consent small{display:block}.sharing-consent strong{color:var(--ink-900);font-size:.891rem}.sharing-consent small{margin-top:.25rem;color:var(--ink-600);font-size:.864rem;line-height:1.45}.job-drop input{position:absolute;width:1px;height:1px;opacity:0}.job-drop__icon{display:grid;width:2.7rem;height:2.7rem;place-items:center;border-radius:.75rem;background:white;color:var(--mint-700);box-shadow:var(--shadow-sm)}.job-drop__icon svg{width:1.1rem}.job-drop strong,.job-drop small{display:block}.job-drop strong{font-size:.918rem}.job-drop small{margin-top:.3rem;color:var(--ink-500);font-size:.87rem}.job-drop__action{padding:.58rem .72rem;border:1px solid var(--border-strong);border-radius:.55rem;background:white;font-size:.891rem;font-weight:750}.recommended-option{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.8rem;padding:1rem;border:1px solid rgba(18,191,174,.18);border-radius:var(--radius-md);background:var(--mint-100)}.recommended-option__icon{display:grid;width:2.4rem;height:2.4rem;place-items:center;border-radius:.7rem;background:white;color:var(--mint-700)}.recommended-option__icon svg{width:1rem}.recommended-option strong,.recommended-option p{display:block}.recommended-option strong{font-size:.918rem}.recommended-option p{margin:.25rem 0 0;color:var(--ink-600);font-size:.87rem;line-height:1.45}.advanced-options{border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.advanced-options summary{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.85rem 1rem;color:var(--ink-800);font-size:.898rem;font-weight:760;cursor:pointer;list-style:none}.advanced-options summary::-webkit-details-marker{display:none}.advanced-options summary>span{display:inline-flex;align-items:center;gap:.5rem}.advanced-options summary svg{width:.85rem}.advanced-options summary>svg{color:var(--ink-400);transition:transform .2s}.advanced-options[open] summary>svg{transform:rotate(90deg)}.job-form__configuration{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;padding:0 1rem 1rem}.job-form__configuration>label{display:grid;grid-template-columns:1fr auto;gap:.5rem;padding:.85rem;border:1px solid var(--border);border-radius:.7rem;background:white}.job-form__configuration>label:last-child{grid-template-columns:1fr;align-content:start}.job-form__configuration strong{font-size:.918rem}.job-form__configuration input{grid-column:1/-1;width:100%;accent-color:var(--mint-600)}.job-form__configuration small{grid-column:1/-1;color:var(--ink-500);font-size:.857rem;line-height:1.4}.field-label{font-size:.877rem;font-weight:700}.review-card{display:grid;grid-template-columns:repeat(3,1fr);gap:.6rem}.review-card>div{min-width:0;padding:.85rem;border:1px solid var(--border);border-radius:.75rem;background:var(--surface-soft)}.review-card span,.review-card strong,.review-card small{display:block}.review-card span{color:var(--ink-500);font-size:.853rem}.review-card strong{margin-top:.35rem;overflow:hidden;color:var(--ink-900);font-size:.898rem;text-overflow:ellipsis;white-space:nowrap}.review-card small{margin-top:.28rem;overflow:hidden;color:var(--ink-500);font-size:.857rem;text-overflow:ellipsis;white-space:nowrap}.job-form__footer{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding-top:1rem;border-top:1px solid var(--border)}.job-form__footer p{max-width:430px;margin:0;color:var(--ink-500);font-size:.881rem;line-height:1.5}
.scene-source{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}.scene-source__option{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:.65rem;padding:.75rem .85rem;border:1px solid var(--border);border-radius:var(--radius-md);background:white;color:var(--ink-700);font:inherit;text-align:left;cursor:pointer}.scene-source__option:hover{border-color:var(--mint-500)}.scene-source__option--active{border-color:var(--mint-600);background:var(--mint-100);color:var(--mint-700)}.scene-source__option svg{width:1rem}.scene-source__option strong,.scene-source__option small{display:block}.scene-source__option strong{color:var(--ink-950);font-size:.9rem}.scene-source__option small{margin-top:.15rem;color:var(--ink-600);font-size:.82rem}
@media(max-width:700px){.review-card{grid-template-columns:1fr}.recommended-option{grid-template-columns:auto 1fr}.recommended-option :deep(.status-badge){grid-column:2;justify-self:start}.job-form__configuration{grid-template-columns:1fr}}
@media(max-width:620px){.job-form__grid{grid-template-columns:1fr}.job-form__wide{grid-column:auto}.wizard-progress li small{display:none}.job-drop{grid-template-columns:auto 1fr}.job-drop__action{display:none}.job-form__footer{align-items:stretch;flex-direction:column}.job-form__footer .cluster{justify-content:flex-end}}
</style>
