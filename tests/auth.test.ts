import { describe, expect, it } from 'vitest';
import { authErrorMessage, tokenExpiry } from '../utils/auth';

const token = (payload: object) => `header.${btoa(JSON.stringify(payload))}.signature`;

describe('login helpers', () => {
  it('uses the token expiry instead of a fixed seven-day cookie', () => {
    expect(tokenExpiry(token({ exp: 1000 }), 999_000)?.getTime()).toBe(1_000_000);
    expect(tokenExpiry(token({ exp: 1000 }), 1_000_000)).toBeUndefined();
  });

  it('ignores malformed, missing and expired tokens', () => {
    for (const value of [undefined, 'broken', token({}), token({ exp: '1000' }), token({ exp: 0 })]) {
      expect(tokenExpiry(value)).toBeUndefined();
    }
  });

  it('displays API errors without exposing technical fallback details', () => {
    expect(authErrorMessage({ data: { message: 'Compte existant.' } })).toBe('Compte existant.');
    expect(authErrorMessage({ status: 401 })).toContain('incorrect');
    expect(authErrorMessage({ statusCode: 409 })).toContain('déjà utilisé');
    expect(authErrorMessage({ data: 'SQL private details', status: 500 })).not.toContain('SQL');
  });
});
