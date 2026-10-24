export function resolveNodeDownloadUrl(value: unknown, fallback: string): string {
  const configured = typeof value === 'string' ? value.trim() : '';
  return configured && !configured.startsWith('/service/downloads/') ? configured : fallback;
}
