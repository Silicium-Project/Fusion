import { describe, expect, it } from 'vitest';
import {
  BATCH_AI_LIMITS,
  buildRequest,
  detectDelimiter,
  guessTextColumn,
  itemsOf,
  outputText,
  readItemTable,
  requestProblem,
  splitNames,
  type BatchRequestInput,
} from '../utils/batchAI';

const input = (change: Partial<BatchRequestInput> = {}): BatchRequestInput => ({
  task: 'classify',
  instruction: 'Classe cet avis.',
  names: 'positif, négatif, neutre',
  items: ['Très bien.', 'Nul.'],
  source: { name: 'avis.csv', column: 'avis' },
  ...change,
});

describe('reading the file', () => {
  it('reads a CSV with quoted cells, its separator and a BOM', () => {
    const table = readItemTable(
      'avis.csv',
      '﻿date;avis\r\n2026-09-01;"Bien ; vraiment\r\n""top"""\r\n2026-09-02;Nul\r\n\r\n',
    );
    expect(table.columns).toEqual(['date', 'avis']);
    expect(table.rows).toEqual([
      ['2026-09-01', 'Bien ; vraiment\r\n"top"'],
      ['2026-09-02', 'Nul'],
    ]);
    expect(guessTextColumn(table)).toBe(1);
  });

  it('detects commas, semicolons and tabs outside quotes', () => {
    expect(detectDelimiter('"a;b",c,d\n')).toBe(',');
    expect(detectDelimiter('a;b;c\n')).toBe(';');
    expect(detectDelimiter('a\tb\n')).toBe('\t');
    expect(detectDelimiter('seul\n')).toBe(',');
  });

  it('names columns without a header and pads short rows', () => {
    const table = readItemTable('x.csv', 'a,\n1,2,3\n');
    expect(table.columns).toEqual(['a', 'Colonne 2', 'Colonne 3']);
    expect(table.rows).toEqual([['1', '2', '3']]);
  });

  it('reads JSON Lines and JSON of strings or objects', () => {
    expect(readItemTable('a.jsonl', '{"t":"un","n":1}\n\n{"t":"deux","x":{"y":1}}\n')).toEqual({
      columns: ['t', 'n', 'x'],
      rows: [
        ['un', '1', ''],
        ['deux', '', '{"y":1}'],
      ],
    });
    expect(readItemTable('a.json', '["un", "deux", 3]').rows).toEqual([['un'], ['deux'], ['3']]);
    expect(() => readItemTable('a.jsonl', '{"a":1}\nnope')).toThrow('ligne 2');
    expect(() => readItemTable('a.json', '{"a":1}')).toThrow();
  });

  it('cuts a text by lines or by paragraphs', () => {
    const text = 'Premier.\nSuite du premier.\n\nSecond.\n';
    expect(readItemTable('notes.txt', text).rows).toEqual([
      ['Premier.'],
      ['Suite du premier.'],
      ['Second.'],
    ]);
    expect(readItemTable('notes.md', text, 'paragraphs').rows).toEqual([
      ['Premier.\nSuite du premier.'],
      ['Second.'],
    ]);
  });

  it('refuses other formats', () => {
    expect(() => readItemTable('a.xlsx', 'PK')).toThrow('a.xlsx');
  });

  it('keeps the non-empty cells of a column', () => {
    expect(itemsOf({ columns: ['a'], rows: [[' x '], [''], ['  '], ['y']] }, 0)).toEqual({
      items: ['x', 'y'],
      skipped: 2,
    });
  });
});

describe('the request', () => {
  it('is built with the output of its task', () => {
    const request = buildRequest(input());
    expect(request).toMatchObject({
      format: 'silicium-llm-request/1',
      task: 'classify',
      output: { kind: 'label', labels: ['positif', 'négatif', 'neutre'] },
      max_tokens: 32,
      items: ['Très bien.', 'Nul.'],
    });
    expect(buildRequest(input({ task: 'extract', names: 'nom; date\nmontant' })).output).toEqual({
      kind: 'fields',
      fields: ['nom', 'date', 'montant'],
    });
    expect(buildRequest(input({ task: 'summarize' })).output).toEqual({ kind: 'text' });
  });

  it('is refused with the reason, as the node would', () => {
    expect(requestProblem(input())).toBe('');
    expect(requestProblem(input({ items: [] }))).toContain('aucun élément');
    expect(requestProblem(input({ items: ['x'.repeat(BATCH_AI_LIMITS.itemChars + 1)] }))).toContain(
      'n° 1',
    );
    expect(requestProblem(input({ names: 'oui' }))).toContain('entre 2');
    expect(requestProblem(input({ names: 'Oui, oui' }))).toContain('deux fois');
    expect(requestProblem(input({ instruction: ' ' }))).toContain('consigne');
    expect(requestProblem(input({ task: 'free', instruction: '' }))).toBe('');
    expect(requestProblem(input({ task: 'extract', names: '' }))).toContain('champs');
  });

  it('splits names on commas, semicolons and lines', () => {
    expect(splitNames(' a ,b;; c\n d  e ')).toEqual(['a', 'b', 'c', 'd e']);
  });
});

describe('answers', () => {
  it('are shown as one line of text', () => {
    expect(outputText(null)).toBe('');
    expect(outputText('positif')).toBe('positif');
    expect(outputText({ nom: 'Alice', date: '' })).toBe('nom : Alice');
  });
});
