// Syntax of scene files, as the engine reads it (port of
// Network/crates/raytracer/src/engine/syntax.rs): `key = value` and
// `name = { ... }` (`:` works like `=`), comments (`#`, `//`), quoted text,
// lists of bare values, keyframes (`x = { 0 = 1  48 = 5 }`) and libconfig
// lists (`( ... )`).

export type Value = { kind: 'number'; value: number } | { kind: 'word'; value: string } | { kind: 'block'; entries: Entry[] };

export interface Entry {
  key?: string;
  value: Value;
  /** 1-based line of the key (or of the bare value). */
  line: number;
}

export class SyntaxError {
  constructor(public line: number, public code: 'unbalanced_braces' | 'syntax_error', public message: string) {}
}

type Token = { type: 'open' | 'close' | 'assign'; line: number } | { type: 'text'; text: string; quoted: boolean; line: number };

/** Rust's `str::parse::<f64>()` (no hex, no empty string). */
export function parseRustFloat(text: string): number | undefined {
  if (/^[+-]?(inf|infinity)$/i.test(text)) return text.startsWith('-') ? -Infinity : Infinity;
  if (/^[+-]?nan$/i.test(text)) return Number.NaN;
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(text)) return undefined;
  return Number(text);
}

function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  const chars = Array.from(text);
  let line = 1;
  let current = '';
  const flush = () => {
    if (current) tokens.push({ type: 'text', text: current, quoted: false, line });
    current = '';
  };
  for (let index = 0; index < chars.length; index += 1) {
    const character = chars[index]!;
    const signAllowed = current === '' || (/[eE]$/.test(current) && /^[0-9.+-]/.test(current));
    if (/[A-Za-z0-9_.]/.test(character)) current += character;
    else if ((character === '-' || character === '+') && signAllowed) current += character;
    else if (character === '#' || (character === '/' && chars[index + 1] === '/')) {
      flush();
      while (index + 1 < chars.length && chars[index + 1] !== '\n') index += 1;
    } else if (character === '"') {
      flush();
      const start = line;
      let word = '';
      for (;;) {
        index += 1;
        const next = chars[index];
        if (next === '"') break;
        if (next === undefined || next === '\n') throw new SyntaxError(start, 'syntax_error', 'unterminated text: a `"` is missing');
        word += next;
      }
      tokens.push({ type: 'text', text: word, quoted: true, line: start });
    } else {
      flush();
      if (character === '{' || character === '(') tokens.push({ type: 'open', line });
      else if (character === '}' || character === ')') tokens.push({ type: 'close', line });
      else if (character === '=' || character === ':') tokens.push({ type: 'assign', line });
      else if (character === '\n') line += 1;
    }
  }
  flush();
  return tokens;
}

function scalar(text: string, quoted: boolean): Value {
  if (!quoted) {
    const number = parseRustFloat(text);
    if (number !== undefined) return { kind: 'number', value: number };
  }
  return { kind: 'word', value: text };
}

/** Parses a whole scene file into its top-level entries; throws a `SyntaxError`. */
export function parse(text: string): Entry[] {
  const tokens = tokenize(text);
  let position = 0;
  const lineAt = () => (tokens[position] || tokens[tokens.length - 1])?.line ?? 1;
  const block = (openedAt: number | undefined): Entry[] => {
    const entries: Entry[] = [];
    for (;;) {
      const line = lineAt();
      const token = tokens[position];
      if (!token) {
        if (openedAt !== undefined) throw new SyntaxError(openedAt, 'unbalanced_braces', 'this block is never closed: a `}` is missing');
        return entries;
      }
      if (token.type === 'close') {
        position += 1;
        if (openedAt === undefined) throw new SyntaxError(line, 'unbalanced_braces', 'this `}` closes nothing');
        return entries;
      }
      if (token.type === 'assign') { position += 1; continue; }
      if (token.type === 'open') {
        position += 1;
        entries.push({ value: { kind: 'block', entries: block(line) }, line });
        continue;
      }
      if (token.type !== 'text') continue;
      position += 1;
      if (tokens[position]?.type === 'assign') {
        position += 1;
        const next = tokens[position];
        let value: Value;
        if (next?.type === 'open') {
          const opened = lineAt();
          position += 1;
          value = { kind: 'block', entries: block(opened) };
        } else if (next?.type === 'text') {
          position += 1;
          value = scalar(next.text, next.quoted);
        } else {
          throw new SyntaxError(line, 'syntax_error', `\`${token.text}\` has no value after \`=\``);
        }
        entries.push({ key: token.text, value, line });
      } else {
        entries.push({ value: scalar(token.text, token.quoted), line });
      }
    }
  };
  return block(undefined);
}

/** First entry named `key`. */
export const entry = (entries: Entry[], key: string): Entry | undefined => entries.find((item) => item.key === key);

/** Every entry named `key`. */
export const all = (entries: Entry[], key: string): Entry[] => entries.filter((item) => item.key === key);

/** The block named `key`, if any. */
export function block(entries: Entry[], key: string): Entry[] | undefined {
  const found = entry(entries, key);
  return found?.value.kind === 'block' ? found.value.entries : undefined;
}

/** The word named `key`, if any. */
export function word(entries: Entry[], key: string): string | undefined {
  const found = entry(entries, key);
  return found?.value.kind === 'word' ? found.value.value : undefined;
}

/** Bare numbers of a block (`vertices = { 0 0 0  1 0 0 }`). */
export const numbers = (entries: Entry[]): number[] =>
  entries.filter((item) => item.key === undefined && item.value.kind === 'number').map((item) => (item.value as { value: number }).value);

/** Keyframes `{ 0 = 1  48 = 5  ease = smooth }`, sorted by frame. */
export function keyframes(entries: Entry[]): { keys: [number, number][]; smooth: boolean } | undefined {
  const keys: [number, number][] = [];
  let smooth = false;
  for (const item of entries) {
    if (item.key === undefined) return undefined;
    if (item.key === 'ease') { smooth = item.value.kind === 'word' && item.value.value === 'smooth'; continue; }
    const frame = parseRustFloat(item.key);
    if (frame === undefined || item.value.kind !== 'number') return undefined;
    keys.push([frame, item.value.value]);
  }
  if (!keys.length) return undefined;
  keys.sort((a, b) => a[0] - b[0]);
  return { keys, smooth };
}

/** Value of a number or of keyframes at `frame`. */
export function evaluate(value: Value, frame: number): number | undefined {
  if (value.kind === 'number') return value.value;
  if (value.kind === 'word') return undefined;
  const found = keyframes(value.entries);
  if (!found) return undefined;
  const { keys, smooth } = found;
  const first = keys[0]!;
  const last = keys[keys.length - 1]!;
  if (frame <= first[0]) return first[1];
  if (frame >= last[0]) return last[1];
  const index = keys.findIndex(([at]) => at > frame);
  const a = keys[index - 1]!;
  const b = keys[index]!;
  let t = (frame - a[0]) / (b[0] - a[0]);
  if (smooth) t = t * t * (3 - 2 * t);
  return a[1] + (b[1] - a[1]) * t;
}

/** Number `key` at `frame` (keyframes interpolated), else `fallback`. */
export function number(entries: Entry[], key: string, fallback: number, frame = 0): number {
  const found = entry(entries, key);
  return (found && evaluate(found.value, frame)) ?? fallback;
}

/** The blocks of a value: itself, or each block of a list (`( { … }, { … } )`). */
export function items(value: Value): Entry[][] {
  if (value.kind !== 'block') return [];
  const list = value.entries;
  if (list.length && list.every((item) => item.key === undefined && item.value.kind === 'block')) {
    return list.map((item) => (item.value as { entries: Entry[] }).entries);
  }
  return [list];
}
