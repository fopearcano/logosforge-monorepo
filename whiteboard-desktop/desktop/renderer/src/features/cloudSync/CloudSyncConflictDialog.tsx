import { useEffect, useId, useRef, useState } from 'react';

import { ModalPortal } from '../../components/ModalPortal';
import { useModalDialog } from '../../components/useModalDialog';
import { formatCloudSyncTime, type CloudSyncConflictSummary } from './cloudSyncUi';

type GuardedChoice = 'cloud' | 'device' | null;

interface Props {
  open: boolean;
  conflict: CloudSyncConflictSummary | null;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onKeepBoth: () => void | Promise<void>;
  onUseCloudCopy: () => void | Promise<void>;
  onReplaceCloud: () => void | Promise<void>;
  onRecoverRemote: () => void | Promise<void>;
}
export function CloudSyncConflictDialog({
  open,
  conflict,
  busy = false,
  error = null,
  onClose,
  onKeepBoth,
  onUseCloudCopy,
  onReplaceCloud,
  onRecoverRemote,
}: Props) {
  const [confirming, setConfirming] = useState<GuardedChoice>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const keepBothRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (open) setConfirming(null);
  }, [open, conflict?.projectTitle, conflict?.branchCount]);

  useModalDialog({
    open,
    dialogRef,
    initialFocusRef: keepBothRef,
    onClose: busy ? () => undefined : onClose,
  });

  if (!open || !conflict) return null;

  return (
    <ModalPortal>
      <div
        data-wb-modal-layer
        className="cf-overlay"
        onClick={(event) => {
          if (event.target === event.currentTarget && !busy) onClose();
        }}
      >
        <div
          ref={dialogRef}
          className="cloud-conflict-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={descriptionId}
          tabIndex={-1}
        >
          <div className="settings-head">
            <h2 id={titleId} className="settings-title">Review sync conflict</h2>
            <button
              type="button"
              className="settings-close"
              aria-label="Close sync conflict"
              disabled={busy}
              onClick={onClose}
            >
              ×
            </button>
          </div>
          <p id={descriptionId} className="settings-sub">
            {conflict.kind === 'remote-recovery' ? (
              <>
                <strong>{conflict.projectTitle}</strong> has multiple preserved cloud versions, but no local copy
                remains linked to that history. Whiteboard can import every version as a separate project.
              </>
            ) : (
              <>
                <strong>{conflict.projectTitle}</strong> changed on more than one device. Whiteboard preserved every
                snapshot and will not replace either branch without your choice.
              </>
            )}
          </p>

          {conflict.kind === 'bound-conflict' && (
            <div className="cloud-conflict-branches" aria-label="Conflicting versions">
              <div>
                <span>This device</span>
                <strong>{conflict.localDeviceLabel}</strong>
                <time>{formatCloudSyncTime(conflict.localChangedAt)}</time>
              </div>
              <div>
                <span>Cloud copy</span>
                <strong>{conflict.remoteDeviceLabel}</strong>
                <time>{formatCloudSyncTime(conflict.remoteChangedAt)}</time>
              </div>
            </div>
          )}
          <p className="cloud-conflict-count">
            {conflict.branchCount} preserved {conflict.branchCount === 1 ? 'branch' : 'branches'} in sync history.
          </p>

          {conflict.kind === 'remote-recovery' ? (
            <div className="cloud-conflict-actions">
              <button
                ref={keepBothRef}
                type="button"
                className="settings-btn is-primary"
                disabled={busy}
                onClick={() => void onRecoverRemote()}
              >
                {busy ? 'Recovering…' : 'Import every preserved version'}
              </button>
            </div>
          ) : confirming === null ? (
            <div className="cloud-conflict-actions">
              <button
                ref={keepBothRef}
                type="button"
                className="settings-btn is-primary"
                disabled={busy}
                onClick={() => void onKeepBoth()}
              >
                Keep both (recommended)
              </button>
              <button type="button" className="settings-btn" disabled={busy} onClick={() => setConfirming('cloud')}>
                Use cloud copy
              </button>
              <button type="button" className="settings-btn" disabled={busy} onClick={() => setConfirming('device')}>
                Replace cloud with this device
              </button>
            </div>
          ) : (
            <div className="cloud-conflict-confirm" aria-live="polite">
              <p>
                {confirming === 'cloud'
                  ? 'Resolve the project to the cloud copy? This device’s version remains preserved in sync history.'
                  : 'Resolve the project to this device’s copy? The other version remains preserved in sync history.'}
              </p>
              <div>
                <button type="button" className="settings-btn" disabled={busy} onClick={() => setConfirming(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="settings-btn is-danger"
                  disabled={busy}
                  onClick={() => void (confirming === 'cloud' ? onUseCloudCopy() : onReplaceCloud())}
                >
                  {busy ? 'Resolving…' : 'Confirm resolution'}
                </button>
              </div>
            </div>
          )}

          {error && <p className="cloud-conflict-error" role="alert">{error}</p>}
        </div>
      </div>
    </ModalPortal>
  );
}
