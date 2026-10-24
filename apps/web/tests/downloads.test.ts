import { describe, expect, it } from 'vitest';
import { resolveNodeDownloadUrl } from '../utils/downloads';

describe('resolveNodeDownloadUrl', () => {
  it('falls back to the published artifact when a legacy page route is configured', () => {
    expect(resolveNodeDownloadUrl('/service/downloads/windows-dev', '/downloads/silicium-node-windows-dev.exe')).toBe('/downloads/silicium-node-windows-dev.exe');
  });

  it('keeps an explicit direct or absolute artifact URL', () => {
    expect(resolveNodeDownloadUrl('/downloads/custom-node.exe', '/downloads/default.exe')).toBe('/downloads/custom-node.exe');
    expect(resolveNodeDownloadUrl('https://cdn.example.test/node.exe', '/downloads/default.exe')).toBe('https://cdn.example.test/node.exe');
  });
});
