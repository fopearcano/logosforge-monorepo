import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import type {
  ProgressionAnchorKind,
  ProgressionCommandDTO,
  ProgressionKind,
  ProgressionBeatDTO,
  ProgressionSnapshotDTO,
  ProgressionTrackDTO,
} from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { useProgressions, usePsykeEntries, useScenes } from "../../hooks";
import {
  useNavigate,
  useProgressionTarget,
  useStudio,
  type ProgressionNavigationTarget,
} from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { usePanelHostWindow } from "../common/PanelHost";
import { ApiRequestError, ApiRequestTimeoutError } from "../../adapters/httpApiClient";
import {
  discardProjectSavePending,
  markProjectSavePending,
  registerProjectFlusher,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import {
  ProgressionCommandCoordinator,
  progressionCommandStorageForWindow,
  type PendingProgressionCommand,
} from "../../adapters/progressionCommandCoordinator";

const KINDS: readonly ProgressionKind[] = [
  "story", "character", "relationship", "theme", "world", "custom",
];
const COLORS = ["", "cyan", "green", "amber", "crimson", "violet", "blue", "gray"];

interface TrackDraft {
  type: "track";
  mode: "create" | "update";
  trackId: number | null;
  trackKind: ProgressionKind;
  title: string;
  description: string;
  colorLabel: string;
  primaryPsykeEntryId: number | null;
  secondaryPsykeEntryId: number | null;
  originalTrackKind: ProgressionKind | null;
  originalPrimaryPsykeEntryId: number | null;
  originalSecondaryPsykeEntryId: number | null;
  legacyCompatibilityLocked: boolean;
  /** Authoritative Progressions revision from which this full-field edit opened. */
  sourceRevision: string | null;
  dirty: boolean;
}

interface BeatDraft {
  type: "beat";
  mode: "create" | "update";
  trackId: number;
  beatId: number | null;
  text: string;
  anchorKind: ProgressionAnchorKind;
  sceneId: number | null;
  anchorRef: string;
  anchorLabel: string;
  originalText: string | null;
  /** Authoritative Progressions revision from which this full-field edit opened. */
  sourceRevision: string | null;
  dirty: boolean;
}

type EditorDraft = TrackDraft | BeatDraft;

interface CommandSnapshotState {
  value: ProgressionSnapshotDTO;
  /** First read generation allowed to supersede this optimistic result. */
  authoritativeRequestId: number;
}

class ProgressionReceiptOnlyError extends Error {}

const root: CSSProperties = {
  position: "relative",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
};
const button: CSSProperties = {
  font: "inherit",
  fontSize: 8,
  letterSpacing: ".08em",
  padding: "5px 8px",
  border: "1px solid var(--line2)",
  background: "var(--tint)",
  color: "var(--txt2)",
  cursor: "pointer",
};
const input: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  font: "inherit",
  fontSize: 10,
  padding: "6px 7px",
  border: "1px solid var(--line2)",
  background: "var(--base)",
  color: "var(--txt)",
  outline: "none",
};
const label: CSSProperties = {
  display: "grid",
  gap: 4,
  color: "var(--txt3)",
  fontSize: 8,
  letterSpacing: ".08em",
};

function isAmbiguousFailure(error: unknown): boolean {
  if (error instanceof ApiRequestTimeoutError) return error.outcomeUnknown;
  if (error instanceof ApiRequestError) {
    return error.status === 408 || error.status === 429 || error.status >= 500;
  }
  return true;
}

function isReceiptMiss(error: unknown): boolean {
  return error instanceof ApiRequestError && error.code === "progression_receipt_not_found";
}

function idempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `progression-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function draftKey(projectId: number, draft: EditorDraft): string {
  return draft.type === "track"
    ? `progression-track:${projectId}:${draft.trackId ?? "new"}`
    : `progression-beat:${projectId}:${draft.beatId ?? `new-${draft.trackId}`}`;
}

function coverageColor(status: ProgressionTrackDTO["coverage"]["status"]): string {
  if (status === "complete") return "var(--green)";
  if (status === "partial") return "var(--amber)";
  if (status === "unanchored") return "var(--crimson)";
  return "var(--txt3)";
}

function anchorText(
  anchorKind: ProgressionAnchorKind,
  sceneTitle: string,
  anchorLabel: string,
  anchorRef: string | null,
): string {
  if (anchorKind === "scene") return sceneTitle || "Scene";
  if (anchorKind === "document_block") return anchorLabel || anchorRef || "Document block";
  return "Unanchored";
}

/** Resolve an exact cross-panel target without guessing by label or order. */
export function resolveProgressionNavigationTarget(
  tracks: readonly ProgressionTrackDTO[],
  target: ProgressionNavigationTarget,
): { track: ProgressionTrackDTO; beat: ProgressionBeatDTO | null } | null {
  const beatOwner = target.beatId == null
    ? null
    : tracks.find((track) => track.beats.some((beat) => beat.id === target.beatId)) ?? null;
  const track = target.trackId == null
    ? beatOwner
    : tracks.find((candidate) => candidate.id === target.trackId) ?? null;
  if (!track) return null;
  const beat = target.beatId == null
    ? null
    : track.beats.find((candidate) => candidate.id === target.beatId) ?? null;
  if (target.beatId != null && !beat) return null;
  return { track, beat };
}

export function ProgressionsPanel(props: PanelProps) {
  const { api, platform, projectId } = useStudio();
  const navigate = useNavigate();
  const { target: progressionTarget, clear: clearProgressionTarget } = useProgressionTarget();
  const ownerWindow = usePanelHostWindow();
  const { setSelection } = useSelection();
  const { data, loading, error, refetch, lastSuccessfulRequest } = useProgressions();
  const { data: psykeEntries = [] } = usePsykeEntries();
  const { data: scenes = [] } = useScenes();
  const commandCoordinator = useMemo(() => new ProgressionCommandCoordinator(
    platform.persistenceScope,
    platform.progressionCommandStorage
      ?? (platform.isDesktop ? null : progressionCommandStorageForWindow(ownerWindow)),
  ), [ownerWindow, platform.isDesktop, platform.persistenceScope, platform.progressionCommandStorage]);
  const commandCoordinatorRef = useRef(commandCoordinator);
  commandCoordinatorRef.current = commandCoordinator;
  const [commandSnapshot, setCommandSnapshot] = useState<CommandSnapshotState | null>(null);
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const [kindFilter, setKindFilter] = useState<ProgressionKind | "all">("all");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [recoveryReady, setRecoveryReady] = useState(projectId == null);
  const [recoveryError, setRecoveryError] = useState("");
  const [recoveryAttempt, setRecoveryAttempt] = useState(0);
  const [targetNotice, setTargetNotice] = useState("");
  const [focusedBeatId, setFocusedBeatId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EditorDraft | null>(null);
  const draftRef = useRef<EditorDraft | null>(null);
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const displayedProjectIdRef = useRef(projectId);
  const saveDraftRef = useRef<() => Promise<boolean>>(async () => true);
  const flushProgressionsRef = useRef<() => Promise<boolean>>(async () => true);
  const pendingProgressionCommandsRef = useRef(new Map<string, PendingProgressionCommand>());
  const inFlightProgressionCommandsRef = useRef(new Set<string>());
  const [receiptOnlySaveKey, setReceiptOnlySaveKey] = useState<string | null>(null);
  const recoveryGenerationRef = useRef(0);
  const trackTargetRefs = useRef(new Map<number, HTMLButtonElement>());
  const beatTargetRefs = useRef(new Map<number, HTMLButtonElement>());
  const targetFrameRef = useRef<number | null>(null);
  const consumedTargetRef = useRef("");
  const targetRequestRef = useRef<{ token: string; requestId: number } | null>(null);
  const clearProgressionTargetRef = useRef(clearProgressionTarget);
  clearProgressionTargetRef.current = clearProgressionTarget;
  const authoritativeReadSupersedesCommand = commandSnapshot != null
    && data?.project_id === projectId
    && lastSuccessfulRequest >= commandSnapshot.authoritativeRequestId;
  const snapshot = commandSnapshot != null
    && commandSnapshot.value.project_id === projectId
    && !authoritativeReadSupersedesCommand
    ? commandSnapshot.value
    : data;

  useEffect(() => {
    if (!authoritativeReadSupersedesCommand) return;
    setCommandSnapshot((current) => current === commandSnapshot ? null : current);
  }, [authoritativeReadSupersedesCommand, commandSnapshot]);

  useEffect(() => {
    const generation = recoveryGenerationRef.current + 1;
    recoveryGenerationRef.current = generation;
    let active = true;
    const previousProjectId = displayedProjectIdRef.current;
    displayedProjectIdRef.current = projectId;
    setCommandSnapshot(null);
    setSelectedTrackId(null);
    setDraft(null);
    draftRef.current = null;
    setBusy("");
    setStatus("");
    setMutationError("");
    setTargetNotice("");
    setFocusedBeatId(null);
    consumedTargetRef.current = "";
    targetRequestRef.current = null;
    inFlightProgressionCommandsRef.current.clear();
    setReceiptOnlySaveKey(null);
    setRecoveryError("");
    setRecoveryReady(projectId == null);

    if (projectId == null) return () => { active = false; };
    void (async () => {
      try {
        if (platform.isDesktop && !platform.progressionCommandStorage) {
          throw new Error("the desktop host did not provide app-owned recovery storage");
        }
        if (previousProjectId != null && previousProjectId !== projectId) {
          for (const [saveKey, pending] of pendingProgressionCommandsRef.current) {
            if (pending.projectId !== previousProjectId) continue;
            const locked = { ...pending, receiptOnly: true };
            if (!await commandCoordinator.save(saveKey, locked)) {
              throw new Error("the previous project's pending command could not be locked durably");
            }
            pendingProgressionCommandsRef.current.set(saveKey, locked);
          }
        }
        const stored = await commandCoordinator.load(projectId);
        if (!active || recoveryGenerationRef.current !== generation) return;
        for (const [saveKey, pending] of pendingProgressionCommandsRef.current) {
          if (pending.projectId === projectId) pendingProgressionCommandsRef.current.delete(saveKey);
        }
        if (stored) {
          const locked = { ...stored.pending, receiptOnly: true };
          if (!await commandCoordinator.save(stored.saveKey, locked)) {
            throw new Error("the recovered command could not be locked durably");
          }
          if (!active || recoveryGenerationRef.current !== generation) return;
          pendingProgressionCommandsRef.current.set(stored.saveKey, locked);
          setReceiptOnlySaveKey(stored.saveKey);
          setMutationError("This project has an unresolved Progressions command. Only its durable receipt may be checked; the exact command will not be resent.");
        }
        setRecoveryReady(true);
      } catch (failure) {
        if (!active || recoveryGenerationRef.current !== generation) return;
        setRecoveryReady(false);
        setRecoveryError(`Progressions recovery storage could not be checked — ${failure instanceof Error ? failure.message : String(failure)}. No write will be sent until recovery succeeds.`);
      }
    })();
    return () => { active = false; };
  }, [commandCoordinator, platform.isDesktop, platform.progressionCommandStorage, projectId, recoveryAttempt]);

  const tracks = useMemo(() => [...(snapshot?.tracks ?? [])]
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id), [snapshot]);
  const filteredTracks = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return tracks.filter((track) => (
      (kindFilter === "all" || track.kind === kindFilter)
      && (!needle || [track.title, track.description, track.primary_psyke_entry_name, track.secondary_psyke_entry_name]
        .some((value) => value.toLowerCase().includes(needle)))
    ));
  }, [kindFilter, query, tracks]);
  const selectedTrack = filteredTracks.find((track) => track.id === selectedTrackId)
    ?? filteredTracks[0]
    ?? null;

  useEffect(() => {
    if (selectedTrack && selectedTrack.id !== selectedTrackId) setSelectedTrackId(selectedTrack.id);
  }, [selectedTrack, selectedTrackId]);

  useEffect(() => () => {
    if (targetFrameRef.current != null) ownerWindow?.cancelAnimationFrame(targetFrameRef.current);
  }, [ownerWindow]);

  useEffect(() => {
    if (!progressionTarget) {
      consumedTargetRef.current = "";
      targetRequestRef.current = null;
      return;
    }
    const token = `${projectId ?? ""}:${progressionTarget.trackId ?? ""}:${progressionTarget.beatId ?? ""}`;
    if (consumedTargetRef.current === token || projectId == null) return;
    if (targetRequestRef.current?.token !== token) {
      // The already-rendered snapshot may predate the navigation request or the
      // host's pending-save barrier.  Resolve (or declare stale) only from a
      // successful read generation started after this exact target arrived.
      setCommandSnapshot(null);
      targetRequestRef.current = { token, requestId: refetch() };
      return;
    }
    if (lastSuccessfulRequest < targetRequestRef.current.requestId) return;
    if (!data || data.project_id !== projectId) return;
    const authoritativeTracks = [...data.tracks]
      .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id);
    const resolved = resolveProgressionNavigationTarget(authoritativeTracks, progressionTarget);
    if (!resolved) {
      consumedTargetRef.current = token;
      setFocusedBeatId(null);
      setTargetNotice("That Progressions evidence is no longer present in the current project.");
      clearProgressionTargetRef.current();
      return;
    }

    setKindFilter("all");
    setQuery("");
    setSelectedTrackId(resolved.track.id);
    setFocusedBeatId(resolved.beat?.id ?? null);
    setSelection({
      section: "Progressions",
      nodeId: resolved.beat?.id ?? resolved.track.id,
      sceneId: resolved.beat?.scene_id ?? null,
      text: resolved.beat?.text ?? `${resolved.track.title}\n${resolved.track.description}`.trim(),
    });
    setTargetNotice(resolved.beat
      ? `Opened traceable evidence in “${resolved.track.title}”.`
      : `Opened progression “${resolved.track.title}”.`);

    if (!ownerWindow) {
      consumedTargetRef.current = token;
      clearProgressionTargetRef.current();
      return;
    }
    if (targetFrameRef.current != null) ownerWindow.cancelAnimationFrame(targetFrameRef.current);
    let attempts = 60;
    const focusExactTarget = () => {
      if (attempts <= 0) {
        targetFrameRef.current = null;
        consumedTargetRef.current = token;
        setTargetNotice("Progressions opened the evidence, but its row could not retain keyboard focus.");
        clearProgressionTargetRef.current();
        return;
      }
      attempts -= 1;
      targetFrameRef.current = ownerWindow.requestAnimationFrame(() => {
        targetFrameRef.current = null;
        const node = resolved.beat
          ? beatTargetRefs.current.get(resolved.beat.id)
          : trackTargetRefs.current.get(resolved.track.id);
        if (!node) {
          focusExactTarget();
          return;
        }
        node.scrollIntoView?.({ block: "center", behavior: "smooth" });
        node.focus?.({ preventScroll: true });
        consumedTargetRef.current = token;
        clearProgressionTargetRef.current();
      });
    };
    focusExactTarget();
    return () => {
      if (targetFrameRef.current != null) ownerWindow.cancelAnimationFrame(targetFrameRef.current);
      targetFrameRef.current = null;
    };
  }, [data, lastSuccessfulRequest, ownerWindow, progressionTarget, projectId, refetch, setSelection]);

  const replacePending = useCallback(async (
    saveKey: string,
    pending: PendingProgressionCommand | null,
  ): Promise<boolean> => {
    const previous = pendingProgressionCommandsRef.current.get(saveKey);
    if (pending) {
      const durablyStored = await commandCoordinatorRef.current.save(saveKey, pending);
      if (!durablyStored) return false;
      pendingProgressionCommandsRef.current.set(saveKey, pending);
    } else {
      const storedProjectId = previous?.projectId ?? projectIdRef.current;
      if (storedProjectId != null) {
        const durablyRemoved = await commandCoordinatorRef.current.remove(storedProjectId, saveKey);
        if (!durablyRemoved && previous) return false;
      }
      pendingProgressionCommandsRef.current.delete(saveKey);
    }
    const ownerProjectId = projectIdRef.current;
    const active = ownerProjectId == null
      ? undefined
      : [...pendingProgressionCommandsRef.current.entries()]
        .find(([, candidate]) => candidate.projectId === ownerProjectId && candidate.receiptOnly);
    setReceiptOnlySaveKey(active?.[0] ?? null);
    return true;
  }, []);

  const checkSavedReceipt = useCallback(async (
    pending: PendingProgressionCommand,
  ): Promise<ProgressionSnapshotDTO | null> => {
    try {
      await api.getProgressionCommandReceipt(pending.projectId, pending.key, pending.command);
      api.invalidatePendingReads?.();
      return await api.getProgressions(pending.projectId);
    } catch (receiptFailure) {
      if (isReceiptMiss(receiptFailure)) return null;
      throw receiptFailure;
    }
  }, [api]);

  const lockReceiptOnly = useCallback(async (
    saveKey: string,
    pending: PendingProgressionCommand,
    reason: string,
  ): Promise<never> => {
    const locked = { ...pending, receiptOnly: true };
    if (!await replacePending(saveKey, locked)) {
      // A full restart always treats any loaded command as receipt-only. Keep
      // the current renderer equally conservative even when the disk update
      // itself failed after an ambiguous transport result.
      pendingProgressionCommandsRef.current.set(saveKey, locked);
      if (projectIdRef.current === locked.projectId) setReceiptOnlySaveKey(saveKey);
    }
    throw new ProgressionReceiptOnlyError(reason);
  }, [replacePending]);

  const resendPending = useCallback(async (
    saveKey: string,
    pending: PendingProgressionCommand,
  ): Promise<ProgressionSnapshotDTO> => {
    const retry = { ...pending, resendAttempted: true };
    if (!await replacePending(saveKey, retry)) {
      return await lockReceiptOnly(
        saveKey,
        retry,
        "The exact resend could not be saved durably, so it was not sent. This command is now receipt-only.",
      );
    }
    try {
      return (await api.executeProgressionCommand(
        retry.projectId,
        retry.command,
        retry.key,
      )).progressions;
    } catch (resendFailure) {
      if (!isAmbiguousFailure(resendFailure)) throw resendFailure;
      try {
        const recovered = await checkSavedReceipt(retry);
        if (recovered) return recovered;
        return await lockReceiptOnly(
          saveKey,
          retry,
          "No durable receipt is available yet after the one allowed same-key resend. This command is now receipt-only and will not be sent again.",
        );
      } catch (receiptFailure) {
        if (receiptFailure instanceof ProgressionReceiptOnlyError) throw receiptFailure;
        return await lockReceiptOnly(
          saveKey,
          retry,
          `The resend outcome could not be verified — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. This command is now receipt-only and will not be sent again.`,
        );
      }
    }
  }, [api, checkSavedReceipt, lockReceiptOnly, replacePending]);

  const deliverSaved = useCallback(async (
    saveKey: string,
    pending: PendingProgressionCommand,
  ): Promise<ProgressionSnapshotDTO> => {
    try {
      return (await api.executeProgressionCommand(
        pending.projectId,
        pending.command,
        pending.key,
      )).progressions;
    } catch (firstFailure) {
      if (!isAmbiguousFailure(firstFailure)) throw firstFailure;
      let recovered: ProgressionSnapshotDTO | null;
      try {
        recovered = await checkSavedReceipt(pending);
      } catch (receiptFailure) {
        return await lockReceiptOnly(
          saveKey,
          pending,
          `The write outcome could not be verified — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. This command is now receipt-only and will not be resent.`,
        );
      }
      if (recovered) return recovered;
      return resendPending(saveKey, pending);
    }
  }, [api, checkSavedReceipt, lockReceiptOnly, resendPending]);

  const resumePending = useCallback(async (
    saveKey: string,
    pending: PendingProgressionCommand,
  ): Promise<ProgressionSnapshotDTO> => {
    // Every later Save/flusher checks the durable receipt before doing anything.
    // Once the sole resend was attempted, even a receipt miss remains
    // receipt-only: a late commit can never be followed by a fresh create key.
    let recovered: ProgressionSnapshotDTO | null;
    try {
      recovered = await checkSavedReceipt(pending);
    } catch (receiptFailure) {
      return await lockReceiptOnly(
        saveKey,
        pending,
        `The receipt check failed — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. The exact command remains receipt-only.`,
      );
    }
    if (recovered) return recovered;
    if (pending.receiptOnly || pending.resendAttempted) {
      return await lockReceiptOnly(
        saveKey,
        pending,
        "No durable receipt is available yet. The exact command remains receipt-only and will not be resent.",
      );
    }
    return resendPending(saveKey, pending);
  }, [checkSavedReceipt, lockReceiptOnly, resendPending]);

  const runCommand = useCallback(async (
    name: string,
    build: (latest: ProgressionSnapshotDTO) => ProgressionCommandDTO,
    saveKey?: string,
  ): Promise<boolean> => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null) return false;
    if (!recoveryReady) {
      setMutationError("Progressions recovery storage is still being checked. No write was sent.");
      return false;
    }
    const commandSaveKey = saveKey ?? `progression-action:${ownerProjectId}:${name}`;
    if (busy || inFlightProgressionCommandsRef.current.size > 0) return false;
    const unresolved = [...pendingProgressionCommandsRef.current.entries()]
      .find(([, candidate]) => candidate.projectId === ownerProjectId);
    if (unresolved && unresolved[0] !== commandSaveKey) {
      setMutationError("Resolve or explicitly abandon the pending Progressions command before starting another change.");
      setReceiptOnlySaveKey(unresolved[0]);
      return false;
    }
    inFlightProgressionCommandsRef.current.add(commandSaveKey);
    setBusy(name);
    setMutationError("");
    setStatus("Saving Progressions…");
    try {
      const pending = pendingProgressionCommandsRef.current.get(commandSaveKey);
      let write: Promise<ProgressionSnapshotDTO>;
      if (pending?.projectId === ownerProjectId) {
        write = resumePending(commandSaveKey, pending);
      } else {
        api.invalidatePendingReads?.();
        const latest = await api.getProgressions(ownerProjectId);
        if (latest.project_id !== ownerProjectId) throw new Error("The latest Progressions snapshot belongs to another project.");
        const command = build(latest);
        const key = idempotencyKey();
        const nextPending: PendingProgressionCommand = {
          projectId: ownerProjectId,
          command: structuredClone(command),
          key,
          resendAttempted: false,
          receiptOnly: false,
        };
        if (!await replacePending(commandSaveKey, nextPending)) {
          throw new Error("The exact recovery command could not be saved durably, so no Progressions request was sent.");
        }
        write = deliverSaved(commandSaveKey, nextPending);
      }
      const next = await trackProjectWrite(write, { saveKey: commandSaveKey });
      const pendingAfterWrite = pendingProgressionCommandsRef.current.get(commandSaveKey);
      if (!await replacePending(commandSaveKey, null) && pendingAfterWrite) {
        const locked = { ...pendingAfterWrite, receiptOnly: true };
        if (!await replacePending(commandSaveKey, locked)) {
          pendingProgressionCommandsRef.current.set(commandSaveKey, locked);
          if (projectIdRef.current === locked.projectId) setReceiptOnlySaveKey(commandSaveKey);
        }
      }
      if (projectIdRef.current === ownerProjectId) {
        setCommandSnapshot({ value: next, authoritativeRequestId: refetch() });
        setStatus("Progressions saved.");
      }
      return true;
    } catch (failure) {
      const pendingAfterFailure = pendingProgressionCommandsRef.current.get(commandSaveKey);
      if (
        !isAmbiguousFailure(failure)
        && !pendingAfterFailure?.receiptOnly
      ) {
        await replacePending(commandSaveKey, null);
      }
      if (projectIdRef.current === ownerProjectId) {
        const conflict = failure instanceof ApiRequestError && failure.status === 409;
        setMutationError(conflict
          ? "Progressions changed elsewhere. Your draft was kept, but it will not be rebased over newer work; review the refreshed row and reopen the editor to apply a new edit."
          : `Couldn't save Progressions — ${failure instanceof Error ? failure.message : String(failure)}`);
        setStatus("");
        refetch();
      }
      return false;
    } finally {
      inFlightProgressionCommandsRef.current.delete(commandSaveKey);
      if (projectIdRef.current === ownerProjectId) setBusy("");
    }
  }, [api, busy, deliverSaved, recoveryReady, refetch, replacePending, resumePending]);

  const checkPendingReceiptOnly = useCallback(async (): Promise<boolean> => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null) return true;
    const entry = [...pendingProgressionCommandsRef.current.entries()]
      .find(([, candidate]) => candidate.projectId === ownerProjectId);
    if (!entry) return true;
    const [saveKey, pending] = entry;
    if (inFlightProgressionCommandsRef.current.has(saveKey)) return false;
    inFlightProgressionCommandsRef.current.add(saveKey);
    setBusy("check-receipt");
    setMutationError("");
    setStatus("Checking the durable Progressions receipt…");
    try {
      const recovery = (async () => {
        const recovered = await checkSavedReceipt(pending);
        if (!recovered) {
          throw new ProgressionReceiptOnlyError(
            "No durable receipt is available yet. The exact command remains receipt-only and will not be resent.",
          );
        }
        return recovered;
      })();
      const next = await trackProjectWrite(recovery, { saveKey });
      if (!await replacePending(saveKey, null)) {
        throw new Error("the recovered command could not be cleared from durable storage");
      }
      const currentDraft = draftRef.current;
      if (currentDraft && draftKey(ownerProjectId, currentDraft) === saveKey) {
        draftRef.current = null;
        setDraft(null);
      }
      if (projectIdRef.current === ownerProjectId) {
        setCommandSnapshot({ value: next, authoritativeRequestId: refetch() });
        setMutationError("");
        setStatus("Recovered the committed Progressions change from its durable receipt.");
      }
      return true;
    } catch (failure) {
      await replacePending(saveKey, { ...pending, receiptOnly: true });
      if (projectIdRef.current === ownerProjectId) {
        setStatus("");
        setMutationError(failure instanceof ProgressionReceiptOnlyError
          ? failure.message
          : `The receipt check failed — ${failure instanceof Error ? failure.message : String(failure)}. The exact command remains receipt-only.`);
      }
      return false;
    } finally {
      inFlightProgressionCommandsRef.current.delete(saveKey);
      if (projectIdRef.current === ownerProjectId) setBusy("");
    }
  }, [checkSavedReceipt, refetch, replacePending]);

  const abandonPendingCommand = useCallback(async () => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null) return;
    const entry = [...pendingProgressionCommandsRef.current.entries()]
      .find(([, candidate]) => candidate.projectId === ownerProjectId);
    if (!entry) return;
    const [saveKey] = entry;
    if (!await replacePending(saveKey, null)) {
      setMutationError("The unresolved command could not be abandoned because durable recovery storage did not accept the removal.");
      return;
    }
    discardProjectSavePending(saveKey);
    const currentDraft = draftRef.current;
    if (currentDraft && draftKey(ownerProjectId, currentDraft) === saveKey) {
      draftRef.current = null;
      setDraft(null);
    }
    setStatus("");
    setMutationError("The unresolved command was abandoned locally. Refresh Progressions before repeating the action; a late server commit may still appear.");
    refetch();
  }, [refetch, replacePending]);

  const closeDraft = useCallback(async (abandon = false) => {
    const current = draftRef.current;
    const ownerProjectId = projectIdRef.current;
    if (abandon && current?.dirty && ownerProjectId != null) {
      const saveKey = draftKey(ownerProjectId, current);
      if (!await replacePending(saveKey, null)) {
        setMutationError("The draft cannot be closed because its durable recovery record could not be cleared.");
        return;
      }
      discardProjectSavePending(saveKey);
    }
    draftRef.current = null;
    setDraft(null);
  }, [replacePending]);

  const saveDraft = useCallback(async (): Promise<boolean> => {
    const current = draftRef.current;
    const ownerProjectId = projectIdRef.current;
    if (!current || !current.dirty) return true;
    if (ownerProjectId == null) return false;
    const saveKey = draftKey(ownerProjectId, current);
    if (current.type === "track") {
      if (!current.title.trim()) {
        setMutationError("A progression track needs a title.");
        return false;
      }
      const primary = psykeEntries.find((entry) => entry.id === current.primaryPsykeEntryId);
      const secondary = psykeEntries.find((entry) => entry.id === current.secondaryPsykeEntryId);
      const subjectError = current.trackKind === "character"
        ? primary?.type !== "character" || secondary != null
          ? "A character progression needs exactly one Character as its primary subject."
          : ""
        : current.trackKind === "theme"
          ? primary?.type !== "theme" || secondary != null
            ? "A theme progression needs exactly one Theme as its primary subject."
            : ""
          : current.trackKind === "world"
            ? !primary || !["place", "object", "lore"].includes(primary.type) || secondary != null
              ? "A world progression needs exactly one Place, Object, or Lore subject."
              : ""
            : current.trackKind === "relationship"
              ? !primary || !secondary || primary.id === secondary.id
                ? "A relationship progression needs two different PSYKE subjects."
                : ""
              : "";
      if (subjectError) {
        setMutationError(subjectError);
        return false;
      }
      if (current.mode === "update" && current.sourceRevision == null) {
        setMutationError("This edit has no authoritative source revision. Close it and reopen the track before saving.");
        return false;
      }
      const primaryId = current.trackKind === "story" || current.trackKind === "custom"
        ? null
        : primary?.id ?? null;
      const secondaryId = current.trackKind === "relationship" ? secondary?.id ?? null : null;
      const subjectPatch = current.mode === "update"
        && !current.legacyCompatibilityLocked
        && (
          current.trackKind !== current.originalTrackKind
          || primaryId !== current.originalPrimaryPsykeEntryId
          || secondaryId !== current.originalSecondaryPsykeEntryId
        )
        ? {
            track_kind: current.trackKind,
            primary_psyke_entry_id: primaryId,
            secondary_psyke_entry_id: secondaryId,
          }
        : {};
      const saved = await runCommand("track", (latest) => current.mode === "create" ? {
        kind: "create_track",
        expected_revision: latest.revision,
        track_kind: current.trackKind,
        title: current.title.trim(),
        description: current.description.trim(),
        color_label: current.colorLabel,
        primary_psyke_entry_id: primaryId,
        secondary_psyke_entry_id: secondaryId,
      } : {
        kind: "update_track",
        // Never silently rebase a stale full-field draft onto a newer snapshot.
        expected_revision: current.sourceRevision!,
        track_id: current.trackId!,
        title: current.title.trim(),
        description: current.description.trim(),
        color_label: current.colorLabel,
        ...subjectPatch,
      }, saveKey);
      if (saved) await closeDraft();
      return saved;
    }
    const textChanged = current.mode === "create" || current.text !== current.originalText;
    if (textChanged && !current.text.trim()) {
      setMutationError("A progression beat needs text.");
      return false;
    }
    if (current.anchorKind === "scene" && current.sceneId == null) {
      setMutationError("Choose a scene for this scene anchor.");
      return false;
    }
    if (current.anchorKind === "document_block" && !current.anchorRef.trim()) {
      setMutationError("A document-block anchor needs a stable reference.");
      return false;
    }
    if (current.mode === "update" && current.sourceRevision == null) {
      setMutationError("This edit has no authoritative source revision. Close it and reopen the beat before saving.");
      return false;
    }
    const anchor = current.anchorKind === "scene"
      ? { anchor_kind: current.anchorKind, scene_id: current.sceneId, anchor_ref: null, anchor_label: current.anchorLabel.trim() }
      : current.anchorKind === "document_block"
        ? { anchor_kind: current.anchorKind, scene_id: null, anchor_ref: current.anchorRef.trim(), anchor_label: current.anchorLabel.trim() }
        : { anchor_kind: current.anchorKind, scene_id: null, anchor_ref: null, anchor_label: "" };
    const saved = await runCommand("beat", (latest) => current.mode === "create" ? {
      kind: "create_beat",
      expected_revision: latest.revision,
      track_id: current.trackId,
      text: current.text.trim(),
      ...anchor,
    } : {
      kind: "update_beat",
      // Anchor fields are a full replacement too, so retain the opening revision.
      expected_revision: current.sourceRevision!,
      beat_id: current.beatId!,
      ...(textChanged ? { text: current.text.trim() } : {}),
      ...anchor,
    }, saveKey);
    if (saved) await closeDraft();
    return saved;
  }, [closeDraft, psykeEntries, runCommand]);
  saveDraftRef.current = saveDraft;

  flushProgressionsRef.current = async () => {
    const ownerProjectId = projectIdRef.current;
    const unresolved = ownerProjectId == null
      ? undefined
      : [...pendingProgressionCommandsRef.current.values()]
        .find((candidate) => candidate.projectId === ownerProjectId);
    return unresolved ? checkPendingReceiptOnly() : saveDraftRef.current();
  };

  useEffect(() => registerProjectFlusher(() => flushProgressionsRef.current()), []);

  const updateDraft = useCallback((patch: Partial<EditorDraft>) => {
    const current = draftRef.current;
    const ownerProjectId = projectIdRef.current;
    if (!current || ownerProjectId == null) return;
    if (pendingProgressionCommandsRef.current.has(draftKey(ownerProjectId, current))) {
      setMutationError("Resolve the pending Progressions save with Save, or Cancel it, before editing this draft.");
      return;
    }
    const next = { ...current, ...patch, dirty: true } as EditorDraft;
    draftRef.current = next;
    setDraft(next);
    markProjectSavePending(draftKey(ownerProjectId, next));
  }, []);

  const openNewTrack = () => {
    const next: TrackDraft = {
      type: "track", mode: "create", trackId: null, trackKind: "story",
      title: "", description: "", colorLabel: "", primaryPsykeEntryId: null,
      secondaryPsykeEntryId: null, originalTrackKind: null,
      originalPrimaryPsykeEntryId: null, originalSecondaryPsykeEntryId: null,
      legacyCompatibilityLocked: false, sourceRevision: null, dirty: false,
    };
    draftRef.current = next;
    setDraft(next);
  };
  const openTrack = (track: ProgressionTrackDTO) => {
    const legacyCompatibilityLocked = track.legacy_compatibility;
    const next: TrackDraft = {
      type: "track", mode: "update", trackId: track.id, trackKind: track.kind,
      title: track.title, description: track.description, colorLabel: track.color_label,
      primaryPsykeEntryId: track.primary_psyke_entry_id,
      secondaryPsykeEntryId: track.secondary_psyke_entry_id,
      originalTrackKind: track.kind,
      originalPrimaryPsykeEntryId: track.primary_psyke_entry_id,
      originalSecondaryPsykeEntryId: track.secondary_psyke_entry_id,
      legacyCompatibilityLocked,
      sourceRevision: snapshot?.revision ?? null,
      dirty: false,
    };
    draftRef.current = next;
    setDraft(next);
  };
  const openNewBeat = (trackId: number) => {
    const next: BeatDraft = {
      type: "beat", mode: "create", trackId, beatId: null, text: "",
      anchorKind: "unanchored", sceneId: null, anchorRef: "", anchorLabel: "",
      originalText: null, sourceRevision: null, dirty: false,
    };
    draftRef.current = next;
    setDraft(next);
  };

  const removeTrack = async (trackId: number) => {
    if (!ownerWindow?.confirm("Delete this progression track and every beat in it?")) return;
    const ok = await runCommand("delete-track", (latest) => ({
      kind: "delete_track", expected_revision: latest.revision, track_id: trackId,
    }));
    if (ok) setSelectedTrackId(null);
  };
  const removeBeat = async (beatId: number) => {
    if (!ownerWindow?.confirm("Delete this progression beat?")) return;
    await runCommand("delete-beat", (latest) => ({
      kind: "delete_beat", expected_revision: latest.revision, beat_id: beatId,
    }));
  };
  const reorderTracks = async (trackId: number, delta: -1 | 1) => {
    await runCommand("reorder-tracks", (latest) => {
      const ids = [...latest.tracks]
        .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
        .map((track) => track.id);
      const from = ids.indexOf(trackId);
      const to = from + delta;
      if (from < 0) throw new Error("That progression track no longer exists. Refresh and try again.");
      if (to < 0 || to >= ids.length) throw new Error("That progression track is already at the requested edge.");
      [ids[from], ids[to]] = [ids[to]!, ids[from]!];
      return { kind: "reorder_tracks", expected_revision: latest.revision, track_ids: ids };
    });
  };
  const reorderBeats = async (track: ProgressionTrackDTO, beatId: number, delta: -1 | 1) => {
    await runCommand("reorder-beats", (latest) => {
      const latestTrack = latest.tracks.find((candidate) => candidate.id === track.id);
      if (!latestTrack) throw new Error("That progression track no longer exists. Refresh and try again.");
      const ids = [...latestTrack.beats]
        .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id)
        .map((beat) => beat.id);
      const from = ids.indexOf(beatId);
      const to = from + delta;
      if (from < 0) throw new Error("That progression beat no longer exists. Refresh and try again.");
      if (to < 0 || to >= ids.length) throw new Error("That progression beat is already at the requested edge.");
      [ids[from], ids[to]] = [ids[to]!, ids[from]!];
      return {
        kind: "reorder_beats", expected_revision: latest.revision,
        track_id: latestTrack.id, beat_ids: ids,
      };
    });
  };

  const trackDraft = draft?.type === "track" ? draft : null;
  const primarySubjectOptions = trackDraft == null
    ? []
    : trackDraft.trackKind === "character"
      ? psykeEntries.filter((entry) => entry.type === "character")
      : trackDraft.trackKind === "theme"
        ? psykeEntries.filter((entry) => entry.type === "theme")
        : trackDraft.trackKind === "world"
          ? psykeEntries.filter((entry) => ["place", "object", "lore"].includes(entry.type))
          : trackDraft.trackKind === "relationship"
            ? psykeEntries
            : [];
  const secondarySubjectOptions = trackDraft?.trackKind === "relationship"
    ? psykeEntries.filter((entry) => entry.id !== trackDraft.primaryPsykeEntryId)
    : [];
  const commandsBlocked = Boolean(!recoveryReady || busy || draft || receiptOnlySaveKey);

  return (
    <PanelShell {...props}>
      <section data-screen-label="BIBLE · PROGRESSIONS" aria-label="Story bible progressions" style={root}>
        <header style={{ padding: "10px 12px", borderBottom: "1px solid var(--line)", display: "flex", gap: 12, alignItems: "center" }}>
          <div style={{ flex: 1 }}>
            <div style={{ color: "var(--accent)", fontSize: 9, letterSpacing: ".16em" }}>BIBLE · PROGRESSIONS</div>
            <div style={{ color: "var(--txt3)", fontSize: 8, marginTop: 3 }}>Story, character, relationship, theme and world arcs on one traceable axis.</div>
          </div>
          {snapshot && <div aria-label="Progressions coverage" style={{ textAlign: "right", fontSize: 9, color: "var(--txt2)" }}>
            <strong style={{ color: "var(--accent)" }}>{snapshot.summary.coverage_percent}%</strong> ANCHOR COVERAGE<br />
            {snapshot.summary.total_tracks} TRACKS · {snapshot.summary.total_beats} BEATS
          </div>}
          <button type="button" style={{ ...button, color: "var(--accent)", borderColor: "var(--accent)" }} onClick={openNewTrack} disabled={commandsBlocked}>+ TRACK</button>
        </header>

        {!recoveryReady && !recoveryError && <div role="status" style={{ padding: "6px 12px", fontSize: 9, color: "var(--txt2)", borderBottom: "1px solid var(--line2)" }}>Checking durable Progressions recovery…</div>}
        {recoveryError && <div role="alert" style={{ padding: "6px 12px", fontSize: 9, color: "var(--crimson)", borderBottom: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 8 }}><span style={{ flex: 1 }}>{recoveryError}</span><button type="button" style={button} onClick={() => setRecoveryAttempt((attempt) => attempt + 1)}>RETRY RECOVERY</button></div>}
        {(status || mutationError) && <div role={mutationError ? "alert" : "status"} style={{ padding: "6px 12px", fontSize: 9, color: mutationError ? "var(--crimson)" : "var(--green)", borderBottom: "1px solid var(--line2)", display: "flex", alignItems: "center", gap: 8 }}><span style={{ flex: 1 }}>{mutationError || status}</span>{receiptOnlySaveKey && <><button type="button" style={button} disabled={!!busy} onClick={() => void checkPendingReceiptOnly()}>CHECK RECEIPT</button><button type="button" style={{ ...button, color: "var(--crimson)" }} disabled={!!busy} onClick={() => void abandonPendingCommand()}>ABANDON</button></>}</div>}
        {targetNotice && <div role="status" style={{ padding: "5px 12px", fontSize: 8.5, color: "var(--accent)", borderBottom: "1px solid var(--line2)" }}>{targetNotice}</div>}
        {loading && !snapshot ? <div style={{ padding: 24, color: "var(--txt3)" }}>Loading Progressions…</div>
          : error && !snapshot ? <div role="alert" style={{ padding: 24, color: "var(--crimson)" }}>{error}</div>
            : <div style={{ flex: 1, minHeight: 0, display: "grid", gridTemplateColumns: "minmax(210px,28%) minmax(0,1fr)" }}>
              <aside style={{ borderRight: "1px solid var(--line)", overflow: "auto", padding: 9 }} aria-label="Progression tracks">
                <input aria-label="Filter progression tracks" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter tracks…" style={input} />
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "7px 0 9px" }}>
                  {["all", ...KINDS].map((kind) => <button key={kind} type="button" aria-pressed={kindFilter === kind} onClick={() => setKindFilter(kind as ProgressionKind | "all")} style={{ ...button, padding: "3px 5px", color: kindFilter === kind ? "var(--accent)" : "var(--txt3)" }}>{kind}</button>)}
                </div>
                {filteredTracks.map((track) => <button key={track.id} type="button" ref={(node) => { if (node) trackTargetRefs.current.set(track.id, node); else trackTargetRefs.current.delete(track.id); }} data-progression-track-id={track.id} aria-label={`Open progression track ${track.title}`} onClick={() => { setFocusedBeatId(null); setTargetNotice(""); setSelectedTrackId(track.id); setSelection({ section: "Progressions", nodeId: track.id, sceneId: null, text: `${track.title}\n${track.description}`.trim() }); }} style={{ width: "100%", textAlign: "left", border: selectedTrack?.id === track.id ? "1px solid var(--accent)" : "1px solid var(--line2)", background: selectedTrack?.id === track.id ? "var(--tint2)" : "transparent", color: "var(--txt)", padding: 8, marginBottom: 6, cursor: "pointer", font: "inherit" }}>
                  <div style={{ fontSize: 10 }}><span style={{ color: "var(--txt3)", textTransform: "uppercase", fontSize: 7 }}>{track.kind}</span> {track.title}</div>
                  <div style={{ height: 3, background: "var(--line2)", marginTop: 6 }}><div style={{ width: `${track.coverage.coverage_percent}%`, height: "100%", background: coverageColor(track.coverage.status) }} /></div>
                  <div style={{ marginTop: 4, color: "var(--txt3)", fontSize: 8 }}>{track.beats.length} beats · {track.coverage.status}</div>
                </button>)}
                {!filteredTracks.length && <div style={{ padding: 14, color: "var(--txt3)", fontSize: 9 }}>No tracks match this filter.</div>}
              </aside>

              <main style={{ minWidth: 0, overflow: "auto", padding: 12 }}>
                {selectedTrack ? <>
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start", borderBottom: "1px solid var(--line2)", paddingBottom: 10 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ color: "var(--txt3)", textTransform: "uppercase", fontSize: 8, letterSpacing: ".12em" }}>{selectedTrack.kind} · {selectedTrack.coverage.coverage_percent}% anchor coverage</div>
                      <h2 style={{ margin: "4px 0", fontSize: 16, color: "var(--txt)" }}>{selectedTrack.title}</h2>
                      {selectedTrack.description && <p style={{ margin: 0, color: "var(--txt2)", fontSize: 10 }}>{selectedTrack.description}</p>}
                      {(selectedTrack.primary_psyke_entry_id || selectedTrack.secondary_psyke_entry_id) && <div style={{ display: "flex", gap: 6, marginTop: 7 }}>
                        {selectedTrack.primary_psyke_entry_id && <button type="button" style={button} onClick={() => navigate("PSYKE", { psykeEntryId: selectedTrack.primary_psyke_entry_id! })}>◆ {selectedTrack.primary_psyke_entry_name || `PSYKE #${selectedTrack.primary_psyke_entry_id}`}</button>}
                        {selectedTrack.secondary_psyke_entry_id && <button type="button" style={button} onClick={() => navigate("PSYKE", { psykeEntryId: selectedTrack.secondary_psyke_entry_id! })}>◆ {selectedTrack.secondary_psyke_entry_name || `PSYKE #${selectedTrack.secondary_psyke_entry_id}`}</button>}
                      </div>}
                    </div>
                    <button type="button" style={button} disabled={commandsBlocked || selectedTrack.sort_order <= 0} onClick={() => void reorderTracks(selectedTrack.id, -1)} aria-label="Move track earlier">↑</button>
                    <button type="button" style={button} disabled={commandsBlocked || selectedTrack.sort_order >= tracks.length - 1} onClick={() => void reorderTracks(selectedTrack.id, 1)} aria-label="Move track later">↓</button>
                    <button type="button" style={button} disabled={commandsBlocked} onClick={() => openTrack(selectedTrack)}>EDIT</button>
                    <button type="button" style={{ ...button, color: "var(--crimson)" }} disabled={commandsBlocked} onClick={() => void removeTrack(selectedTrack.id)}>DELETE</button>
                  </div>
                  <div aria-label="Scene axis" style={{ display: "flex", gap: 5, overflow: "auto", padding: "9px 0", borderBottom: "1px solid var(--line2)" }}>
                    <span style={{ flex: "none", color: "var(--txt3)", fontSize: 8, padding: "4px 3px" }}>SCENE AXIS</span>
                    {[...scenes].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id).map((scene) => {
                      const count = selectedTrack.beats.filter((beat) => beat.scene_id === scene.id).length;
                      return <button key={scene.id} type="button" onClick={() => navigate("Manuscript", { sceneId: scene.id })} title="Open scene in Manuscript" style={{ ...button, flex: "none", color: count ? "var(--accent)" : "var(--txt3)", borderColor: count ? "var(--accent)" : "var(--line2)" }}>{scene.title || `Scene ${scene.id}`}{count ? ` · ${count}` : ""}</button>;
                    })}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0" }}>
                    <strong style={{ flex: 1, fontSize: 9, letterSpacing: ".12em", color: "var(--txt2)" }}>PROGRESSION BEATS</strong>
                    <span style={{ color: selectedTrack.coverage.out_of_order_beat_ids.length ? "var(--amber)" : "var(--txt3)", fontSize: 8 }}>{selectedTrack.coverage.out_of_order_beat_ids.length ? `${selectedTrack.coverage.out_of_order_beat_ids.length} OUT OF ORDER` : "ORDER CLEAN"}</span>
                    <button type="button" style={{ ...button, color: "var(--accent)" }} disabled={commandsBlocked} onClick={() => openNewBeat(selectedTrack.id)}>+ BEAT</button>
                  </div>
                  <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
                    {[...selectedTrack.beats].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id).map((beat, index, ordered) => <li key={beat.id} style={{ display: "grid", gridTemplateColumns: "28px minmax(0,1fr) auto", gap: 8, alignItems: "start", padding: "8px 0", borderTop: "1px solid var(--line2)" }}>
                      <span style={{ color: "var(--txt3)", fontSize: 9, paddingTop: 3 }}>{index + 1}</span>
                      <button type="button" ref={(node) => { if (node) beatTargetRefs.current.set(beat.id, node); else beatTargetRefs.current.delete(beat.id); }} data-progression-beat-id={beat.id} aria-label={`Open progression beat ${index + 1}: ${beat.text}`} onClick={() => { setFocusedBeatId(beat.id); setTargetNotice(""); setSelection({ section: "Progressions", nodeId: beat.id, sceneId: beat.scene_id, text: beat.text }); }} style={{ textAlign: "left", border: focusedBeatId === beat.id ? "1px solid var(--accent)" : "1px solid transparent", background: focusedBeatId === beat.id ? "var(--tint2)" : "transparent", color: "var(--txt)", cursor: "pointer", padding: 2, font: "inherit" }}>
                        <span style={{ display: "block", fontSize: 11 }}>{beat.text}</span>
                        <span style={{ display: "block", marginTop: 4, color: beat.anchor_kind === "unanchored" ? "var(--crimson)" : "var(--green)", fontSize: 8 }}>{beat.anchor_kind.replace("_", " ").toUpperCase()} · {anchorText(beat.anchor_kind, beat.scene_title, beat.anchor_label, beat.anchor_ref)}</span>
                      </button>
                      <div style={{ display: "flex", gap: 4 }}>
                        {beat.scene_id && <button type="button" style={button} onClick={() => navigate("Manuscript", { sceneId: beat.scene_id! })}>OPEN SCENE</button>}
                        <button type="button" style={button} disabled={commandsBlocked || index === 0} onClick={() => void reorderBeats(selectedTrack, beat.id, -1)} aria-label="Move beat earlier">↑</button>
                        <button type="button" style={button} disabled={commandsBlocked || index === ordered.length - 1} onClick={() => void reorderBeats(selectedTrack, beat.id, 1)} aria-label="Move beat later">↓</button>
                        <button type="button" style={button} disabled={commandsBlocked} onClick={() => { const next: BeatDraft = { type: "beat", mode: "update", trackId: selectedTrack.id, beatId: beat.id, text: beat.text, anchorKind: beat.anchor_kind, sceneId: beat.scene_id, anchorRef: beat.anchor_ref ?? "", anchorLabel: beat.anchor_label, originalText: beat.text, sourceRevision: snapshot?.revision ?? null, dirty: false }; draftRef.current = next; setDraft(next); }}>EDIT</button>
                        <button type="button" style={{ ...button, color: "var(--crimson)" }} disabled={commandsBlocked} onClick={() => void removeBeat(beat.id)}>DELETE</button>
                      </div>
                    </li>)}
                  </ol>
                  {!selectedTrack.beats.length && <div style={{ padding: 24, textAlign: "center", color: "var(--txt3)", fontSize: 10 }}>No beats yet. Add the first turning point in this progression.</div>}
                </> : <div style={{ padding: 28, textAlign: "center", color: "var(--txt3)" }}>Create a progression track to map an arc across the story.</div>}
              </main>
            </div>}

        {draft && <div role="dialog" aria-modal="true" aria-label={draft.type === "track" ? "Progression track editor" : "Progression beat editor"} style={{ position: "absolute", inset: "8% 10%", zIndex: 20, overflow: "auto", border: "1px solid var(--accent)", background: "var(--panel)", boxShadow: "0 20px 70px rgba(0,0,0,.75)", padding: 14 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}><strong style={{ flex: 1, color: "var(--accent)", letterSpacing: ".12em", fontSize: 10 }}>{draft.mode === "create" ? "NEW" : "EDIT"} {draft.type.toUpperCase()}</strong><button type="button" style={button} disabled={!!busy || !recoveryReady} onClick={() => void closeDraft(true)}>CANCEL</button><button type="button" style={{ ...button, color: "var(--accent)", borderColor: "var(--accent)" }} disabled={!!busy || !recoveryReady} onClick={() => void saveDraft()}>SAVE</button></div>
          {draft.type === "track" ? <div style={{ display: "grid", gap: 10 }}>
            <label style={label}>TITLE<input autoFocus style={input} value={draft.title} onChange={(event) => updateDraft({ title: event.target.value })} /></label>
            <label style={label}>KIND<select style={input} value={draft.trackKind} disabled={draft.legacyCompatibilityLocked} onChange={(event) => updateDraft({ trackKind: event.target.value as ProgressionKind, primaryPsykeEntryId: null, secondaryPsykeEntryId: null })}>{KINDS.map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select></label>
            {draft.legacyCompatibilityLocked && <div role="note" style={{ color: "var(--txt3)", fontSize: 9, lineHeight: 1.5 }}>This track preserves an older per-entry PSYKE progression. Its kind and subject stay linked; title, description and color remain editable here.</div>}
            <label style={label}>DESCRIPTION<textarea rows={4} style={input} value={draft.description} onChange={(event) => updateDraft({ description: event.target.value })} /></label>
            <label style={label}>COLOR<select style={input} value={draft.colorLabel} onChange={(event) => updateDraft({ colorLabel: event.target.value })}>{COLORS.map((color) => <option key={color || "auto"} value={color}>{color || "auto"}</option>)}</select></label>
            {draft.trackKind !== "story" && draft.trackKind !== "custom" && <label style={label}>{draft.trackKind === "relationship" ? "PRIMARY PSYKE SUBJECT" : "PSYKE SUBJECT"}<select style={input} disabled={draft.legacyCompatibilityLocked} value={draft.primaryPsykeEntryId ?? ""} onChange={(event) => updateDraft({ primaryPsykeEntryId: event.target.value ? Number(event.target.value) : null, secondaryPsykeEntryId: event.target.value === String(draft.secondaryPsykeEntryId) ? null : draft.secondaryPsykeEntryId })}><option value="">Choose subject…</option>{primarySubjectOptions.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {entry.type}</option>)}</select></label>}
            {draft.trackKind === "relationship" && <label style={label}>SECONDARY PSYKE SUBJECT<select style={input} disabled={draft.legacyCompatibilityLocked} value={draft.secondaryPsykeEntryId ?? ""} onChange={(event) => updateDraft({ secondaryPsykeEntryId: event.target.value ? Number(event.target.value) : null })}><option value="">Choose a different subject…</option>{secondarySubjectOptions.map((entry) => <option key={entry.id} value={entry.id}>{entry.name} · {entry.type}</option>)}</select></label>}
          </div> : <div style={{ display: "grid", gap: 10 }}>
            <label style={label}>BEAT<textarea autoFocus rows={5} style={input} value={draft.text} onChange={(event) => updateDraft({ text: event.target.value })} /></label>
            <label style={label}>ANCHOR<select style={input} value={draft.anchorKind} onChange={(event) => updateDraft({ anchorKind: event.target.value as ProgressionAnchorKind, sceneId: null, anchorRef: "", anchorLabel: "" })}><option value="unanchored">Unanchored</option><option value="scene">Scene</option><option value="document_block">Document block</option></select></label>
            {draft.anchorKind === "scene" && <label style={label}>SCENE<select style={input} value={draft.sceneId ?? ""} onChange={(event) => updateDraft({ sceneId: event.target.value ? Number(event.target.value) : null })}><option value="">Choose scene…</option>{[...scenes].sort((left, right) => left.sort_order - right.sort_order || left.id - right.id).map((scene) => <option key={scene.id} value={scene.id}>{scene.title || `Scene ${scene.id}`}</option>)}</select></label>}
            {draft.anchorKind === "document_block" && <><label style={label}>DOCUMENT REFERENCE<input style={input} value={draft.anchorRef} onChange={(event) => updateDraft({ anchorRef: event.target.value })} placeholder="Stable block id or reference" /></label><label style={label}>DISPLAY LABEL<input style={input} value={draft.anchorLabel} onChange={(event) => updateDraft({ anchorLabel: event.target.value })} placeholder="Optional readable label" /></label></>}
          </div>}
        </div>}
      </section>
    </PanelShell>
  );
}
