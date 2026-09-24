import { useEffect, useState, useSyncExternalStore } from 'react';

import {
  abandonPendingDocumentRecoveryAndReload,
  discardPendingDocumentRecovery,
  pendingDocumentRecoveriesSnapshot,
  subscribePendingDocumentRecoveries,
} from '../api/pendingDocumentPersistence';
import { exportSave } from '../features/files/importExportApi';
import {
  captureDocumentIncarnation,
  flushPendingDocSaves,
  useCurrentDocId,
} from '../state/currentDocument';
import { recoveryTargetsActiveDocument } from '../api/pendingRecoveryPolicy';
import { lockDocumentInteraction } from '../features/whiteboard/documentOperationGuard';
import { ConfirmDialog } from './ConfirmDialog';

export function PendingDocumentRecoveryBanner() {
  const recoveries = useSyncExternalStore(
    subscribePendingDocumentRecoveries,
    pendingDocumentRecoveriesSnapshot,
    pendingDocumentRecoveriesSnapshot,
  );
  const [discardOpen, setDiscardOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [savedRecoveryKey, setSavedRecoveryKey] = useState<string | null>(null);
  const recovery = recoveries[0];
  const activeDocumentId = useCurrentDocId();
  const recoveryKey = recovery ? `${recovery.conflictId}:${recovery.version}` : '';

  useEffect(() => {
    setSavedRecoveryKey(null);
    setFeedback(null);
    setDiscardOpen(false);
  }, [recoveryKey]);

  if (!recovery) return null;
  const activeIncarnation = captureDocumentIncarnation(activeDocumentId);
  const targetsActiveDocument = recoveryTargetsActiveDocument(
    recovery,
    activeDocumentId,
    activeIncarnation,
  );

  const saveCopy = async () => {
    setBusy(true);
    setFeedback(null);
    try {
      const content = JSON.stringify({
        format: 'logosforge-pending-document-recovery',
        version: 1,
        exported_at: new Date().toISOString(),
        recovery,
      }, null, 2);
      const result = await exportSave(
        content,
        `logosforge-${recovery.kind}-${recovery.documentId}-recovery.json`,
        [{ name: 'JSON', extensions: ['json'] }],
      );
      if (!result.ok && !result.canceled) {
        setFeedback(result.error ?? 'The recovery copy could not be saved.');
      } else if (result.ok && !result.canceled) {
        setSavedRecoveryKey(recoveryKey);
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    setDiscardOpen(false);
    setBusy(true);
    setFeedback(null);
    const releaseInteraction = targetsActiveDocument ? lockDocumentInteraction() : null;
    let reloading = false;
    try {
      if (targetsActiveDocument) {
        reloading = await abandonPendingDocumentRecoveryAndReload(
          recovery,
          flushPendingDocSaves,
        );
        if (!reloading) {
          setFeedback('Reload was canceled or a newer recovery arrived. The draft is still protected.');
        }
      } else if (!await discardPendingDocumentRecovery(recovery)) {
        setFeedback('A newer recovery snapshot arrived. Review it before discarding.');
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : String(error));
    } finally {
      if (!reloading) releaseInteraction?.();
      setBusy(false);
    }
  };

  return (
    <>
      <div
        role="alert"
        aria-atomic="true"
        data-pending-document-recovery={recovery.conflictId}
        style={{
          position: 'fixed',
          top: 54,
          left: '50%',
          zIndex: 895,
          transform: 'translateX(-50%)',
          width: 'min(820px, calc(100% - 40px))',
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '9px 12px',
          border: '1px solid var(--error, #c0473b)',
          borderRadius: 'var(--r-md, 6px)',
          background: 'var(--panel-2, #fff)',
          color: 'var(--text, #252422)',
          boxShadow: 'var(--page-shadow, 0 12px 40px rgba(0, 0, 0, .28))',
          fontFamily: 'var(--font-ui, sans-serif)',
        }}
      >
        <strong style={{ flex: 'none', color: 'var(--error, #c0473b)', fontSize: 10 }}>
          RECOVERY REQUIRED
        </strong>
        <span style={{ flex: 1, minWidth: 0, fontSize: 11.5, lineHeight: 1.4 }}>
          {recovery.kind === 'whiteboard' ? 'Manuscript' : 'Outline'} draft for document{' '}
          {recovery.documentId} is protected from overwrite. {recovery.error.message}
          {recoveries.length > 1 ? ` (${recoveries.length} recoveries pending.)` : ''}
          {targetsActiveDocument
            ? ' After saving a copy, abandoning this draft reloads the workspace onto a valid saved document.'
            : ''}
          {feedback ? ` ${feedback}` : ''}
        </span>
        <button type="button" disabled={busy} onClick={() => { void saveCopy(); }}>
          Save copy…
        </button>
        <button
          type="button"
          disabled={busy || savedRecoveryKey !== recoveryKey}
          onClick={() => setDiscardOpen(true)}
        >
          {targetsActiveDocument ? 'Abandon & reload…' : 'Discard local draft…'}
        </button>
      </div>
      <ConfirmDialog
        open={discardOpen}
        title="Discard protected local draft?"
        message={targetsActiveDocument
          ? 'This clears the protected local draft and reloads the workspace from saved data.'
          : 'This permanently clears this recovery snapshot.'}
        confirmLabel={targetsActiveDocument ? 'Abandon and reload' : 'Discard draft'}
        onConfirm={() => { void discard(); }}
        onCancel={() => setDiscardOpen(false)}
      />
    </>
  );
}
