export const clampProgress = (value: number): number =>
  Math.max(0, Math.min(100, Number(value) || 0));

export const formatProgress = (value: number): string =>
  `${clampProgress(value).toFixed(value > 0 && value < 10 ? 1 : 0)}%`;

export const formatMetricPercent = (value: number): string =>
  `${Math.max(0, Number(value) || 0).toFixed(1)}%`;

export const formatElapsed = (milliseconds: number): string => {
  const seconds = Math.max(0, Math.round((Number(milliseconds) || 0) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};

export const taskStatusLabel = (status: string): string => ({
  running: 'en cours',
  dispatched: 'attribuee',
  retrying: 'nouvel essai',
  cancelling: 'annulation',
  cancelled: 'annulee',
  expired: 'expiree',
  failed: 'echec',
}[status] || 'en attente');

export const phaseLabel = (phase: string): string => ({
  fetching_input: 'Recuperation',
  executing: 'Execution',
  rendering: 'Rendu',
  publishing_result: 'Publication',
  finalizing: 'Finalisation',
  cancelling: 'Annulation',
  cancelled: 'Annulee',
  expired: 'Expiree',
  completed: 'Terminee',
  failed: 'Echec',
}[phase] || phase || 'Execution');
