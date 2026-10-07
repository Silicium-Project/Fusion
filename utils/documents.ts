// "Recherche dans mes documents": what the site needs besides the API calls.
// The user drops documents, the network turns their passages into vectors,
// then the user searches them by meaning. Nothing technical (model, vectors,
// passages per part) is shown: these helpers keep the screens in plain words.

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
  if (!files.length) return 'Ajoute au moins un document.';
  if (files.length > MAX_DOCUMENT_FILES) return `Envoie ${MAX_DOCUMENT_FILES} fichiers au plus, ou un ZIP du dossier.`;
  const archives = files.filter((file) => extensionOf(file.name) === 'zip');
  if (archives.length && files.length > 1) return 'Envoie soit un ZIP, soit des documents, mais pas les deux ensemble.';
  const unsupported = files.find((file) => extensionOf(file.name) !== 'zip' && !DOCUMENT_EXTENSIONS.includes(extensionOf(file.name)));
  if (unsupported) return `${unsupported.name} n’est pas pris en charge : envoie des PDF, des fichiers Word (.docx), texte, Markdown ou un ZIP.`;
  if (files.some((file) => file.size === 0)) return 'Un des documents est vide.';
  if (files.reduce((total, file) => total + file.size, 0) > MAX_DOCUMENT_BYTES) return 'Les documents dépassent 64 Mo au total. Envoie-les en plusieurs fois.';
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

/** Why a file was not read, in the user's words. */
export const skipReasonLabel = (reason: string): string => ({
  no_text: 'aucun texte lisible : c’est sans doute une image scannée',
  unsupported_format: 'format non pris en charge',
  unreadable: 'fichier abîmé ou protégé',
  too_large: 'fichier trop gros',
} as Record<string, string>)[reason] || 'non lu';

/** Where a passage comes from: `contrat.pdf — page 12`. */
export const passageSource = (hit: Pick<DocumentHit, 'document' | 'page'>): string => {
  const name = hit.document.split('/').pop() || hit.document;
  return hit.page ? `${name} — page ${hit.page}` : name;
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
