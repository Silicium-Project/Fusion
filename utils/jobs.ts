import { translate } from './i18n';

export const compactJobError = (message: string, limit = 16_000): string => {
  const normalized = String(message || '').replace(/\r\n?/g, '\n').trim();
  if (!normalized) return translate('errors.workerNoDetail');
  if (normalized.length <= limit) return normalized;
  const marker = `\n\n${translate('errors.truncated')}`;
  return `${normalized.slice(0, Math.max(0, limit - marker.length)).trimEnd()}${marker}`;
};

/** True for an HTML page (the error page of a proxy), never shown as text. */
const isHtml = (text: string): boolean => /^\s*<(!doctype|html|head|body)\b/i.test(text) || /<\/html>/i.test(text);

/** A message for an HTTP status when the response says nothing readable. */
const statusMessage = (status: unknown): string | undefined => {
  const code = Number(status);
  if (code === 413) return translate('errors.tooLarge');
  if (code >= 500 && code < 600) return translate('errors.serverError');
  return undefined;
};

/**
 * The message to show for a failed request or job: the API's `message`
 * (in the user's language) before an `error` code, then a message for the
 * HTTP status, then the fallback. An HTML error page (from the proxy in
 * front of the API) is never shown.
 */
export const extractJobError = (failure: unknown, fallback = translate('errors.submitFailed')): string => {
  const candidate = failure as {
    data?: unknown;
    message?: unknown;
    status?: unknown;
    statusCode?: unknown;
    response?: { _data?: unknown; data?: unknown; status?: unknown };
  };
  const payloads = [candidate?.data, candidate?.response?._data, candidate?.response?.data, candidate];
  for (const payload of payloads) {
    if (typeof payload === 'string' && payload.trim()) {
      if (isHtml(payload)) continue;
      return payload.trim();
    }
    if (!payload || typeof payload !== 'object') continue;
    const values = payload as Record<string, unknown>;
    const message = ['failureDetail', 'failure_detail', 'errorMessage', 'message', 'error']
      .map((key) => values[key]).find((value): value is string => typeof value === 'string' && Boolean(value.trim()))?.trim() || '';
    const traceback = ['traceback', 'error_traceback']
      .map((key) => values[key]).find((value): value is string => typeof value === 'string' && Boolean(value.trim()))?.trim() || '';
    if (message || traceback) {
      if (!traceback || message.includes(traceback)) return message || traceback;
      return message ? `${message}\n\n${traceback}` : traceback;
    }
  }
  const byStatus = statusMessage(candidate?.statusCode ?? candidate?.status ?? candidate?.response?.status);
  if (byStatus) return byStatus;
  return failure instanceof Error && failure.message && !isHtml(failure.message) ? failure.message : fallback;
};

/**
 * The number of parts of a job: the first known count among `counts`, 0
 * while it is not known yet (a document search is split by the network
 * once the documents are read).
 */
export const jobPartCount = (...counts: unknown[]): number => {
  for (const count of counts) {
    const value = Math.trunc(Number(count));
    if (Number.isFinite(value) && value > 0) return value;
  }
  return 0;
};

export const isJobCancellable = (status: string): boolean =>
  ['queued', 'running', 'cancelling'].includes(status);

export type FragmentVisualState = 'planned' | 'computing' | 'validating' | 'done' | 'failed';

export const fragmentVisualState = (status: unknown): FragmentVisualState => {
  const normalized = String(status || '').trim().toLowerCase();
  if (['failed', 'error', 'cancelled', 'canceled', 'expired'].some(value => normalized.includes(value))) return 'failed';
  if (['reassembled', 'verified', 'completed', 'finished', 'resolved'].includes(normalized)) return 'done';
  if (normalized.includes('verify') || normalized.includes('validat') || normalized === 'computed') return 'validating';
  if (normalized.includes('compute') || ['claimed', 'dispatched', 'running', 'processing', 'in_progress'].includes(normalized)) return 'computing';
  return 'planned';
};

export const fragmentStateLabel = (status: unknown): string => translate(`fragmentState.${fragmentVisualState(status)}`);

export const shouldRefreshJob = (status: string, resultReady: boolean): boolean =>
  isJobCancellable(status) || (status === 'completed' && !resultReady);

/** How long after completion the page waits for the blockchain anchor. */
const CHAIN_ANCHOR_WAIT_MS = 5 * 60_000;

/**
 * A completed job whose trace is still being written on the blockchain:
 * keep refreshing for a few minutes, then stop (the anchor may have failed
 * on the server side without a trace file).
 */
export const awaitingChainAnchor = (
  dashboard: { job: { status: string; completedAt?: string }; devnet?: { status?: string } },
  now: number = Date.now(),
): boolean => {
  if (dashboard.job.status !== 'completed' || dashboard.devnet?.status !== 'pending') return false;
  const completed = Date.parse(dashboard.job.completedAt || '');
  return Number.isFinite(completed) && now - completed < CHAIN_ANCHOR_WAIT_MS;
};

export const clampJobPage = (page: number, total: number, pageSize: number): number => {
  const lastPage = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  return Math.max(1, Math.min(lastPage, Math.trunc(page) || 1));
};

/** Jobs that render an image (the default workload of older jobs). */
export const isImageWorkload = (workload: unknown): boolean => {
  const normalized = String(workload || '').trim();
  return !normalized || normalized === 'raytracer';
};

/** Workloads whose result is a SHA-256 report (`result/sha256.json`). */
export const isHashWorkload = (workload: unknown): boolean =>
  ['calcul/integrity/sha256', 'calcul/hash/sha256'].includes(String(workload || '').trim());

/** File extension of a downloaded result, from its content type. */
export const resultExtension = (contentType: string): string => {
  const type = contentType.toLowerCase();
  if (type.includes('png')) return 'png';
  if (type.includes('json')) return 'json';
  if (type.includes('portable-pixmap') || type.includes('ppm')) return 'ppm';
  if (type.includes('zip')) return 'zip';
  return 'bin';
};

/** One chunk of a SHA-256 job result. */
export interface HashChunk { index: number; offset: number; length: number; sha256: string }

/** SHA-256 job result written by the Rust node. */
export interface HashReport {
  size_bytes: number;
  chunk_count: number;
  chunk_list_sha256: string;
  input_hash?: string | null;
  chunks: HashChunk[];
}

/** The report when `value` has the shape written by the node, else null. */
export const parseHashReport = (value: unknown): HashReport | null => {
  const report = value as Partial<HashReport> | null;
  if (!report || typeof report !== 'object' || !Array.isArray(report.chunks)) return null;
  if (typeof report.size_bytes !== 'number' || typeof report.chunk_list_sha256 !== 'string') return null;
  return report as HashReport;
};
