// "Recherche dans mes documents": what the site needs besides the API calls.
// The user drops documents, the network turns their passages into vectors,
// then the user searches them by meaning. Nothing technical (model, vectors,
// passages per part) is shown: these helpers keep the screens in plain words.
import { translate } from './i18n';

/** Workload of a document search (BackEnd `silicium.DocumentSearchWorkload`). */
export const DOCUMENT_SEARCH_WORKLOAD = 'ai/embedding/multilingual-e5-small';

/** File picker filter: the formats the node reads. */
export const DOCUMENT_ACCEPT = '.pdf,.docx,.txt,.md,.markdown,.zip';

/** Limits enforced again by the BackEnd. */
export const MAX_DOCUMENT_BYTES = 64 * 1024 * 1024;
export const MAX_DOCUMENT_FILES = 200;

const DOCUMENT_EXTENSIONS = ['pdf', 'docx', 'txt', 'md', 'markdown'];

export const isDocumentSearchWorkload = (workload: unknown): boolean =>
  String(workload || '').trim() === DOCUMENT_SEARCH_WORKLOAD;

const extensionOf = (name: string): string => {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
};

/** Adds files to a selection, ignoring a file already selected. */
export const mergeDocumentSelection = (current: File[], added: File[]): File[] => {
  const key = (file: File) => `${file.name}:${file.size}`;
  const seen = new Set(current.map(key));
  return [...current, ...added.filter((file) => !seen.has(key(file)) && seen.add(key(file)))];
};

/** Why a selection cannot be sent, in the user's words; '' when it can. */
export const documentSelectionError = (files: File[]): string => {
  if (!files.length) return translate('documents.selection.none');
  if (files.length > MAX_DOCUMENT_FILES) return translate('documents.selection.tooMany', { max: MAX_DOCUMENT_FILES });
  const archives = files.filter((file) => extensionOf(file.name) === 'zip');
  if (archives.length && files.length > 1) return translate('documents.selection.zipAndFiles');
  const unsupported = files.find((file) => extensionOf(file.name) !== 'zip' && !DOCUMENT_EXTENSIONS.includes(extensionOf(file.name)));
  if (unsupported) return translate('documents.selection.unsupported', { name: unsupported.name });
  if (files.some((file) => file.size === 0)) return translate('documents.selection.empty');
  if (files.reduce((total, file) => total + file.size, 0) > MAX_DOCUMENT_BYTES) return translate('documents.selection.tooLarge');
  return '';
};

/** A passage found by a search (`GET /jobs/{id}/search`). */
export interface DocumentHit {
  jobId: number;
  passageId: number;
  document: string;
  page: number | null;
  text: string;
  score: number;
}

/** What the site knows about a finished document search. */
export interface DocumentIndexSummary {
  documents?: { name: string; pages: number; passages: number }[] | null;
  skipped?: { name: string; reason: string }[] | null;
  passageCount?: number | null;
}

/** A document of a collection, listed above the search box. */
export interface CollectionDocument {
  jobId: number;
  name: string;
  pages?: number | null;
  passages?: number | null;
}

const SKIP_REASONS = ['no_text', 'unsupported_format', 'unreadable', 'too_large'];

/** Why a file was not read, in the user's words. */
export const skipReasonLabel = (reason: string): string =>
  translate(`documents.skip.${SKIP_REASONS.includes(reason) ? reason : 'other'}`);

/** The file name of a document path (`dossier/contrat.pdf` → `contrat.pdf`). */
export const documentName = (path: string): string => path.split('/').pop() || path;

/** Where a passage comes from: `contrat.pdf — page 12`. */
export const passageSource = (hit: Pick<DocumentHit, 'document' | 'page'>): string => {
  const name = documentName(hit.document);
  return hit.page ? translate('documents.page', { name, page: hit.page }) : name;
};

/** The documents of a collection, each name once, sorted by name. */
export const uniqueDocuments = (documents: CollectionDocument[]): CollectionDocument[] => {
  const seen = new Set<string>();
  return documents
    .filter((document) => document && typeof document.name === 'string' && !seen.has(document.name) && seen.add(document.name))
    .sort((a, b) => documentName(a.name).localeCompare(documentName(b.name), undefined, { numeric: true, sensitivity: 'base' }));
};

/** Passages read so far, from the parts of the job (`items` per part). */
export const passageProgress = (fragments: { status?: unknown; items?: unknown }[], isDone: (status: unknown) => boolean): { done: number; total: number } =>
  fragments.reduce((progress, fragment) => {
    const count = Number(fragment.items) || 0;
    return { done: progress.done + (isDone(fragment.status) ? count : 0), total: progress.total + count };
  }, { done: 0, total: 0 });

/** Words too common to be worth highlighting. */
const STOP_WORDS = new Set(['les', 'des', 'une', 'est', 'que', 'qui', 'pour', 'par', 'sur', 'dans', 'avec', 'pas', 'plus', 'comment', 'quoi', 'quel', 'quelle', 'the', 'and', 'for', 'how', 'what']);

/** Lowercase without accents, character by character. */
const fold = (character: string): string => character.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/**
 * The text cut into pieces, the pieces matching a word of the query (or a
 * word starting like it: "résilier" matches "résiliation") marked, accents
 * and case ignored.
 */
export const highlightSegments = (text: string, query: string): { text: string; match: boolean }[] => {
  const terms = [...new Set(query.split(/[^\p{L}\p{N}]+/u).map((word) => [...word].map(fold).join('')).filter((word) => word.length >= 3 && !STOP_WORDS.has(word)))]
    .map((word) => (word.length >= 8 ? word.slice(0, word.length - 2) : word));
  if (!terms.length) return [{ text, match: false }];
  const segments: { text: string; match: boolean }[] = [];
  const words = text.split(/([\p{L}\p{N}]+)/u);
  for (const piece of words) {
    if (!piece) continue;
    const folded = [...piece].map(fold).join('');
    const match = /[\p{L}\p{N}]/u.test(piece) && terms.some((term) => folded.startsWith(term));
    const last = segments[segments.length - 1];
    if (last && last.match === match) last.text += piece;
    else segments.push({ text: piece, match });
  }
  return segments;
};
