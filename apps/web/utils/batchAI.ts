// "Traitement par IA": one instruction applied by the network to every item
// of a list (the rows of a spreadsheet column, the lines of a text file…)
// with a pinned language model. The file is read here, in the browser: the
// user picks the column, sees the first items, and the site sends a
// request `silicium-llm-request/1` (checked again by the BackEnd and the
// node, with the same limits).
import { translate } from './i18n';

/** Workload of a batch AI job (BackEnd `silicium.BatchAIWorkload`). */
export const BATCH_AI_WORKLOAD = 'ai/llm/qwen2.5-1.5b-instruct';
export const REQUEST_FORMAT = 'silicium-llm-request/1';

/** File picker filter: the formats read here. */
export const BATCH_AI_ACCEPT = '.csv,.tsv,.txt,.md,.jsonl,.ndjson,.json';

/** Limits of the node (crate `silicium-llm`, module `request`). */
export const BATCH_AI_LIMITS = {
  fileBytes: 16 * 1024 * 1024,
  items: 20_000,
  itemChars: 6_000,
  instructionChars: 2_000,
  minLabels: 2,
  maxLabels: 50,
  labelChars: 80,
  maxFields: 20,
  fieldChars: 40,
} as const;

export type BatchTask = 'summarize' | 'translate' | 'classify' | 'extract' | 'free';
export const BATCH_TASKS: readonly BatchTask[] = ['summarize', 'translate', 'classify', 'extract', 'free'];

/** What an answer is, for each kind of task, and how long it may be. */
export const TASK_OUTPUT: Record<BatchTask, { kind: 'text' | 'label' | 'fields'; maxTokens: number }> = {
  summarize: { kind: 'text', maxTokens: 192 },
  translate: { kind: 'text', maxTokens: 768 },
  classify: { kind: 'label', maxTokens: 32 },
  extract: { kind: 'fields', maxTokens: 256 },
  free: { kind: 'text', maxTokens: 512 },
};

/** A file read as a table: column names and rows of cells. */
export interface ItemTable {
  columns: string[];
  rows: string[][];
}

/** How a plain text file is cut into items. */
export type TextSplit = 'lines' | 'paragraphs';

const extensionOf = (name: string): string => {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
};

/** True for a file read as plain text (lines or paragraphs). */
export const isPlainText = (name: string): boolean => ['txt', 'md'].includes(extensionOf(name));

/**
 * The table of a file: CSV / TSV (header row, separator detected), JSON
 * Lines or JSON (strings or objects), plain text (one item per line or per
 * paragraph). Throws an Error with a message for the user.
 */
export function readItemTable(name: string, text: string, split: TextSplit = 'lines'): ItemTable {
  const content = text.replace(/^﻿/, '');
  const extension = extensionOf(name);
  if (['csv', 'tsv'].includes(extension)) return readDelimited(content, extension === 'tsv' ? '\t' : detectDelimiter(content));
  if (['jsonl', 'ndjson'].includes(extension)) {
    const values = content.split(/\r?\n/).filter((line) => line.trim()).map((line, index) => {
      try { return JSON.parse(line) as unknown; } catch { throw new Error(translate('batchAI.file.badLine', { line: index + 1 })); }
    });
    return tableOfValues(values);
  }
  if (extension === 'json') {
    let value: unknown;
    try { value = JSON.parse(content); } catch { throw new Error(translate('batchAI.file.badJson')); }
    if (!Array.isArray(value)) throw new Error(translate('batchAI.file.badJson'));
    return tableOfValues(value);
  }
  if (isPlainText(name)) {
    const pieces = split === 'paragraphs' ? content.split(/\r?\n\s*\r?\n/) : content.split(/\r?\n/);
    return { columns: [translate('batchAI.file.textColumn')], rows: pieces.map((piece) => [piece.trim()]).filter((row) => row[0]) };
  }
  throw new Error(translate('batchAI.file.unsupported', { name }));
}

/** `,`, `;` or tab: the most frequent outside quotes on the first line. */
export function detectDelimiter(text: string): string {
  const firstLine = text.split(/\r?\n/, 1)[0] || '';
  let quoted = false;
  const counts: Record<string, number> = { ',': 0, ';': 0, '\t': 0 };
  for (const char of firstLine) {
    if (char === '"') quoted = !quoted;
    else if (!quoted && char in counts) counts[char]! += 1;
  }
  const [best, count] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]!;
  return count > 0 ? best : ',';
}

/** RFC 4180: quoted cells may hold separators, quotes (doubled) and line breaks. */
export function readDelimited(text: string, delimiter: string): ItemTable {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]!;
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') { cell += '"'; index += 1; }
      else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"' && !cell) quoted = true;
    else if (char === delimiter) { row.push(cell); cell = ''; }
    else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[index + 1] === '\n') index += 1;
      row.push(cell); cell = '';
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
    } else cell += char;
  }
  row.push(cell);
  if (row.some((value) => value.trim())) rows.push(row);
  const header = rows.shift() || [];
  const width = Math.max(header.length, ...rows.map((line) => line.length));
  const columns = Array.from({ length: width }, (_, index) => header[index]?.trim() || translate('batchAI.file.column', { index: index + 1 }));
  return { columns, rows: rows.map((line) => Array.from({ length: width }, (_, index) => line[index] ?? '')) };
}

function tableOfValues(values: unknown[]): ItemTable {
  if (values.every((value) => typeof value === 'string' || typeof value === 'number')) {
    return { columns: [translate('batchAI.file.textColumn')], rows: values.map((value) => [String(value)]) };
  }
  const columns: string[] = [];
  for (const value of values) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const key of Object.keys(value)) if (!columns.includes(key)) columns.push(key);
    }
  }
  if (!columns.length) throw new Error(translate('batchAI.file.badJson'));
  const cell = (value: unknown): string => (value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value));
  return {
    columns,
    rows: values.map((value) => columns.map((column) => (value && typeof value === 'object' ? cell((value as Record<string, unknown>)[column]) : ''))),
  };
}

/** The column that most likely holds the texts: the longest on average. */
export function guessTextColumn(table: ItemTable): number {
  let best = 0;
  let bestLength = -1;
  table.columns.forEach((_, index) => {
    const sample = table.rows.slice(0, 50);
    const length = sample.reduce((total, row) => total + (row[index]?.length || 0), 0) / Math.max(1, sample.length);
    if (length > bestLength) { best = index; bestLength = length; }
  });
  return best;
}

/** The non-empty cells of `column`, trimmed, and how many were empty. */
export function itemsOf(table: ItemTable, column: number): { items: string[]; skipped: number } {
  const items: string[] = [];
  let skipped = 0;
  for (const row of table.rows) {
    const value = (row[column] || '').trim();
    if (value) items.push(value); else skipped += 1;
  }
  return { items, skipped };
}

/** "positif, négatif ; neutre" → ["positif", "négatif", "neutre"]. */
export const splitNames = (text: string): string[] =>
  text.split(/[,;\n]/).map((name) => name.trim().replace(/\s+/g, ' ')).filter(Boolean);

export interface BatchRequestInput {
  task: BatchTask;
  instruction: string;
  /** Categories (classify) or fields (extract), comma separated. */
  names: string;
  items: string[];
  source: { name: string; column: string };
}

/** The request sent to the BackEnd. */
export function buildRequest(input: BatchRequestInput): Record<string, unknown> {
  const output = TASK_OUTPUT[input.task];
  const names = splitNames(input.names);
  return {
    format: REQUEST_FORMAT,
    task: input.task,
    instruction: input.instruction.trim(),
    output: output.kind === 'label' ? { kind: 'label', labels: names } : output.kind === 'fields' ? { kind: 'fields', fields: names } : { kind: 'text' },
    max_tokens: output.maxTokens,
    source: { name: input.source.name.slice(0, 200), column: input.source.column.slice(0, 200) },
    items: input.items,
  };
}

/** Why the request cannot be sent, in the user's words; '' when it can. */
export function requestProblem(input: BatchRequestInput): string {
  const limits = BATCH_AI_LIMITS;
  const kind = TASK_OUTPUT[input.task].kind;
  if (!input.items.length) return translate('batchAI.problems.noItems');
  if (input.items.length > limits.items) return translate('batchAI.problems.tooManyItems', { max: limits.items });
  const long = input.items.findIndex((item) => [...item].length > limits.itemChars);
  if (long >= 0) return translate('batchAI.problems.itemTooLong', { index: long + 1, max: limits.itemChars });
  // Only a free task may go without instruction: each item is then a prompt.
  if (!input.instruction.trim() && input.task !== 'free') return translate('batchAI.problems.instruction');
  if ([...input.instruction.trim()].length > limits.instructionChars) return translate('batchAI.problems.instructionLong', { max: limits.instructionChars });
  const names = splitNames(input.names);
  const lower = names.map((name) => name.toLowerCase());
  if (kind === 'label') {
    if (names.length < limits.minLabels || names.length > limits.maxLabels) return translate('batchAI.problems.labels', { min: limits.minLabels, max: limits.maxLabels });
    if (names.some((name) => name.length > limits.labelChars)) return translate('batchAI.problems.nameLong', { max: limits.labelChars });
  }
  if (kind === 'fields') {
    if (!names.length || names.length > limits.maxFields) return translate('batchAI.problems.fields', { max: limits.maxFields });
    if (names.some((name) => name.length > limits.fieldChars)) return translate('batchAI.problems.nameLong', { max: limits.fieldChars });
  }
  const twice = lower.find((name, index) => lower.indexOf(name) !== index);
  if (twice) return translate('batchAI.problems.twice', { name: names[lower.indexOf(twice)]! });
  return '';
}

/** What the form of step 1 tells the job form; `build` makes the request
 * file (only when sent: a list can weigh megabytes). */
export interface BatchAIState { build: () => File | null; problem: string; itemCount: number; task: BatchTask; consent: boolean }

/** The request as the file sent in the job form. */
export const requestFile = (request: Record<string, unknown>): File =>
  new File([JSON.stringify(request)], 'request.json', { type: 'application/json' });

/** True for a batch AI job. */
export const isBatchAIWorkload = (workload: unknown): boolean => String(workload || '').trim() === BATCH_AI_WORKLOAD;

/** An answer as the API sends it: a text, a label, `{field: text}` or null. */
export type BatchOutput = string | Record<string, string> | null;

/** One answered item (`GET /jobs/{id}/answers`). */
export interface BatchAnswer {
  id: number;
  input: string;
  output: BatchOutput;
}

export interface BatchAnswersPage {
  total: number;
  available: number;
  complete: boolean;
  offset: number;
  items: BatchAnswer[];
}

/** The request of a batch AI job, as the job page shows it. */
export interface BatchAIRequestSummary {
  task: BatchTask;
  instruction: string;
  output: { kind: 'text' | 'label' | 'fields'; labels?: string[]; fields?: string[] };
  maxTokens: number;
  itemCount: number;
  source: { name?: string; column?: string };
}

export interface BatchAIDashboard {
  request: BatchAIRequestSummary | null;
  result?: { model?: { id?: string; licence?: string }; itemCount?: number; answered?: number };
}

/** An answer in one line of text (fields as "name : value · …"). */
export function outputText(output: BatchOutput): string {
  if (output == null) return '';
  if (typeof output === 'string') return output;
  return Object.entries(output).filter(([, value]) => value).map(([key, value]) => `${key} : ${value}`).join(' · ');
}
