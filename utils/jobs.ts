export const compactJobError = (message: string, limit = 180): string => {
  const line = message.split(/\r?\n/).find((value) => value.trim()) || message;
  return line.length > limit ? `${line.slice(0, Math.max(0, limit - 1))}…` : line;
};

export const isJobCancellable = (status: string): boolean =>
  ['queued', 'running', 'cancelling'].includes(status);

export const clampJobPage = (page: number, total: number, pageSize: number): number => {
  const lastPage = Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, pageSize)));
  return Math.max(1, Math.min(lastPage, Math.trunc(page) || 1));
};
