<template>
  <div class="catalog-ai">
    <UiNotice v-if="loadError" tone="danger">{{ loadError }}</UiNotice>
    <UiNotice v-else-if="tasksData?.sync.failed" :title="t('catalogAI.syncFailedTitle')">{{ t('catalogAI.syncFailed') }}</UiNotice>

    <fieldset class="catalog-ai__block">
      <legend>{{ t('catalogAI.taskTitle') }}</legend>
      <div v-for="group in groups" :key="group.category" class="catalog-ai__category">
        <span class="eyebrow">{{ t(`catalogAI.categories.${group.category}`) }}</span>
        <div class="catalog-ai__tasks" role="radiogroup" :aria-label="t(`catalogAI.categories.${group.category}`)">
          <button v-for="item in group.tasks" :key="item.id" type="button" role="radio" :aria-checked="task === item.id" :disabled="!item.networkReady" :class="{ active: task === item.id }" @click="selectTask(item.id)">
            <strong>{{ item.label }}</strong>
            <small>{{ item.networkReady ? t('catalogAI.modelCount', { count: item.models }) : t('catalogAI.soon') }}</small>
          </button>
        </div>
      </div>
    </fieldset>

    <fieldset v-if="task" class="catalog-ai__block">
      <legend>{{ t('catalogAI.modelTitle') }}</legend>
      <input v-model.trim="search" class="input" type="search" :placeholder="t('catalogAI.searchPlaceholder')" :aria-label="t('catalogAI.searchPlaceholder')">
      <p v-if="!models.length && !modelsLoading" class="catalog-ai__empty">{{ t('catalogAI.noModel') }}</p>
      <ul class="catalog-ai__models" role="radiogroup" :aria-label="t('catalogAI.modelTitle')">
        <li v-for="model in models" :key="model.key">
          <button type="button" role="radio" :aria-checked="selected?.key === model.key" :class="{ active: selected?.key === model.key }" @click="selected = model">
            <span class="catalog-ai__model-name">{{ model.repository }}</span>
            <span class="catalog-ai__model-meta">{{ modelSize(model.totalBytes) }} · {{ t(`catalogAI.classes.${model.hardwareClass}`) }} · {{ model.licence }} · {{ t('catalogAI.downloads', { count: model.downloads }) }}</span>
          </button>
          <a :href="model.hubUrl" target="_blank" rel="noopener noreferrer" class="catalog-ai__hub">{{ t('catalogAI.onHub') }}</a>
        </li>
      </ul>
    </fieldset>

    <fieldset v-if="selected && form" class="catalog-ai__block">
      <legend>{{ t('catalogAI.dataTitle') }}</legend>
      <template v-if="form.input.kind === 'image' || form.input.kind === 'audio'">
        <label class="catalog-ai__drop" :class="{ 'catalog-ai__drop--ready': files.length }">
          <input type="file" multiple :accept="form.input.kind === 'image' ? IMAGE_ACCEPT : AUDIO_ACCEPT" @change="onFiles">
          <span><strong>{{ files.length ? t('catalogAI.filesReady', { count: files.length }) : t(`catalogAI.drop.${form.input.kind}`) }}</strong><small>{{ files.length ? filesSize : t('catalogAI.dropHint') }}</small></span>
        </label>
      </template>
      <template v-else>
        <label class="catalog-ai__drop" :class="{ 'catalog-ai__drop--ready': table }">
          <input type="file" :accept="TABLE_ACCEPT" @change="onTable">
          <span><strong>{{ tableName || t('catalogAI.drop.table') }}</strong><small>{{ table ? t('catalogAI.rows', { count: table.rows.length }) : t(form.input.kind === 'fields' ? 'catalogAI.dropFieldsHint' : 'catalogAI.dropTextHint') }}</small></span>
        </label>
        <template v-if="table">
          <div v-if="form.input.kind === 'text'" class="catalog-ai__columns">
            <label class="field"><span>{{ t('catalogAI.column') }}</span><select v-model.number="columns.text" class="select"><option v-for="(name, index) in table.columns" :key="index" :value="index">{{ name }}</option></select></label>
          </div>
          <div v-else class="catalog-ai__columns">
            <label v-for="field in form.input.fields" :key="field" class="field"><span>{{ t(`catalogAI.fields.${field}`) }}</span><select v-model.number="columns[field]" class="select"><option v-for="(name, index) in table.columns" :key="index" :value="index">{{ name }}</option></select></label>
          </div>
        </template>
      </template>
      <UiNotice v-if="dataError" tone="danger">{{ dataError }}</UiNotice>
      <div v-if="previews.length" class="catalog-ai__preview"><span class="eyebrow">{{ t('catalogAI.preview') }}</span><ol><li v-for="(item, index) in previews" :key="index">{{ item }}</li></ol></div>

      <div v-if="form.parameters.length" class="catalog-ai__parameters">
        <label v-for="parameter in form.parameters" :key="parameter.key" class="field">
          <span>{{ t(`catalogAI.parameters.${parameter.key}.label`) }}</span>
          <textarea v-if="parameter.type === 'labels'" v-model="values[parameter.key]" class="textarea" rows="2" :placeholder="t(`catalogAI.parameters.${parameter.key}.placeholder`)"></textarea>
          <select v-else-if="parameter.type === 'choice'" v-model="values[parameter.key]" class="select"><option v-for="choice in parameter.choices" :key="choice" :value="choice">{{ choice }}</option></select>
          <input v-else-if="parameter.type === 'text'" v-model.trim="values[parameter.key]" class="input" maxlength="20" :placeholder="t(`catalogAI.parameters.${parameter.key}.placeholder`)">
          <input v-else v-model.number="values[parameter.key]" class="input" type="number" :min="parameter.min" :max="parameter.max" :step="parameter.type === 'int' ? 1 : 0.05">
          <small>{{ t(`catalogAI.parameters.${parameter.key}.hint`) }}</small>
        </label>
      </div>
    </fieldset>

    <section v-if="selected && quote" class="catalog-ai__quote" :class="quote.warm ? 'is-warm' : 'is-cold'" aria-live="polite">
      <div>
        <UiStatusBadge :tone="quote.warm ? 'success' : 'warning'" :label="quote.warm ? t('catalogAI.warm') : t('catalogAI.cold')" />
        <p>{{ quote.warm ? t('catalogAI.warmText', { count: quote.warmWorkers }) : t('catalogAI.coldText', { count: quote.workersNeeded - Math.min(quote.warmWorkers, quote.workersNeeded), size: quote.installGigabytes.toFixed(1) }) }}</p>
        <small>{{ t(`catalogAI.verification.${quote.verification}`) }}</small>
      </div>
      <dl>
        <dt>{{ t('catalogAI.compute') }}</dt><dd>{{ credits(quote.computeCredits) }}</dd>
        <dt>{{ t('catalogAI.verify') }}</dt><dd>{{ credits(quote.verifyCredits) }}</dd>
        <dt>{{ t('catalogAI.install') }}</dt><dd>{{ credits(quote.installCredits) }}</dd>
        <dt class="total">{{ t('catalogAI.total') }}</dt><dd class="total">{{ credits(quote.totalCredits) }}</dd>
      </dl>
      <small class="catalog-ai__estimate">{{ t('catalogAI.estimate') }}<template v-if="!networkKnown"> {{ t('catalogAI.networkUnknown') }}</template></small>
    </section>

    <label v-if="selected" class="catalog-ai__consent">
      <input v-model="consent" type="checkbox">
      <span><strong>{{ t('catalogAI.consent') }}</strong><small>{{ t('catalogAI.consentHint') }}</small></span>
    </label>
  </div>
</template>

<script setup lang="ts">
// Step 1 of a catalogue job: the task (as on the Hub's page, only those the
// network runs can be picked), an admitted model, the data (read here, in
// the browser), the task's parameters, the quote (warm or cold model) and
// the consent. The parent gets the workload `ai/hf/<task>/<key>` and the
// request, or why it cannot be sent yet.
import { guessTextColumn, readItemTable, type ItemTable } from '~/utils/batchAI';
import { AUDIO_ACCEPT, CATEGORIES, IMAGE_ACCEPT, TABLE_ACCEPT, TASK_FORMS, buildParameters, buildSiteRequest, fieldItem, fileItem, hfWorkloadId, modelSize, hfRequestFile, hfRequestProblem, type CatalogAIState, type CatalogModel, type CatalogTask, type CatalogTasks, type ParameterValues, type Quote } from '~/utils/hfCatalog';

const emit = defineEmits<{ update: [state: CatalogAIState] }>();
const { t, formatBytes } = useI18n();
const { loadTasks, loadModels, loadQuote } = useCatalog();

const tasksData = ref<CatalogTasks | null>(null);
const loadError = ref('');
const task = ref('');
const search = ref('');
const models = ref<CatalogModel[]>([]);
const modelsLoading = ref(false);
const selected = ref<CatalogModel | null>(null);
const table = ref<ItemTable | null>(null);
const tableName = ref('');
const columns = reactive<Record<string, number>>({ text: 0 });
const files = ref<File[]>([]);
const dataError = ref('');
const values = reactive<ParameterValues>({});
const consent = ref(false);
const quote = ref<Quote | null>(null);
const networkKnown = ref(true);

const form = computed(() => (task.value ? TASK_FORMS[task.value] : undefined));
const groups = computed(() => CATEGORIES.map((category) => ({ category, tasks: (tasksData.value?.tasks || []).filter((item: CatalogTask) => item.category === category) })).filter((group) => group.tasks.length));
const filesSize = computed(() => formatBytes(files.value.reduce((total, file) => total + file.size, 0)));

/** The items of a table, or the key of a problem. */
const tableItems = computed<{ items: unknown[]; problem: string }>(() => {
  if (!table.value || !form.value) return { items: [], problem: 'noItems' };
  const input = form.value.input;
  if (input.kind === 'text') {
    const items = table.value.rows.map((row) => (row[columns.text] ?? '').trim()).filter(Boolean);
    return { items, problem: '' };
  }
  if (input.kind !== 'fields') return { items: [], problem: 'noItems' };
  const items: unknown[] = [];
  for (const row of table.value.rows) {
    const item = fieldItem(input.fields, input.fields.map((field) => row[columns[field] ?? 0] ?? ''));
    if (typeof item === 'string') return { items: [], problem: item.startsWith('missing:') ? 'missingField' : 'table' };
    items.push(item);
  }
  return { items, problem: '' };
});
const itemCount = computed(() => (form.value?.input.kind === 'image' || form.value?.input.kind === 'audio' ? files.value.length : tableItems.value.items.length));
const previews = computed(() => (form.value?.input.kind === 'image' || form.value?.input.kind === 'audio')
  ? files.value.slice(0, 3).map((file) => file.name)
  : tableItems.value.items.slice(0, 3).map((item) => (typeof item === 'string' ? item : Object.values(item as Record<string, unknown>).map((value) => (Array.isArray(value) ? value.join(' | ') : typeof value === 'object' ? JSON.stringify(value) : String(value))).join(' — '))));
const parameters = computed(() => buildParameters(task.value, values));
const problem = computed(() => {
  if (!task.value) return t('catalogAI.problems.noTask');
  if (!selected.value) return t('catalogAI.problems.noModel');
  if (dataError.value) return dataError.value;
  if (!itemCount.value) return t('catalogAI.problems.noItems');
  if (tableItems.value.problem && form.value?.input.kind === 'fields') return t(`catalogAI.problems.${tableItems.value.problem}`);
  if (form.value?.input.kind === 'text') {
    const textProblem = hfRequestProblem(tableItems.value.items);
    if (textProblem) return t(`catalogAI.problems.${textProblem}`);
  }
  if (files.value.some((file) => file.size > 6 * 1024 * 1024)) return t('catalogAI.problems.itemTooLarge');
  if (files.value.reduce((total, file) => total + file.size, 0) > 40 * 1024 * 1024) return t('catalogAI.problems.requestTooLarge');
  if (parameters.value.problem) return t(`catalogAI.problems.${parameters.value.problem}`);
  return '';
});

async function build(): Promise<File | null> {
  if (problem.value || !selected.value) return null;
  const items = form.value?.input.kind === 'image' || form.value?.input.kind === 'audio'
    ? await Promise.all(files.value.map((file) => fileItem(file)))
    : tableItems.value.items;
  const source = files.value.length ? t('catalogAI.filesReady', { count: files.value.length }) : tableName.value;
  return hfRequestFile(buildSiteRequest(task.value, items, parameters.value.parameters, source));
}

watch([problem, consent, itemCount, selected, quote], () => {
  emit('update', {
    workload: selected.value ? hfWorkloadId(task.value, selected.value.key) : '',
    build,
    problem: problem.value,
    itemCount: itemCount.value,
    task: task.value,
    modelName: selected.value?.repository || '',
    consent: consent.value,
    quote: quote.value,
  });
}, { immediate: true });

onMounted(async () => {
  try {
    tasksData.value = await loadTasks();
  } catch {
    loadError.value = t('catalogAI.loadFailed');
  }
});

async function refreshModels() {
  if (!task.value) return;
  modelsLoading.value = true;
  try {
    models.value = (await loadModels(task.value, search.value)).models;
  } catch {
    models.value = [];
    loadError.value = t('catalogAI.loadFailed');
  } finally {
    modelsLoading.value = false;
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined;
watch(search, () => { clearTimeout(searchTimer); searchTimer = setTimeout(refreshModels, 300); });

let quoteTimer: ReturnType<typeof setTimeout> | undefined;
watch([selected, itemCount], () => {
  clearTimeout(quoteTimer);
  quote.value = null;
  const model = selected.value;
  if (!model) return;
  quoteTimer = setTimeout(async () => {
    try {
      const answer = await loadQuote(model.key, itemCount.value || 1);
      if (selected.value?.key === model.key) { quote.value = answer.quote; networkKnown.value = answer.networkKnown; }
    } catch {
      quote.value = null;
    }
  }, 250);
});

function selectTask(id: string) {
  if (task.value === id) return;
  task.value = id;
  selected.value = null;
  search.value = '';
  files.value = [];
  dataError.value = '';
  for (const key of Object.keys(values)) delete values[key];
  for (const parameter of TASK_FORMS[id]?.parameters || []) {
    if ('default' in parameter) values[parameter.key] = parameter.default;
    else values[parameter.key] = '';
  }
  void refreshModels();
}

async function onTable(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  dataError.value = '';
  table.value = null;
  if (!file) return;
  tableName.value = file.name;
  if (file.size > 56 * 1024 * 1024) { dataError.value = t('catalogAI.problems.requestTooLarge'); return; }
  try {
    table.value = readItemTable(file.name, await file.text());
    columns.text = guessTextColumn(table.value);
    const fields = form.value?.input.kind === 'fields' ? form.value.input.fields : [];
    fields.forEach((field, index) => {
      const named = table.value!.columns.findIndex((name) => name.trim().toLowerCase() === field);
      columns[field] = named >= 0 ? named : Math.min(index, table.value!.columns.length - 1);
    });
  } catch (failure) {
    dataError.value = failure instanceof Error ? failure.message : String(failure);
  }
}

function onFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  files.value = Array.from(input.files || []).slice(0, 2_000);
  input.value = '';
  dataError.value = '';
}

const credits = (value: number) => t('catalogAI.credits', { count: value.toLocaleString(undefined, { maximumFractionDigits: 2 }) });
</script>

<style scoped>
.catalog-ai{display:grid;gap:1.1rem}
.catalog-ai__block{display:grid;gap:.7rem;margin:0;padding:0;border:0}.catalog-ai__block legend{margin-bottom:.5rem;color:var(--ink-900);font-size:.95rem;font-weight:750}
.catalog-ai__category{display:grid;gap:.4rem}.catalog-ai__tasks{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.4rem}
.catalog-ai__tasks button,.catalog-ai__models button{display:grid;gap:.15rem;padding:.6rem .7rem;border:1px solid var(--border);border-radius:var(--radius-md);background:white;color:var(--ink-700);font:inherit;text-align:left;cursor:pointer}
.catalog-ai__tasks button:hover:not(:disabled),.catalog-ai__models button:hover{border-color:var(--mint-500)}.catalog-ai__tasks button.active,.catalog-ai__models button.active{border-color:var(--mint-600);background:var(--mint-100);color:var(--mint-700)}
.catalog-ai__tasks button:disabled{opacity:.55;cursor:not-allowed;background:var(--surface-soft)}.catalog-ai__tasks strong{color:var(--ink-950);font-size:.86rem}.catalog-ai__tasks small{color:var(--ink-500);font-size:.78rem}
.catalog-ai__models{display:grid;gap:.4rem;max-height:340px;margin:0;padding:0;overflow:auto;list-style:none}.catalog-ai__models li{display:grid;grid-template-columns:1fr auto;align-items:center;gap:.5rem}
.catalog-ai__model-name{overflow-wrap:anywhere;color:var(--ink-950);font-family:var(--font-mono);font-size:.86rem;font-weight:650}.catalog-ai__model-meta{color:var(--ink-500);font-size:.8rem}
.catalog-ai__hub{color:var(--mint-700);font-size:.82rem;font-weight:700;text-decoration:underline;text-underline-offset:2px;white-space:nowrap}.catalog-ai__empty{margin:0;color:var(--ink-500);font-size:.88rem}
.catalog-ai__drop{position:relative;display:grid;min-height:76px;align-items:center;padding:1rem;border:1px dashed var(--border-strong);border-radius:var(--radius-md);background:rgba(244,245,241,.45);cursor:pointer}.catalog-ai__drop:hover,.catalog-ai__drop--ready{border-color:var(--mint-500);background:var(--mint-100)}.catalog-ai__drop input{position:absolute;width:1px;height:1px;opacity:0}.catalog-ai__drop strong,.catalog-ai__drop small{display:block;overflow-wrap:anywhere}.catalog-ai__drop small{margin-top:.25rem;color:var(--ink-500);font-size:.85rem}
.catalog-ai__columns,.catalog-ai__parameters{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.7rem}.field small{color:var(--ink-500);font-size:.82rem;line-height:1.4}
.catalog-ai__preview{padding:.7rem .85rem;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-soft)}.catalog-ai__preview ol{display:grid;gap:.3rem;margin:.4rem 0 0;padding-left:1.1rem;color:var(--ink-700);font-size:.86rem}.catalog-ai__preview li{overflow:hidden;overflow-wrap:anywhere;text-overflow:ellipsis;white-space:nowrap}
.catalog-ai__quote{display:grid;grid-template-columns:1fr auto;gap:.6rem 1.2rem;padding:1rem;border:1px solid var(--border);border-radius:var(--radius-md)}.catalog-ai__quote.is-warm{border-color:rgba(18,191,174,.3);background:var(--mint-100)}.catalog-ai__quote.is-cold{border-color:rgba(217,119,6,.3);background:#fff8eb}
.catalog-ai__quote p{margin:.45rem 0 .2rem;color:var(--ink-800);font-size:.9rem}.catalog-ai__quote small{color:var(--ink-600);font-size:.82rem}.catalog-ai__quote dl{display:grid;grid-template-columns:auto auto;gap:.2rem .9rem;margin:0;font-size:.86rem}.catalog-ai__quote dt{color:var(--ink-600)}.catalog-ai__quote dd{margin:0;text-align:right;font-family:var(--font-mono)}.catalog-ai__quote .total{color:var(--ink-950);font-weight:800}.catalog-ai__estimate{grid-column:1/-1}
.catalog-ai__consent{display:grid;grid-template-columns:auto 1fr;gap:.7rem;padding:.85rem 1rem;border:1px solid rgba(217,119,6,.25);border-radius:var(--radius-md);background:#fff8eb;cursor:pointer}.catalog-ai__consent input{margin-top:.15rem;accent-color:var(--mint-600)}.catalog-ai__consent strong,.catalog-ai__consent small{display:block}.catalog-ai__consent strong{font-size:.89rem}.catalog-ai__consent small{margin-top:.25rem;color:var(--ink-600);font-size:.86rem;line-height:1.45}
@media(max-width:600px){.catalog-ai__quote{grid-template-columns:1fr}.catalog-ai__models li{grid-template-columns:1fr}}
</style>
