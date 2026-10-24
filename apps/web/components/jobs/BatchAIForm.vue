<template>
  <div class="batch-ai">
    <label class="batch-ai__drop" :class="{ 'batch-ai__drop--ready': table, 'batch-ai__drop--over': dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
      <input type="file" :accept="BATCH_AI_ACCEPT" @change="onFile">
      <span class="batch-ai__drop-icon"><UiIcon :name="table ? 'check' : 'upload'"/></span>
      <span><strong>{{ fileName || t('batchAI.drop') }}</strong><small>{{ table ? t('batchAI.itemCount', { count: items.length }) + (skipped ? ` · ${t('batchAI.skipped', { count: skipped })}` : '') : t('batchAI.dropHint') }}</small></span>
      <span class="batch-ai__drop-action">{{ table ? t('jobForm.replace') : t('jobForm.browse') }}</span>
    </label>
    <UiNotice v-if="fileError" tone="danger">{{ fileError }}</UiNotice>

    <div v-if="table" class="batch-ai__source">
      <div v-if="plainText" class="batch-ai__choices" role="radiogroup" :aria-label="t('batchAI.splitAria')">
        <button v-for="mode in (['lines', 'paragraphs'] as const)" :key="mode" type="button" role="radio" :aria-checked="split === mode" :class="{ active: split === mode }" @click="setSplit(mode)">{{ t(`batchAI.split.${mode}`) }}</button>
      </div>
      <label v-else-if="table.columns.length > 1" class="field"><span>{{ t('batchAI.column') }}</span><select v-model.number="column" class="select"><option v-for="(name, index) in table.columns" :key="index" :value="index">{{ name }}</option></select></label>
      <div class="batch-ai__preview">
        <span class="eyebrow">{{ t('batchAI.preview') }}</span>
        <ol><li v-for="(item, index) in items.slice(0, 3)" :key="index">{{ item }}</li></ol>
      </div>
    </div>

    <fieldset class="batch-ai__tasks">
      <legend>{{ t('batchAI.taskTitle') }}</legend>
      <div class="batch-ai__task-grid" role="radiogroup" :aria-label="t('batchAI.taskTitle')">
        <button v-for="item in BATCH_TASKS" :key="item" type="button" role="radio" :aria-checked="task === item" :class="{ active: task === item }" @click="setTask(item)">
          <strong>{{ t(`batchAI.tasks.${item}.label`) }}</strong><small>{{ t(`batchAI.tasks.${item}.hint`) }}</small>
        </button>
      </div>
    </fieldset>

    <label class="field"><span>{{ task === 'free' ? t('batchAI.instructionOptional') : t('batchAI.instruction') }}</span><textarea v-model="instruction" class="textarea" rows="3" :maxlength="BATCH_AI_LIMITS.instructionChars" :placeholder="t(`batchAI.tasks.${task}.placeholder`)" @input="instructionEdited = true"></textarea><small>{{ task === 'free' ? t('batchAI.freeHint') : t('batchAI.instructionHint') }}</small></label>
    <label v-if="kind !== 'text'" class="field"><span>{{ kind === 'label' ? t('batchAI.labels') : t('batchAI.fields') }}</span><input v-model="names" class="input" :placeholder="kind === 'label' ? t('batchAI.labelsPlaceholder') : t('batchAI.fieldsPlaceholder')"><small>{{ kind === 'label' ? t('batchAI.labelsHint') : t('batchAI.fieldsHint') }}</small></label>

    <label class="batch-ai__consent">
      <input v-model="consent" type="checkbox">
      <span><strong>{{ t('batchAI.consent') }}</strong><small>{{ t('batchAI.consentHint') }}</small></span>
    </label>
  </div>
</template>

<script setup lang="ts">
// Step 1 of a batch AI job ("Traitement par IA"): the file is read in the
// browser, the user picks the column (or how a text is cut), sees the first
// items, picks a kind of task and writes the instruction. The parent gets
// the request as a file, or why it cannot be sent yet.
import { BATCH_AI_ACCEPT, BATCH_AI_LIMITS, BATCH_TASKS, TASK_OUTPUT, buildRequest, guessTextColumn, isPlainText, itemsOf, readItemTable, requestFile, requestProblem, type BatchAIState, type BatchTask, type ItemTable, type TextSplit } from '~/utils/batchAI';

const emit = defineEmits<{ update: [state: BatchAIState] }>();
const { t, formatBytes } = useI18n();

const fileName = ref('');
const fileText = ref('');
const fileError = ref('');
const dragging = ref(false);
const split = ref<TextSplit>('lines');
const table = ref<ItemTable | null>(null);
const column = ref(0);
const task = ref<BatchTask>('summarize');
const instruction = ref(t('batchAI.tasks.summarize.default'));
const instructionEdited = ref(false);
const names = ref('');
const consent = ref(false);

const plainText = computed(() => isPlainText(fileName.value));
const kind = computed(() => TASK_OUTPUT[task.value].kind);
const extracted = computed(() => (table.value ? itemsOf(table.value, column.value) : { items: [], skipped: 0 }));
const items = computed(() => extracted.value.items);
const skipped = computed(() => extracted.value.skipped);
const columnName = computed(() => table.value?.columns[column.value] || '');
const input = computed(() => ({ task: task.value, instruction: instruction.value, names: names.value, items: items.value, source: { name: fileName.value, column: plainText.value ? '' : columnName.value } }));
const problem = computed(() => (!table.value ? t('batchAI.problems.noFile') : requestProblem(input.value)));

watch([problem, consent, () => items.value.length, task], () => {
  emit('update', {
    build: () => (problem.value ? null : requestFile(buildRequest(input.value))),
    problem: problem.value,
    itemCount: items.value.length,
    task: task.value,
    consent: consent.value,
  });
}, { immediate: true });

function read() {
  fileError.value = '';
  table.value = null;
  if (!fileText.value) return;
  try {
    table.value = readItemTable(fileName.value, fileText.value, split.value);
    column.value = guessTextColumn(table.value);
  } catch (failure) {
    fileError.value = failure instanceof Error ? failure.message : String(failure);
  }
}

async function load(file: File | undefined) {
  if (!file) return;
  fileName.value = file.name;
  fileText.value = '';
  if (file.size === 0) { fileError.value = t('jobForm.emptyFile'); table.value = null; return; }
  if (file.size > BATCH_AI_LIMITS.fileBytes) { fileError.value = t('batchAI.file.tooLarge', { size: formatBytes(BATCH_AI_LIMITS.fileBytes) }); table.value = null; return; }
  fileText.value = await file.text();
  read();
}

function onFile(event: Event) {
  const element = event.target as HTMLInputElement;
  void load(element.files?.[0]);
  element.value = '';
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  void load(event.dataTransfer?.files?.[0]);
}

function setSplit(mode: TextSplit) {
  split.value = mode;
  read();
}

function setTask(next: BatchTask) {
  task.value = next;
  if (!instructionEdited.value || !instruction.value.trim()) {
    instruction.value = t(`batchAI.tasks.${next}.default`);
    instructionEdited.value = false;
  }
  if (TASK_OUTPUT[next].kind !== 'text') names.value = t(`batchAI.tasks.${next}.names`);
}
</script>

<style scoped>
.batch-ai{display:grid;gap:1rem}
.batch-ai__drop{position:relative;display:grid;min-height:88px;grid-template-columns:auto 1fr auto;align-items:center;gap:1rem;padding:1rem;border:1px dashed var(--border-strong);border-radius:var(--radius-md);background:rgba(244,245,241,.45);cursor:pointer}.batch-ai__drop:hover,.batch-ai__drop--ready,.batch-ai__drop--over{border-color:var(--mint-500);background:var(--mint-100)}.batch-ai__drop input{position:absolute;width:1px;height:1px;opacity:0}.batch-ai__drop-icon{display:grid;width:2.7rem;height:2.7rem;place-items:center;border-radius:.75rem;background:white;color:var(--mint-700);box-shadow:var(--shadow-sm)}.batch-ai__drop-icon svg{width:1.1rem}.batch-ai__drop strong,.batch-ai__drop small{display:block;overflow-wrap:anywhere}.batch-ai__drop strong{font-size:.9375rem}.batch-ai__drop small{margin-top:.3rem;color:var(--ink-500);font-size:.9375rem}.batch-ai__drop-action{padding:.58rem .72rem;border:1px solid var(--border-strong);border-radius:.55rem;background:white;font-size:.9375rem;font-weight:750}
.batch-ai__source{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:1rem;align-items:start}.batch-ai__preview{min-width:0;padding:.8rem .9rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.batch-ai__preview ol{display:grid;gap:.4rem;margin:.5rem 0 0;padding-left:1.1rem;color:var(--ink-700);font-size:.9375rem;line-height:1.45}.batch-ai__preview li{display:-webkit-box;overflow:hidden;overflow-wrap:anywhere;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-clamp:2}
.batch-ai__choices{display:flex;flex-wrap:wrap;gap:.4rem}.batch-ai__choices button,.batch-ai__task-grid button{border:1px solid var(--border);border-radius:var(--radius-md);background:white;color:var(--ink-700);font:inherit;text-align:left;cursor:pointer}.batch-ai__choices button{padding:.55rem .8rem;font-size:.9375rem;font-weight:700}.batch-ai__choices button.active,.batch-ai__task-grid button.active{border-color:var(--mint-600);background:var(--mint-100);color:var(--mint-700)}.batch-ai__choices button:hover,.batch-ai__task-grid button:hover{border-color:var(--mint-500)}
.batch-ai__tasks{margin:0;padding:0;border:0}.batch-ai__tasks legend{margin-bottom:.5rem;color:var(--ink-900);font-size:.9375rem;font-weight:700}.batch-ai__task-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.5rem}.batch-ai__task-grid button{display:grid;align-content:start;gap:.2rem;padding:.7rem .75rem}.batch-ai__task-grid strong{color:var(--ink-950);font-size:.9375rem}.batch-ai__task-grid small{color:var(--ink-600);font-size:.9375rem;line-height:1.35}
.field small{color:var(--ink-500);font-size:.9375rem;line-height:1.4}
.batch-ai__consent{display:grid;grid-template-columns:auto 1fr;gap:.7rem;padding:.85rem 1rem;border:1px solid rgba(217,119,6,.25);border-radius:var(--radius-md);background:#fff8eb;cursor:pointer}.batch-ai__consent input{margin-top:.15rem;accent-color:var(--mint-600)}.batch-ai__consent strong,.batch-ai__consent small{display:block}.batch-ai__consent strong{color:var(--ink-900);font-size:.9375rem}.batch-ai__consent small{margin-top:.25rem;color:var(--ink-600);font-size:.9375rem;line-height:1.45}
@media(max-width:900px){.batch-ai__task-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.batch-ai__source{grid-template-columns:1fr}}
@media(max-width:560px){.batch-ai__drop{grid-template-columns:auto 1fr}.batch-ai__drop-action{display:none}.batch-ai__task-grid{grid-template-columns:1fr}}
</style>
