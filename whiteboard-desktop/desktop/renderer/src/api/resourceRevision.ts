export type VersionedDocumentResource = 'whiteboard' | 'outline';

export interface ResourceRevisionRead {
  epoch: number;
}

export interface ResourceRevisionReadCommit {
  accepted: boolean;
  revision: string;
}

export class StaleResourceReadError extends Error {
  constructor(kind: VersionedDocumentResource) {
    super(`The ${kind} changed repeatedly while it was loading; try again.`);
    this.name = 'StaleResourceReadError';
  }
}

interface ResourceRevisionEntry {
  revision: string;
  epoch: number;
}

const REVISION_RE = /^[a-f0-9]{32}$/;
const entries = new Map<string, ResourceRevisionEntry>();

function normalizedRevision(value: unknown): string {
  if (typeof value !== 'string' || !REVISION_RE.test(value)) {
    throw new Error('The backend returned an invalid document revision.');
  }
  return value;
}

function key(
  kind: VersionedDocumentResource,
  documentId: string,
  incarnation: string,
): string {
  if (!documentId || !incarnation) {
    throw new Error('The document identity is unavailable; reload the document and try again.');
  }
  return `${kind}:${documentId}:${incarnation}`;
}

export function resourceEtag(
  kind: VersionedDocumentResource,
  incarnation: string,
  revision: string,
): string {
  return `"lfwb:${kind}:${incarnation}:${normalizedRevision(revision)}"`;
}

/** Validate that a resource response body and its strong validator agree. */
export function validateResourceRevisionResponse(
  kind: VersionedDocumentResource,
  incarnation: string,
  revision: unknown,
  etag: string | null,
): string {
  const normalized = normalizedRevision(revision);
  if (etag !== resourceEtag(kind, incarnation, normalized)) {
    throw new Error(`The backend returned an invalid ${kind} ETag.`);
  }
  return normalized;
}

/** Capture an epoch before GET so a late response cannot replace a newer PUT. */
export function beginResourceRevisionRead(
  kind: VersionedDocumentResource,
  documentId: string,
  incarnation: string,
): ResourceRevisionRead {
  return { epoch: entries.get(key(kind, documentId, incarnation))?.epoch ?? 0 };
}

/** Install a GET result only if no mutation or newer GET completed meanwhile. */
export function commitResourceRevisionRead(
  kind: VersionedDocumentResource,
  documentId: string,
  incarnation: string,
  revision: unknown,
  read: ResourceRevisionRead,
): ResourceRevisionReadCommit {
  const entryKey = key(kind, documentId, incarnation);
  const current = entries.get(entryKey);
  const normalized = normalizedRevision(revision);
  if ((current?.epoch ?? 0) !== read.epoch) {
    if (!current) throw new Error('The document revision changed while it was loading.');
    return { accepted: false, revision: current.revision };
  }
  entries.set(entryKey, { revision: normalized, epoch: read.epoch + 1 });
  return { accepted: true, revision: normalized };
}

/** Install a newly-created or explicitly reconciled resource revision. */
export function installResourceRevision(
  kind: VersionedDocumentResource,
  documentId: string,
  incarnation: string,
  revision: unknown,
): string {
  const entryKey = key(kind, documentId, incarnation);
  const current = entries.get(entryKey);
  const normalized = normalizedRevision(revision);
  entries.set(entryKey, { revision: normalized, epoch: (current?.epoch ?? 0) + 1 });
  return normalized;
}

export function requireResourceRevision(
  kind: VersionedDocumentResource,
  documentId: string,
  incarnation: string,
): string {
  const revision = entries.get(key(kind, documentId, incarnation))?.revision;
  if (!revision) {
    throw new Error(`The ${kind} revision is unavailable; reload the document and try again.`);
  }
  return revision;
}

/** Advance one exact acknowledged write; never let a late acknowledgement regress state. */
export function advanceResourceRevision(
  kind: VersionedDocumentResource,
  documentId: string,
  incarnation: string,
  expected: string,
  revision: unknown,
): string {
  const entryKey = key(kind, documentId, incarnation);
  const current = entries.get(entryKey);
  const next = normalizedRevision(revision);
  if (current?.revision === next) return next;
  if (!current || current.revision !== expected) {
    throw new Error(`The ${kind} revision changed while the save acknowledgement was pending.`);
  }
  entries.set(entryKey, { revision: next, epoch: current.epoch + 1 });
  return next;
}

export function clearDocumentResourceRevisions(
  documentId: string,
  incarnation?: string,
): void {
  for (const entryKey of entries.keys()) {
    const [, candidateId, candidateIncarnation] = entryKey.split(':');
    if (candidateId === documentId && (!incarnation || candidateIncarnation === incarnation)) {
      entries.delete(entryKey);
    }
  }
}

/** Test-only reset; production code clears targeted identities on DELETE. */
export function resetResourceRevisionsForTests(): void {
  entries.clear();
}
