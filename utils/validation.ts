// Checks of the text users type, mirroring the API (BackEnd
// `internal/handler/userInput.go`): the site refuses early with a clear
// message, the API refuses again whatever the client sends.
//
// Each function returns the catalog key of the problem, '' when the value
// is accepted.

/** Limits shared with the API. */
export const LIMITS = {
  email: 254,
  username: 30,
  personName: 50,
  passwordMin: 8,
  passwordBytes: 72,
  jobTitle: 120,
  jobDescription: 1000,
  contactName: 100,
  contactMessage: 4000,
} as const;

const EMAIL = /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;
const USERNAME = /^[A-Za-z0-9._-]{3,30}$/;
const RESERVED_USERNAMES = new Set(['admin', 'administrator', 'root', 'silicium', 'support', 'system', 'moderator', 'staff']);
/** Letters of any alphabet, combining marks, spaces, hyphens, apostrophes, dots; at least one letter. */
const PERSON_NAME = /^(?=.*\p{L})[\p{L}\p{Mn} '’.-]+$/u;
/** Control characters (line breaks and tabs aside) and invisible reordering characters. */
const HIDDEN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏‪-‮⁠-⁩﻿]/;

const characters = (value: string) => [...value].length;

export function emailProblem(value: string): string {
  const email = value.trim().toLowerCase();
  const local = email.split('@')[0] || '';
  return email.length <= LIMITS.email && local.length <= 64 && EMAIL.test(email) ? '' : 'validation.emailInvalid';
}

/** An empty username is allowed (optional field). */
export function usernameProblem(value: string): string {
  const username = value.trim();
  if (!username) return '';
  return USERNAME.test(username) && !RESERVED_USERNAMES.has(username.toLowerCase()) && /[A-Za-z0-9]/.test(username) ? '' : 'validation.usernameInvalid';
}

/** An empty name is allowed (optional field). */
export function personNameProblem(value: string): string {
  const name = value.trim().replace(/\s+/g, ' ');
  if (!name) return '';
  return characters(name) <= LIMITS.personName && PERSON_NAME.test(name) ? '' : 'validation.nameInvalid';
}

export function newPasswordProblem(value: string): string {
  if (characters(value) < LIMITS.passwordMin) return 'validation.passwordShort';
  if (new TextEncoder().encode(value).length > LIMITS.passwordBytes) return 'validation.passwordLong';
  return '';
}

export function jobTitleProblem(value: string): string {
  const title = value.trim();
  return characters(title) <= LIMITS.jobTitle && !HIDDEN.test(title) && !/[\r\n\t]/.test(title) ? '' : 'validation.titleInvalid';
}

export function jobDescriptionProblem(value: string): string {
  return characters(value.trim()) <= LIMITS.jobDescription && !HIDDEN.test(value) ? '' : 'validation.descriptionLong';
}

/** The first problem of a list of checks, '' when all pass. */
export const firstProblem = (...problems: string[]): string => problems.find(Boolean) || '';
