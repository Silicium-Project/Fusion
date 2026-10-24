import { describe, expect, it } from 'vitest';
import { HF_WORKLOAD, TASK_FORMS, buildParameters, buildSiteRequest, fieldItem, fileItem, hfRequestProblem, hfTaskOf, hfWorkloadId, isHFWorkload, modelSize, outputSummary, splitLabels } from '../utils/hfCatalog';
import { translate } from '../utils/i18n';

describe('catalogue workloads', () => {
  it('names a task and a model', () => {
    const id = hfWorkloadId('text-classification', 'org--model-0123456789ab');
    expect(id).toBe('ai/hf/text-classification/org--model-0123456789ab');
    expect(isHFWorkload(id)).toBe(true);
    expect(isHFWorkload(HF_WORKLOAD)).toBe(true);
    expect(isHFWorkload('ai/llm/qwen2.5-1.5b-instruct')).toBe(false);
    expect(hfTaskOf(id)).toBe('text-classification');
  });

  it('has a form for every task the network runs (19, as the node)', () => {
    expect(Object.keys(TASK_FORMS)).toHaveLength(19);
  });
});

describe('parameters', () => {
  it('uses the defaults and bounds what the user types', () => {
    expect(buildParameters('text-classification', {})).toEqual({ parameters: { top_k: 3 }, problem: '' });
    expect(buildParameters('text-classification', { top_k: 99 }).problem).toBe('parameter');
    expect(buildParameters('text-classification', { top_k: 2.5 }).problem).toBe('parameter');
    expect(buildParameters('object-detection', { threshold: 0.3 }).parameters).toEqual({ threshold: 0.3 });
  });

  it('needs the labels of a zero-shot task and leaves out empty texts', () => {
    expect(buildParameters('zero-shot-classification', { candidate_labels: '' }).problem).toBe('labels');
    expect(buildParameters('zero-shot-classification', { candidate_labels: 'sport, art\nsport' }).parameters).toEqual({ candidate_labels: ['sport', 'art'] });
    expect(buildParameters('translation', { src_lang: '', tgt_lang: 'en_XX' }).parameters).toEqual({ max_new_tokens: 256, tgt_lang: 'en_XX' });
    expect(splitLabels(' a ; b,,c ')).toEqual(['a', 'b', 'c']);
  });
});

describe('items', () => {
  it('builds the fields of a row', () => {
    expect(fieldItem(['question', 'context'], ['Qui ?', 'Marie.'])).toEqual({ question: 'Qui ?', context: 'Marie.' });
    expect(fieldItem(['query', 'texts'], ['chat', 'a | b'])).toEqual({ query: 'chat', texts: ['a', 'b'] });
    expect(fieldItem(['query', 'table'], ['total ?', '{"a":["1"]}'])).toEqual({ query: 'total ?', table: { a: ['1'] } });
    expect(fieldItem(['query', 'table'], ['total ?', '[1]'])).toBe('table');
    expect(fieldItem(['question', 'context'], ['Qui ?', ' '])).toBe('missing:context');
  });

  it('reads files as base64', async () => {
    expect(await fileItem(new Blob([new Uint8Array([104, 105])]))).toEqual({ $bytes: 'aGk=' });
  });

  it('refuses empty or oversized requests', () => {
    expect(hfRequestProblem([])).toBe('noItems');
    expect(hfRequestProblem(['ok', '  '])).toBe('emptyItem');
    expect(hfRequestProblem(['x'.repeat(20_001)])).toBe('itemTooLong');
    expect(hfRequestProblem(['ok'])).toBe('');
    expect(buildSiteRequest('summarization', ['a'], {}, 'notes.txt')).toEqual({ format: 'silicium-hf-site-request/1', task: 'summarization', parameters: {}, items: ['a'], source: { name: 'notes.txt' } });
  });
});

describe('outputs', () => {
  it('summarises the Hub task shapes for the answers table', () => {
    expect(outputSummary([{ label: 'positif', score: 0.91 }, { label: 'négatif', score: 0.09 }])).toBe('positif 91 % · négatif 9 %');
    expect(outputSummary({ sequence: 'x', labels: ['sport'], scores: [0.7] })).toBe('sport 70 %');
    expect(outputSummary([{ generated_text: 'Bonjour' }])).toBe('Bonjour');
    expect(outputSummary({ text: 'bonjour à tous' })).toBe('bonjour à tous');
    expect(outputSummary([{ entity_group: 'PER', word: 'Marie' }])).toBe('Marie [PER]');
    expect(outputSummary([{ label: 'chat', score: 0.8, box: { xmin: 0, ymin: 0, xmax: 1, ymax: 1 } }])).toBe('chat (0.80)');
    expect(outputSummary([{ index: 1, score: 2 }, { index: 0, score: 1 }])).toBe('#2 > #1');
    expect(outputSummary([0.1, 0.2])).toMatch(/^\[2\] 0.100, 0.200/);
    expect(modelSize(1.5 * 1024 ** 3)).toBe('1,5 Go');
    expect(modelSize(350 * 1024 ** 2, 'en')).toBe('350 MB');
  });

  it('fills the placeholders of plural messages', () => {
    expect(translate('catalogAI.modelCount', { count: 3 })).toBe('3 modèles');
    expect(translate('catalogAI.coldText', { count: 2, size: '2.2' })).toMatch(/^Le modèle sera installé sur 2 machines \(2.2 Go/);
  });
});
