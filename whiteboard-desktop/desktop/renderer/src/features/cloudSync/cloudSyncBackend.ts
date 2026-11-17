import { backendFetch, withExpectedDocumentIncarnation } from '../../api/backendAuth';
import { BackendResponseError, responseError } from '../../api/responseError';
import {
  installResourceRevision,
  validateResourceRevisionResponse,
} from '../../api/resourceRevision';
import {
  validateDocumentCreateResponse,
  validateProjectBundleForDocument,
  validateProjectBundleSnapshot,
  type ProjectBundleSnapshot,
} from '../../api/runtimeDtoValidation';
import type { WhiteboardDocument } from '../whiteboard/types';
import { deleteDocument } from '../whiteboard/documentsApi';

export class CloudRestoreRetryStaleError extends BackendResponseError {
  constructor(
    message: string,
    readonly documentId: string | null,
    readonly incarnation: string | null,
  ) {
    super(message, 409, 'cloud_restore_retry_stale', {
      document_id: documentId,
      incarnation,
    });
    this.name = 'CloudRestoreRetryStaleError';
  }
}

export async function readCompleteProjectBundle(
  baseUrl: string,
  documentId: string,
  incarnation: string,
): Promise<ProjectBundleSnapshot> {
  const url = new URL(`${baseUrl}/api/export/project`);
  url.searchParams.set('doc', documentId);
  const response = await backendFetch(url.toString(), {
    headers: withExpectedDocumentIncarnation(incarnation),
  });
  if (!response.ok) throw await responseError(response, 'Could not assemble the cloud snapshot');
  return validateProjectBundleForDocument(await response.json(), documentId);
}

export async function restoreCompleteProjectBundle(
  baseUrl: string,
  bundle: ProjectBundleSnapshot,
  restoreId: string,
  titleSuffix?: string,
): Promise<WhiteboardDocument> {
  // Revalidate provider bytes immediately before the internal restore route.
  const validated = validateProjectBundleSnapshot(bundle);
  const response = await backendFetch(`${baseUrl}/api/cloud-sync/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ restore_id: restoreId, bundle: validated, title_suffix: titleSuffix ?? '' }),
  });
  if (!response.ok) {
    const error = await responseError(response, 'Could not restore the cloud snapshot');
    if (error.code === 'cloud_restore_retry_stale') {
      throw new CloudRestoreRetryStaleError(
        error.message,
        typeof error.details.document_id === 'string' ? error.details.document_id : null,
        typeof error.details.incarnation === 'string' ? error.details.incarnation : null,
      );
    }
    throw error;
  }
  const document = validateDocumentCreateResponse(await response.json()).document;
  const revision = validateResourceRevisionResponse(
    'whiteboard',
    document.incarnation,
    document.revision,
    response.headers.get('ETag'),
  );
  installResourceRevision('whiteboard', document.id, document.incarnation, revision);
  return document;
}

/** Remove a not-yet-published copy-on-write restore after a failed final CAS. */
export async function discardRestoredProject(
  baseUrl: string,
  document: Pick<WhiteboardDocument, 'id' | 'incarnation'>,
): Promise<void> {
  await deleteDocument(baseUrl, document.id, document.incarnation);
}

export interface ConditionalCloudRetireResult {
  deleted: boolean;
  alreadyAbsent: boolean;
  cleanupPending: boolean;
}

function validateCloudRetireResponse(value: unknown): ConditionalCloudRetireResult {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('The backend returned an invalid cloud retirement acknowledgement.');
  }
  const record = value as Record<string, unknown>;
  if (
    record.ok !== true
    || typeof record.deleted !== 'boolean'
    || typeof record.already_absent !== 'boolean'
    || typeof record.cleanup_pending !== 'boolean'
  ) {
    throw new Error('The backend returned an invalid cloud retirement acknowledgement.');
  }
  return {
    deleted: record.deleted,
    alreadyAbsent: record.already_absent,
    cleanupPending: record.cleanup_pending,
  };
}

/**
 * Delete a superseded, inactive project only while its complete graph still
 * matches the bytes that were inspected before the cloud restore. The backend
 * holds the document lifecycle lock across comparison and deletion, closing
 * the final renderer/MCP write race.
 */
export async function retireCloudProjectIfUnchanged(
  baseUrl: string,
  document: Pick<WhiteboardDocument, 'id' | 'incarnation'>,
  expectedDigest: string,
  expectedBundle: ProjectBundleSnapshot,
): Promise<ConditionalCloudRetireResult> {
  const validated = validateProjectBundleSnapshot(expectedBundle);
  const response = await backendFetch(
    `${baseUrl}/api/cloud-sync/retire/${encodeURIComponent(document.id)}`,
    {
      method: 'POST',
      headers: withExpectedDocumentIncarnation(document.incarnation, {
        'Content-Type': 'application/json',
      }),
      body: JSON.stringify({
        expected_digest: expectedDigest,
        expected_bundle: validated,
      }),
    },
  );
  if (!response.ok) throw await responseError(response, 'Could not safely retire the superseded project');
  return validateCloudRetireResponse(await response.json());
}

export function isCloudRetireContentChanged(error: unknown): boolean {
  return error instanceof BackendResponseError
    && error.status === 409
    && error.code === 'cloud_retire_content_changed';
}

export function isCloudRestoreRetryStale(error: unknown): error is CloudRestoreRetryStaleError {
  return error instanceof CloudRestoreRetryStaleError;
}
