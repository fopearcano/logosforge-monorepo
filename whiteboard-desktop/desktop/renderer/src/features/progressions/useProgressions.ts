import { useCallback, useEffect, useRef, useState } from 'react';

import { captureDocumentIdentity, subscribeCurrentDoc } from '../../state/currentDocument';
import {
  abandonPendingProgressionCommand,
  getProgressions,
  hasPendingProgressionCommand,
  ProgressionRecoveryPendingError,
  resumePendingProgressionCommand,
  runProgressionCommand,
} from './progressionsApi';
import type { ProgressionCommand, ProgressionCommandInput, ProgressionSnapshot } from './types';

export function useProgressions(baseUrl: string) {
  const [snapshot, setSnapshot] = useState<ProgressionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recoveryPending, setRecoveryPending] = useState(
    () => hasPendingProgressionCommand(baseUrl),
  );
  const executingRef = useRef(false);

  const refresh = useCallback(async () => {
    const identity = captureDocumentIdentity();
    if (!identity.documentId) return;
    const isCurrent = () => {
      const current = captureDocumentIdentity();
      return current.documentId === identity.documentId
        && current.incarnation === identity.incarnation;
    };
    setLoading(true);
    setError(null);
    try {
      const value = await getProgressions(baseUrl, identity);
      if (isCurrent()) setSnapshot(value);
    } catch (reason) {
      if (isCurrent()) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    void refresh();
    return subscribeCurrentDoc(() => {
      setSnapshot(null);
      setError(null);
      setSaving(false);
      setLoading(true);
      executingRef.current = false;
      setRecoveryPending(hasPendingProgressionCommand(baseUrl));
      void refresh();
    });
  }, [baseUrl, refresh]);

  const execute = useCallback(async (
    command: ProgressionCommandInput,
  ) => {
    if (!snapshot || executingRef.current) return null;
    const identity = captureDocumentIdentity();
    const isCurrent = () => {
      const current = captureDocumentIdentity();
      return current.documentId === identity.documentId
        && current.incarnation === identity.incarnation;
    };
    executingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const next = await runProgressionCommand(baseUrl, {
        ...command,
        expected_revision: snapshot.revision,
      } as ProgressionCommand);
      if (!isCurrent()) return null;
      setSnapshot(next);
      setRecoveryPending(false);
      return next;
    } catch (reason) {
      if (isCurrent()) {
        setRecoveryPending(
          reason instanceof ProgressionRecoveryPendingError
          || hasPendingProgressionCommand(baseUrl, identity),
        );
        setError(reason instanceof Error ? reason.message : String(reason));
      }
      return null;
    } finally {
      executingRef.current = false;
      if (isCurrent()) setSaving(false);
    }
  }, [baseUrl, snapshot]);

  const retryPending = useCallback(async () => {
    if (executingRef.current) return null;
    const identity = captureDocumentIdentity();
    const isCurrent = () => {
      const current = captureDocumentIdentity();
      return current.documentId === identity.documentId
        && current.incarnation === identity.incarnation;
    };
    executingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      const next = await resumePendingProgressionCommand(baseUrl, identity);
      if (!isCurrent()) return null;
      setRecoveryPending(hasPendingProgressionCommand(baseUrl, identity));
      if (next) setSnapshot(next);
      return next;
    } catch (reason) {
      if (isCurrent()) {
        setRecoveryPending(hasPendingProgressionCommand(baseUrl, identity));
        setError(reason instanceof Error ? reason.message : String(reason));
      }
      return null;
    } finally {
      executingRef.current = false;
      if (isCurrent()) setSaving(false);
    }
  }, [baseUrl]);

  const abandonPending = useCallback(() => {
    abandonPendingProgressionCommand(baseUrl);
    setRecoveryPending(false);
    setError(null);
  }, [baseUrl]);

  return {
    snapshot, loading, saving, error, recoveryPending,
    refresh, execute, retryPending, abandonPending,
  };
}
