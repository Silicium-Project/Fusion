export const compactJobError = (message: string, limit = 16_000): string => {
  const normalized = String(message || '').replace(/\r\n?/g, '\n').trim();
  if (!normalized) return 'Erreur sans détail fourni par le worker.';
  if (normalized.length <= limit) return normalized;
  const marker = '\n\n[… détail d’erreur tronqué pour l’affichage …]';
  return `${normalized.slice(0, Math.max(0, limit - marker.length)).trimEnd()}${marker}`;
};

export const extractJobError = (failure: unknown, fallback = 'La tâche ne peut pas être soumise pour le moment.'): string => {
  const candidate = failure as {
    data?: unknown;
    message?: unknown;
    response?: { _data?: unknown; data?: unknown };
  };
  const payloads = [candidate?.data, candidate?.response?._data, candidate?.response?.data, candidate];
  for (const payload of payloads) {
    if (typeof payload === 'string' && payload.trim()) return payload.trim();
    if (!payload || typeof payload !== 'object') continue;
    const values = payload as Record<string, unknown>;
    const message = ['failureDetail', 'failure_detail', 'errorMessage', 'error', 'message']
      .map((key) => values[key]).find((value): value is string => typeof value === 'string' && Boolean(value.trim()))?.trim() || '';
    const traceback = ['traceback', 'error_traceback']
      .map((key) => values[key]).find((value): value is string => typeof value === 'string' && Boolean(value.trim()))?.trim() || '';
    if (message || traceback) {
      if (!traceback || message.includes(traceback)) return message || traceback;
      return message ? `${message}\n\n${traceback}` : traceback;
    }
  }
  return failure instanceof Error && failure.message ? failure.message : fallback;
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

export const fragmentStateLabel = (status: unknown): string => ({
  planned: 'En attente',
  computing: 'Calcul en cours',
  validating: 'Validation en cours',
  done: 'Terminé',
  failed: 'En erreur',
})[fragmentVisualState(status)];

export const shouldRefreshJob = (status: string, resultReady: boolean): boolean =>
  isJobCancellable(status) || (status === 'completed' && !resultReady);

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
