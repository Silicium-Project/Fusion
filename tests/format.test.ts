import { describe, expect, it } from 'vitest';
import { compactIdentifier, peerAvailability, peerRoles, statusLabel, statusTone } from '../utils/format';

describe('display contracts', () => {
  it('keeps status wording and tones consistent across pages', () => {
    expect(statusLabel('running')).toBe('En cours');
    expect(statusLabel('outdated-build')).toBe('Build obsolète');
    expect(statusTone('completed')).toBe('success');
    expect(statusTone('failed')).toBe('danger');
    expect(statusTone('queued')).toBe('warning');
    expect(statusLabel('queued_verify')).toBe('Validation en attente');
    expect(statusTone('reassembled')).toBe('success');
  });

  it('compacts technical identifiers without hiding short values', () => {
    expect(compactIdentifier('short')).toBe('short');
    expect(compactIdentifier('abcdefghijklmnopqrstuvwxyz', 5, 4)).toBe('abcde…wxyz');
  });

  it('keeps peer roles and availability tied to announced data', () => {
    expect(peerRoles({ node_id: 'worker', node_roles: ['resource', 'verify'] })).toEqual(['resource', 'verify']);
    expect(peerRoles({ node_id: 'orchestrator-1' })).toEqual([]);
    expect(peerAvailability({ node_id: 'worker', online: true })).toBe('online');
    expect(peerAvailability({ node_id: 'worker', online: false })).toBe('offline');
    expect(peerAvailability({ node_id: 'worker' })).toBe('unknown');
  });
});
