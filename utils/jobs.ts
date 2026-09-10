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

export const clampJobPage = (page: number, total: number, pageSize: number): number => {
  const lastPage = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  return Math.max(1, Math.min(lastPage, Math.trunc(page) || 1));
};
