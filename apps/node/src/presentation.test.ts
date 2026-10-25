import { describe, expect, it } from 'vitest';
import {
  formatBytes,
  friendlyError,
  shortIdentity,
  taskRoleLabel,
  transportRouteLabel,
} from './presentation';

describe('presentation independent from runtime access', () => {
  it('keeps observed transport and unavailable proof distinguishable', () => {
    expect(transportRouteLabel('direct', 'ice')).toBe('Direct ICE prouve');
    expect(transportRouteLabel('unknown', '')).toBe('Chemin inconnu');
    expect(shortIdentity('')).toBe('identite non annoncee');
  });
  it('formats resources and roles without invoking a daemon', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(taskRoleLabel('verify')).toBe('Verification');
  });
  it('keeps unexpected errors visible', () => {
    expect(friendlyError(new Error('unexpected storage failure'))).toContain(
      'unexpected storage failure',
    );
  });
});
