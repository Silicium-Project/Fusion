// "Catalogue IA": a task of the Hugging Face Hub applied by the network to
// every item of a list, with a model admitted by the BackEnd's catalogue
// (`GET /catalog/tasks`, `/catalog/models`, `/catalog/models/{key}/quote`).
// The site sends the task, the items and the parameters
// (`silicium-hf-site-request/1`); the BackEnd adds the model's manifest, the
// node checks everything again. Nothing here names a model.

/** Prefix of the catalogue workloads: `ai/hf/<task>/<model key>`. */
export const HF_PREFIX = 'ai/hf/';
/** Value of the job type selector before a task and a model are chosen. */
export const HF_WORKLOAD = 'ai/hf';
export const SITE_REQUEST_FORMAT = 'silicium-hf-site-request/1';

/** Limits of the BackEnd and the node (`internal/aijobs`, `workload/hf`). */
export const HF_LIMITS = {
  items: 20_000,
  itemBytes: 8 * 1024 * 1024,
  requestBytes: 56 * 1024 * 1024,
  textChars: 20_000,
} as const;

export const isHFWorkload = (workload?: string | null): boolean =>
  Boolean(workload && (workload === HF_WORKLOAD || workload.startsWith(HF_PREFIX)));

export const hfWorkloadId = (task: string, key: string): string => `${HF_PREFIX}${task}/${key}`;

/** The task of a catalogue workload, or ''. */
export const hfTaskOf = (workload?: string | null): string =>
  workload?.startsWith(HF_PREFIX) ? workload.slice(HF_PREFIX.length).split('/')[0] || '' : '';

export type HardwareClass = 'A' | 'B' | 'C';
export type Category = 'multimodal' | 'computer-vision' | 'natural-language-processing' | 'audio' | 'tabular' | 'reinforcement-learning' | 'other';
export const CATEGORIES: readonly Category[] = ['multimodal', 'computer-vision', 'natural-language-processing', 'audio', 'tabular', 'reinforcement-learning', 'other'];

export interface CatalogTask {
  id: string;
  label: string;
  category: Category;
  minClass: HardwareClass;
  verification: 'exact' | 'similarity' | 'perceptual' | 'full-recompute';
  metric: string;
  hubSchema: boolean;
  libraries: string[];
  models: number;
  networkReady: boolean;
}

export interface CatalogTasks {
  tasks: CatalogTask[];
  sync: { succeededAt: string | null; finishedAt: string | null; failed: boolean };
}

export interface CatalogModel {
  key: string;
  repository: string;
  revision: string;
  task: string;
  library: string;
  status: string;
  hardwareClass: HardwareClass;
  totalBytes: number;
  parameters: number;
  licence: string;
  downloads: number;
  likes: number;
  hubUrl: string;
}

export interface Quote {
  items: number;
  fragments: number;
  workersNeeded: number;
  warmWorkers: number;
  onlineWorkers: number;
  warm: boolean;
  computeCredits: number;
  verifyCredits: number;
  installCredits: number;
  totalCredits: number;
  installGigabytes: number;
  verification: string;
  estimateOnly: boolean;
}

/** How the items of a task are given. */
export type InputKind =
  | { kind: 'text' }
  | { kind: 'fields'; fields: readonly string[] }
  | { kind: 'image' }
  | { kind: 'audio' };

/** A parameter of a task (the Hub's schema, bounded as the runtime does). */
export type Parameter =
  | { key: string; type: 'int'; default: number; min: number; max: number }
  | { key: string; type: 'number'; default: number; min: number; max: number }
  | { key: string; type: 'labels'; required: true }
  | { key: string; type: 'choice'; default: string; choices: readonly string[] }
  | { key: string; type: 'text'; default: string };

/** What the site asks for each task the network runs (Silicium AI runtime, `tasks.py`). */
export const TASK_FORMS: Record<string, { input: InputKind; parameters: readonly Parameter[] }> = {
  'text-classification': { input: { kind: 'text' }, parameters: [{ key: 'top_k', type: 'int', default: 3, min: 1, max: 50 }] },
  'token-classification': { input: { kind: 'text' }, parameters: [{ key: 'aggregation_strategy', type: 'choice', default: 'simple', choices: ['simple', 'first', 'average', 'max', 'none'] }] },
  'question-answering': { input: { kind: 'fields', fields: ['question', 'context'] }, parameters: [{ key: 'max_answer_len', type: 'int', default: 30, min: 1, max: 200 }] },
  'zero-shot-classification': { input: { kind: 'text' }, parameters: [{ key: 'candidate_labels', type: 'labels', required: true }] },
  translation: { input: { kind: 'text' }, parameters: [{ key: 'max_new_tokens', type: 'int', default: 256, min: 1, max: 512 }, { key: 'src_lang', type: 'text', default: '' }, { key: 'tgt_lang', type: 'text', default: '' }] },
  summarization: { input: { kind: 'text' }, parameters: [{ key: 'max_new_tokens', type: 'int', default: 160, min: 1, max: 512 }] },
  'feature-extraction': { input: { kind: 'text' }, parameters: [] },
  'text-generation': { input: { kind: 'text' }, parameters: [{ key: 'max_new_tokens', type: 'int', default: 128, min: 1, max: 512 }] },
  'fill-mask': { input: { kind: 'text' }, parameters: [{ key: 'top_k', type: 'int', default: 5, min: 1, max: 20 }] },
  'sentence-similarity': { input: { kind: 'fields', fields: ['source_sentence', 'sentences'] }, parameters: [] },
  'text-ranking': { input: { kind: 'fields', fields: ['query', 'texts'] }, parameters: [] },
  'table-question-answering': { input: { kind: 'fields', fields: ['query', 'table'] }, parameters: [] },
  'image-classification': { input: { kind: 'image' }, parameters: [{ key: 'top_k', type: 'int', default: 5, min: 1, max: 50 }] },
  'zero-shot-image-classification': { input: { kind: 'image' }, parameters: [{ key: 'candidate_labels', type: 'labels', required: true }] },
  'object-detection': { input: { kind: 'image' }, parameters: [{ key: 'threshold', type: 'number', default: 0.5, min: 0, max: 1 }] },
  'image-to-text': { input: { kind: 'image' }, parameters: [{ key: 'max_new_tokens', type: 'int', default: 64, min: 1, max: 512 }] },
  'image-feature-extraction': { input: { kind: 'image' }, parameters: [] },
  'automatic-speech-recognition': { input: { kind: 'audio' }, parameters: [{ key: 'language', type: 'text', default: '' }] },
  'audio-classification': { input: { kind: 'audio' }, parameters: [{ key: 'top_k', type: 'int', default: 5, min: 1, max: 50 }] },
};

export const IMAGE_ACCEPT = 'image/png,image/jpeg,image/webp,image/bmp,image/gif';
export const AUDIO_ACCEPT = '.wav,.flac,.ogg,audio/wav,audio/flac,audio/ogg';
export const TABLE_ACCEPT = '.csv,.tsv,.txt,.md,.jsonl,.ndjson,.json';

/** Values of the parameters as typed in the form (labels: one per line or comma). */
export type ParameterValues = Record<string, string | number>;

/** Splits a list of labels typed by the user. */
export const splitLabels = (value: string): string[] =>
  value.split(/[\n,;]/).map((label) => label.trim()).filter(Boolean).filter((label, index, all) => all.indexOf(label) === index);

/**
 * The parameters to send, or the key of the first problem
 * (`catalogAI.problems.*`). Empty text parameters are left out.
 */
export function buildParameters(task: string, values: ParameterValues): { parameters: Record<string, unknown>; problem: string } {
  const parameters: Record<string, unknown> = {};
  for (const parameter of TASK_FORMS[task]?.parameters || []) {
    const raw = values[parameter.key];
    if (parameter.type === 'labels') {
      const labels = splitLabels(String(raw ?? ''));
      if (labels.length < 1 || labels.length > 50 || labels.some((label) => label.length > 80)) return { parameters, problem: 'labels' };
      parameters[parameter.key] = labels;
    } else if (parameter.type === 'int' || parameter.type === 'number') {
      const value = raw === undefined || raw === '' ? parameter.default : Number(raw);
      if (!Number.isFinite(value) || value < parameter.min || value > parameter.max || (parameter.type === 'int' && !Number.isInteger(value))) {
        return { parameters, problem: 'parameter' };
      }
      parameters[parameter.key] = value;
    } else if (parameter.type === 'choice') {
      const value = String(raw ?? parameter.default);
      if (!parameter.choices.includes(value)) return { parameters, problem: 'parameter' };
      parameters[parameter.key] = value;
    } else {
      const value = String(raw ?? parameter.default).trim();
      if (value.length > 20) return { parameters, problem: 'parameter' };
      if (value) parameters[parameter.key] = value;
    }
  }
  return { parameters, problem: '' };
}

/**
 * The items of a `fields` task from a table row: `sentences` and `texts`
 * are split on ` | `, `table` is a JSON object of columns.
 */
export function fieldItem(fields: readonly string[], cells: readonly string[]): Record<string, unknown> | string {
  const item: Record<string, unknown> = {};
  for (const [index, field] of fields.entries()) {
    const cell = (cells[index] ?? '').trim();
    if (!cell) return `missing:${field}`;
    if (field === 'sentences' || field === 'texts') item[field] = cell.split(' | ').map((part) => part.trim()).filter(Boolean);
    else if (field === 'table') {
      try {
        const table = JSON.parse(cell) as unknown;
        if (!table || typeof table !== 'object' || Array.isArray(table)) return 'table';
        item[field] = table;
      } catch {
        return 'table';
      }
    } else item[field] = cell;
  }
  return item;
}

/** A file as the node reads it: `{"$bytes": "<base64>"}`. */
export async function fileItem(file: Blob): Promise<{ $bytes: string }> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  return { $bytes: btoa(binary) };
}

/** Byte length of a value once written as JSON (UTF-8). */
export const jsonBytes = (value: unknown): number => new TextEncoder().encode(JSON.stringify(value)).length;

export interface SiteRequest {
  format: typeof SITE_REQUEST_FORMAT;
  task: string;
  parameters: Record<string, unknown>;
  items: unknown[];
  source: { name?: string };
}

/** The key of the first problem of a request (`catalogAI.problems.*`), or ''. */
export function hfRequestProblem(items: readonly unknown[]): string {
  if (!items.length) return 'noItems';
  if (items.length > HF_LIMITS.items) return 'tooManyItems';
  let total = 0;
  for (const item of items) {
    if (item === null || item === undefined || (typeof item === 'string' && !item.trim())) return 'emptyItem';
    if (typeof item === 'string' && item.length > HF_LIMITS.textChars) return 'itemTooLong';
    const size = jsonBytes(item);
    if (size > HF_LIMITS.itemBytes) return 'itemTooLarge';
    total += size;
  }
  return total > HF_LIMITS.requestBytes ? 'requestTooLarge' : '';
}

export const buildSiteRequest = (task: string, items: unknown[], parameters: Record<string, unknown>, sourceName = ''): SiteRequest => ({
  format: SITE_REQUEST_FORMAT,
  task,
  parameters,
  items,
  source: sourceName ? { name: sourceName.slice(0, 200) } : {},
});

export const hfRequestFile = (request: SiteRequest): File =>
  new File([JSON.stringify(request)], 'request.json', { type: 'application/json' });

/** What step 1 hands to the job form. */
export interface CatalogAIState {
  workload: string;
  /** The request file (images and sounds are read when it is built). */
  build: () => Promise<File | null>;
  problem: string;
  itemCount: number;
  task: string;
  modelName: string;
  consent: boolean;
  quote: Quote | null;
}

/** The answer of a catalogue job as the BackEnd returns it. */
export interface CatalogAnswer {
  id: number;
  output: unknown;
}

export interface CatalogAnswersPage {
  total: number;
  available: number;
  complete: boolean;
  offset: number;
  items: CatalogAnswer[];
}

export interface CatalogDashboard {
  request: null | {
    task: string;
    model: { key: string; repository: string; revision: string; licence: string; hardwareClass: string };
    itemCount: number;
    parameters: Record<string, unknown>;
    source: { name?: string };
    previews: string[];
  };
  result?: { itemCount?: number; model?: { repository?: string } };
}

/** A short text for an output of the Hub's task schemas, for the answers table. */
export function outputSummary(output: unknown): string {
  if (output === null || output === undefined) return '';
  if (typeof output === 'string') return output;
  if (Array.isArray(output)) {
    if (!output.length) return '—';
    if (output.every((value) => typeof value === 'number')) return `[${output.length}] ${output.slice(0, 4).map((value) => (value as number).toFixed(3)).join(', ')}…`;
    const first = output[0] as Record<string, unknown>;
    if (first && typeof first === 'object') {
      if ('box' in first) return output.map((entry) => `${(entry as { label?: string }).label} (${Number((entry as { score?: number }).score ?? 0).toFixed(2)})`).join(', ');
      if ('label' in first || 'token_str' in first) {
        return output.slice(0, 3).map((entry) => {
          const value = entry as { label?: string; token_str?: string; score?: number };
          return `${value.label ?? value.token_str} ${Math.round(Number(value.score ?? 0) * 100)} %`;
        }).join(' · ');
      }
      if ('entity_group' in first || 'entity' in first) {
        return output.map((entry) => {
          const value = entry as { entity_group?: string; entity?: string; word?: string };
          return `${value.word} [${value.entity_group ?? value.entity}]`;
        }).join(', ');
      }
      if ('index' in first) return output.map((entry) => `#${(entry as { index: number }).index + 1}`).join(' > ');
      for (const key of ['generated_text', 'summary_text', 'translation_text', 'answer']) {
        if (key in first) return String(first[key]);
      }
    }
  }
  if (typeof output === 'object') {
    const value = output as Record<string, unknown>;
    if (Array.isArray(value.labels)) return `${value.labels[0]} ${Math.round(Number((value.scores as number[] | undefined)?.[0] ?? 0) * 100)} %`;
    for (const key of ['text', 'answer', 'generated_text']) if (typeof value[key] === 'string') return value[key] as string;
  }
  return JSON.stringify(output);
}

/** Model size for people: "1,1 Go", "350 Mo". */
export function modelSize(bytes: number, locale = 'fr'): string {
  const gigabytes = bytes / 1024 ** 3;
  if (gigabytes >= 1) return `${gigabytes.toLocaleString(locale, { maximumFractionDigits: 1 })} ${locale.startsWith('fr') ? 'Go' : 'GB'}`;
  return `${Math.max(1, Math.round(bytes / 1024 ** 2))} ${locale.startsWith('fr') ? 'Mo' : 'MB'}`;
}
