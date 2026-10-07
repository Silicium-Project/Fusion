import { describe, expect, it } from 'vitest';
import { safeRedirect } from '../utils/auth';
import { emailProblem, jobDescriptionProblem, jobTitleProblem, newPasswordProblem, personNameProblem, usernameProblem } from '../utils/validation';
import { extractJobError } from '../utils/jobs';
import { uniqueDocuments } from '../utils/documents';

describe('user input', () => {
  it('accepts plain email addresses only', () => {
    for (const email of ['ada@example.com', ' Ada.Lovelace+silicium@Example.co.uk ']) expect(emailProblem(email)).toBe('');
    for (const email of ['ada', 'ada@localhost', 'Ada <ada@example.com>', '"a b"@example.com', `${'a'.repeat(65)}@example.com`, 'ada@exa mple.com']) {
      expect(emailProblem(email)).toBe('validation.emailInvalid');
    }
  });

  it('checks usernames, names and passwords like the API', () => {
    expect(usernameProblem('')).toBe('');
    expect(usernameProblem('thom_42')).toBe('');
    for (const username of ['ab', 'a'.repeat(31), 'john doe', 'me@example.com', 'Admin', '...']) expect(usernameProblem(username)).not.toBe('');
    for (const name of ['Zoë', 'Jean-Luc', 'O’Neil', 'José María', '李']) expect(personNameProblem(name)).toBe('');
    for (const name of ['R2D2', '<script>', 'x'.repeat(51), 'Bob​', '---']) expect(personNameProblem(name)).not.toBe('');
    expect(newPasswordProblem('1234567')).toBe('validation.passwordShort');
    expect(newPasswordProblem('é'.repeat(37))).toBe('validation.passwordLong');
    expect(newPasswordProblem('correct horse')).toBe('');
  });

  it('refuses hidden characters and overlong job texts', () => {
    expect(jobTitleProblem('Rendu — version 4')).toBe('');
    expect(jobTitleProblem('invoice‮txt.exe')).not.toBe('');
    expect(jobTitleProblem('x'.repeat(121))).not.toBe('');
    expect(jobDescriptionProblem('line 1\nline 2')).toBe('');
    expect(jobDescriptionProblem('x'.repeat(1001))).not.toBe('');
  });

  it('only redirects inside the site after login', () => {
    expect(safeRedirect('/jobs/3?tab=result')).toBe('/jobs/3?tab=result');
    for (const target of ['//evil.example', '/\\evil.example', 'https://evil.example', 'javascript:alert(1)', '/jobs\n', undefined]) {
      expect(safeRedirect(target)).toBe('/dashboard');
    }
  });

  it('shows the API message rather than its error code', () => {
    expect(extractJobError({ data: { error: 'invalid_query', message: 'Ask a question of 1 to 1,000 characters.' } })).toBe('Ask a question of 1 to 1,000 characters.');
  });

  it('lists each document of a collection once, by name', () => {
    const listed = uniqueDocuments([
      { jobId: 2, name: 'notes/zeta.md' }, { jobId: 1, name: 'alpha.pdf', pages: 3 }, { jobId: 3, name: 'notes/zeta.md' },
    ]);
    expect(listed.map(document => document.name)).toEqual(['alpha.pdf', 'notes/zeta.md']);
  });
});
