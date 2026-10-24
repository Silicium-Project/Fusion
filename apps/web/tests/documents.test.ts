import { describe, expect, it } from 'vitest';
import { documentSelectionError, highlightSegments, isDocumentSearchWorkload, mergeDocumentSelection, passageProgress, passageSource, skipReasonLabel } from '../utils/documents';

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);

describe('document search helpers', () => {
  it('recognizes the document search workload only', () => {
    expect(isDocumentSearchWorkload('ai/embedding/multilingual-e5-small')).toBe(true);
    expect(isDocumentSearchWorkload('raytracer')).toBe(false);
    expect(isDocumentSearchWorkload(undefined)).toBe(false);
  });

  it('accepts documents or one ZIP, and explains every refusal', () => {
    expect(documentSelectionError([file('cours.pdf'), file('notes.MD'), file('contrat.docx')])).toBe('');
    expect(documentSelectionError([file('dossier.zip')])).toBe('');
    expect(documentSelectionError([])).toContain('au moins un document');
    expect(documentSelectionError([file('a.zip'), file('b.pdf')])).toContain('pas les deux');
    expect(documentSelectionError([file('slides.pptx')])).toContain('slides.pptx n’est pas pris en charge');
    expect(documentSelectionError([file('vide.txt', 0)])).toContain('vide');
    expect(documentSelectionError([file('gros.pdf', 65 * 1024 * 1024)])).toContain('64 Mo');
  });

  it('does not select the same file twice', () => {
    const first = file('a.pdf');
    expect(mergeDocumentSelection([first], [file('a.pdf'), file('b.pdf')]).map((f) => f.name)).toEqual(['a.pdf', 'b.pdf']);
  });

  it('says where a passage comes from and why a file was skipped', () => {
    expect(passageSource({ document: 'cours/contrat.pdf', page: 12 })).toBe('contrat.pdf — page 12');
    expect(passageSource({ document: 'notes.txt', page: null })).toBe('notes.txt');
    expect(skipReasonLabel('no_text')).toContain('scannée');
    expect(skipReasonLabel('other')).toBe('non lu');
  });

  it('counts the passages of finished parts', () => {
    const fragments = [{ status: 'completed', items: 120 }, { status: 'running', items: 80 }, { status: 'completed' }];
    expect(passageProgress(fragments, (status) => status === 'completed')).toEqual({ done: 120, total: 200 });
  });

  it('highlights query words regardless of accents, case and endings', () => {
    const segments = highlightSegments('La résiliation du Contrat se fait par lettre.', 'comment resilier le contrat ?');
    expect(segments.filter((s) => s.match).map((s) => s.text)).toEqual(['résiliation', 'Contrat']);
    expect(segments.map((s) => s.text).join('')).toBe('La résiliation du Contrat se fait par lettre.');
    expect(highlightSegments('texte', 'le')).toEqual([{ text: 'texte', match: false }]);
    expect(highlightSegments('le juge contrôle', 'contrat').some((s) => s.match)).toBe(false);
  });
});
