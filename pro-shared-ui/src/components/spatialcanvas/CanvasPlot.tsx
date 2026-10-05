import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import type {
  CanvasPlotFrameDTO,
  CanvasPlotNodeDTO,
  CanvasPlotSnapshotDTO,
} from "@logosforge/ui-contracts";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { ApiRequestError } from "../../adapters/httpApiClient";
import {
  discardProjectSavePending,
  flushPendingProjectSaves,
  markProjectSavePending,
  registerProjectFlusher,
  trackProjectOperation,
  trackProjectWrite,
  type ProjectFlusher,
} from "../../adapters/projectSaveCoordinator";
import { useCanvasPlot, useMountedRef, useSettings } from "../../hooks";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import {
  canvasContentBounds,
  canvasLinkGeometry,
  canvasWorldTransform,
  DEFAULT_CANVAS_VIEWPORT,
  fitCanvasViewport,
  moveCanvasRect,
  panCanvasViewport,
  parseCanvasViewport,
  resizeCanvasRect,
  zoomCanvasViewportAt,
  type CanvasRect,
  type CanvasSize,
  type CanvasViewport,
} from "./canvasPlotGeometry";
import {
  canvasPlotIntentCanRetry,
  describeCanvasPlotIntent,
  planCanvasPlotCommand,
  type CanvasPlotCommandIntent,
} from "./canvasPlotTransactions";

const VIEW_SETTING_KEY = "canvas_plot_view";
const DEFAULT_VIEW_SIZE: CanvasSize = { width: 1000, height: 700 };

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  minHeight: 320,
  background: "var(--panel2)",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const toolbarButton: CSSProperties = {
  border: "1px solid var(--line2)",
  background: "var(--raised)",
  color: "var(--txt2)",
  padding: "4px 7px",
  font: "inherit",
  fontSize: 8,
  letterSpacing: ".08em",
};

const field: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  border: "1px solid var(--line2)",
  background: "var(--panel2)",
  color: "var(--strong)",
  padding: "5px 6px",
  font: "inherit",
  fontSize: 9,
};

const COLORS = ["", "cyan", "green", "amber", "violet", "crimson", "pink", "blue", "red", "teal"];
const COLOR_HEX: Record<string, string> = {
  cyan: "#4cc2ff",
  green: "#62d99a",
  amber: "#ffb454",
  violet: "#b07cff",
  crimson: "#ff5c6c",
  pink: "#ff7ac6",
  blue: "#7aa2ff",
  red: "#ff5c6c",
  teal: "#45c7bb",
  gray: "#7a8694",
};

function colorValue(label: string, fallback = "var(--accent)"): string {
  const normalized = label.trim().toLocaleLowerCase();
  if (!normalized) return fallback;
  return COLOR_HEX[normalized] ?? label;
}

type Selection =
  | { kind: "node"; id: number }
  | { kind: "link"; id: number }
  | { kind: "frame"; id: number }
  | null;

type Gesture = {
  kind: "pan" | "move_node" | "resize_node" | "move_frame" | "resize_frame";
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startViewport: CanvasViewport;
  rect?: CanvasRect;
  id?: number;
};

interface EditDraft {
  title: string;
  body: string;
  colorLabel: string;
  groupLabel: string;
  label: string;
  linkType: string;
}

interface InspectorDraft {
  projectId: number;
  selection: Exclude<Selection, null>;
  baseline: EditDraft;
  value: EditDraft;
  generation: number;
  dirty: boolean;
}

const EMPTY_EDIT: EditDraft = {
  title: "",
  body: "",
  colorLabel: "",
  groupLabel: "",
  label: "",
  linkType: "",
};

const EDIT_KEYS = ["title", "body", "colorLabel", "groupLabel", "label", "linkType"] as const;

function selectionKey(selection: Selection): string {
  return selection ? `${selection.kind}:${selection.id}` : "";
}

function inspectorSaveKey(draft: Pick<InspectorDraft, "projectId" | "selection">): string {
  return `canvas-plot-inspector:${draft.projectId}:${selectionKey(draft.selection)}`;
}

function editsEqual(left: EditDraft, right: EditDraft): boolean {
  return EDIT_KEYS.every((key) => left[key] === right[key]);
}

function rebaseEdit(
  local: EditDraft,
  previousBaseline: EditDraft,
  authoritative: EditDraft,
): EditDraft {
  const rebased = { ...local };
  for (const key of EDIT_KEYS) {
    if (local[key] === previousBaseline[key]) rebased[key] = authoritative[key];
  }
  return rebased;
}

function authoritativeEdit(
  canvas: CanvasPlotSnapshotDTO | null | undefined,
  selection: Selection,
): EditDraft | null {
  if (!canvas || !selection) return null;
  if (selection.kind === "node") {
    const node = canvas.nodes.find((candidate) => candidate.id === selection.id);
    return node
      ? { ...EMPTY_EDIT, title: node.title, body: node.body, colorLabel: node.color_label, groupLabel: node.group_label }
      : null;
  }
  if (selection.kind === "link") {
    const link = canvas.links.find((candidate) => candidate.id === selection.id);
    return link
      ? { ...EMPTY_EDIT, label: link.label, colorLabel: link.color_label, linkType: link.link_type }
      : null;
  }
  const frame = canvas.frames.find((candidate) => candidate.id === selection.id);
  return frame
    ? { ...EMPTY_EDIT, title: frame.title, colorLabel: frame.color_label }
    : null;
}

function inspectorUpdateIntent(draft: InspectorDraft): CanvasPlotCommandIntent {
  const value = draft.value;
  const baseline = draft.baseline;
  if (draft.selection.kind === "node") {
    return {
      kind: "update_node",
      nodeId: draft.selection.id,
      ...(value.title !== baseline.title ? { title: value.title } : {}),
      ...(value.body !== baseline.body ? { body: value.body } : {}),
      ...(value.colorLabel !== baseline.colorLabel ? { colorLabel: value.colorLabel } : {}),
      ...(value.groupLabel !== baseline.groupLabel ? { groupLabel: value.groupLabel } : {}),
    };
  }
  if (draft.selection.kind === "link") {
    return {
      kind: "update_link",
      linkId: draft.selection.id,
      ...(value.label !== baseline.label ? { label: value.label } : {}),
      ...(value.colorLabel !== baseline.colorLabel ? { colorLabel: value.colorLabel } : {}),
      ...(value.linkType !== baseline.linkType ? { linkType: value.linkType } : {}),
    };
  }
  return {
    kind: "update_frame",
    frameId: draft.selection.id,
    ...(value.title !== baseline.title ? { title: value.title } : {}),
    ...(value.colorLabel !== baseline.colorLabel ? { colorLabel: value.colorLabel } : {}),
  };
}

function message(text: string, role?: "alert" | "status") {
  return (
    <div role={role} style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", padding: 28, textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>
      {text}
    </div>
  );
}

function boundsOf(node: Pick<CanvasPlotNodeDTO | CanvasPlotFrameDTO, "x" | "y" | "width" | "height">): CanvasRect {
  return { x: node.x, y: node.y, width: node.width, height: node.height };
}

function keyboardDelta(event: KeyboardEvent, amount = 10): { x: number; y: number } | null {
  const step = event.shiftKey ? 1 : amount;
  if (event.key === "ArrowLeft") return { x: -step, y: 0 };
  if (event.key === "ArrowRight") return { x: step, y: 0 };
  if (event.key === "ArrowUp") return { x: 0, y: -step };
  if (event.key === "ArrowDown") return { x: 0, y: step };
  return null;
}

function isCanvasInteractiveTarget(target: EventTarget | null): boolean {
  const candidate = target as (EventTarget & { closest?: (selector: string) => Element | null }) | null;
  return Boolean(candidate?.closest?.('[data-canvas-interactive="true"]'));
}

function ColorOptions({ current }: { current: string }) {
  return (
    <>
      {current && !COLORS.includes(current) && <option value={current}>{current}</option>}
      {COLORS.map((color) => <option key={color || "auto"} value={color}>{color || "Auto"}</option>)}
    </>
  );
}

export function CanvasPlot(props: PanelProps) {
  const { data, loading, error, refetch } = useCanvasPlot();
  const settings = useSettings();
  const { api, projectId } = useStudio();
  const { setSelection: publishSelection } = useSelection();
  const mounted = useMountedRef();
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const requestRef = useRef<object | null>(null);
  const selectionRef = useRef<Selection>(null);
  const inspectorDraftRef = useRef<InspectorDraft | null>(null);
  const inspectorSaveInFlightRef = useRef<Promise<boolean> | null>(null);
  const persistInspectorRef = useRef<(reservedToken?: object) => Promise<boolean>>(async () => true);
  const inspectorFlusherRef = useRef<ProjectFlusher>(() => persistInspectorRef.current());
  const unregisterInspectorFlusherRef = useRef<(() => void) | null>(null);
  const inspectorDetachedRef = useRef(false);
  const viewportElementRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<Gesture | null>(null);
  const viewportPersistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const settingsPatchRef = useRef(settings.patch);
  settingsPatchRef.current = settings.patch;

  const [commandSnapshot, setCommandSnapshot] = useState<CanvasPlotSnapshotDTO | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [pendingSource, setPendingSource] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [status, setStatus] = useState("");
  const [retryIntent, setRetryIntent] = useState<CanvasPlotCommandIntent | null>(null);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [viewport, setViewport] = useState<CanvasViewport>({ ...DEFAULT_CANVAS_VIEWPORT });
  const [viewportReady, setViewportReady] = useState(false);
  const [viewportSize, setViewportSize] = useState<CanvasSize>(DEFAULT_VIEW_SIZE);
  const [draftNode, setDraftNode] = useState<(CanvasRect & { id: number }) | null>(null);
  const [draftFrame, setDraftFrame] = useState<(CanvasRect & { id: number }) | null>(null);
  const [edit, setEdit] = useState<EditDraft>(EMPTY_EDIT);
  const editRef = useRef<EditDraft>(EMPTY_EDIT);
  const [inspectorDirty, setInspectorDirty] = useState(false);

  selectionRef.current = selection;
  editRef.current = edit;

  const canvas = commandSnapshot?.project_id === projectId
    ? commandSnapshot
    : data?.project_id === projectId
      ? data
      : undefined;

  useEffect(() => {
    if (data && data.project_id === projectId) setCommandSnapshot(data);
  }, [data, projectId]);

  useEffect(() => {
    const carriedDraft = inspectorDraftRef.current?.dirty
      ? inspectorDraftRef.current
      : null;
    requestRef.current = null;
    gestureRef.current = null;
    setCommandSnapshot(null);
    setSelection(null);
    setPendingSource(null);
    setBusy("");
    setMutationError(carriedDraft
      ? "A Canvas Plot inspector draft from the previous project still needs Save or Revert."
      : "");
    setStatus("");
    setRetryIntent(null);
    setConfirmDelete("");
    setDraftNode(null);
    setDraftFrame(null);
    setEdit(EMPTY_EDIT);
    editRef.current = EMPTY_EDIT;
    if (!carriedDraft) {
      inspectorDraftRef.current = null;
      inspectorSaveInFlightRef.current = null;
    }
    setInspectorDirty(Boolean(carriedDraft));
    setViewport({ ...DEFAULT_CANVAS_VIEWPORT });
    setViewportReady(false);
    publishSelection({ sceneId: null, text: "", section: "Canvas Plot", nodeId: null });
    if (viewportPersistTimerRef.current) clearTimeout(viewportPersistTimerRef.current);
    viewportPersistTimerRef.current = null;
  }, [projectId, publishSelection]);

  // Read the viewport against an explicit owner id. `useSettings().data` is
  // intentionally optimistic and can still contain project A for the first
  // render after switching to B; hydrating from that transient value would leak
  // A's camera and then suppress B's eventual value. The HTTP client coalesces
  // this GET with useSettings' own read, so the ownership guard costs no extra
  // desktop request while keeping project switches exact.
  useEffect(() => {
    setViewportReady(false);
    if (projectId == null) return;
    const ownerProjectId = projectId;
    let cancelled = false;
    void api.getSettings(ownerProjectId).then(
      (value) => {
        if (!cancelled && projectIdRef.current === ownerProjectId) {
          setViewport(parseCanvasViewport(value.settings[VIEW_SETTING_KEY]));
          setViewportReady(true);
        }
      },
      () => {
        // useSettings exposes the load error; retain the safe default camera.
        if (!cancelled && projectIdRef.current === ownerProjectId) setViewportReady(true);
      },
    );
    return () => { cancelled = true; };
  }, [api, projectId]);

  useEffect(() => {
    const element = viewportElementRef.current;
    if (!element) return;
    const measure = () => {
      const rect = element.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setViewportSize({ width: rect.width, height: rect.height });
      }
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    if (typeof window !== "undefined") window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      if (typeof window !== "undefined") window.removeEventListener("resize", measure);
    };
  }, []);

  useEffect(() => () => {
    if (viewportPersistTimerRef.current) clearTimeout(viewportPersistTimerRef.current);
  }, []);

  const persistViewport = useCallback((next: CanvasViewport, delayed = false) => {
    const save = () => {
      viewportPersistTimerRef.current = null;
      void settingsPatchRef.current({ [VIEW_SETTING_KEY]: next });
    };
    if (viewportPersistTimerRef.current) clearTimeout(viewportPersistTimerRef.current);
    if (delayed) viewportPersistTimerRef.current = setTimeout(save, 240);
    else save();
  }, []);

  const applyViewport = useCallback((next: CanvasViewport, delayed = false) => {
    setViewport(next);
    persistViewport(next, delayed);
  }, [persistViewport]);

  const clearDrafts = useCallback(() => {
    setDraftNode(null);
    setDraftFrame(null);
  }, []);

  const replaceEdit = useCallback((next: EditDraft) => {
    editRef.current = next;
    setEdit(next);
  }, []);

  persistInspectorRef.current = async (reservedToken?: object): Promise<boolean> => {
    if (requestRef.current != null && requestRef.current !== reservedToken) return false;
    if (inspectorSaveInFlightRef.current) return inspectorSaveInFlightRef.current;
    const initialDraft = inspectorDraftRef.current;
    if (!initialDraft?.dirty) return true;

    const token = reservedToken ?? {};
    const ownsToken = requestRef.current == null;
    if (ownsToken) {
      requestRef.current = token;
      if (mounted.current) {
        setBusy("save_inspector");
        setStatus("Saving Canvas Plot inspector…");
        setMutationError("");
      }
    }

    const operation = (async (): Promise<boolean> => {
      while (true) {
        const current = inspectorDraftRef.current;
        if (!current?.dirty) return true;
        const ownerProjectId = current.projectId;
        const ownerKey = selectionKey(current.selection);
        const generation = current.generation;
        const submittedBaseline = { ...current.baseline };
        const submittedValue = { ...current.value };
        const intent = inspectorUpdateIntent({
          ...current,
          baseline: submittedBaseline,
          value: submittedValue,
        });
        const saveKey = inspectorSaveKey(current);
        try {
          const latest = await api.getCanvasPlot(ownerProjectId);
          if (latest.project_id !== ownerProjectId) {
            throw new Error("The latest Canvas Plot belongs to another project.");
          }
          const beforeWrite = inspectorDraftRef.current;
          if (!beforeWrite?.dirty) return true;
          if (beforeWrite.projectId !== ownerProjectId || selectionKey(beforeWrite.selection) !== ownerKey) {
            return false;
          }
          if (beforeWrite.generation !== generation) continue;
          const planned = planCanvasPlotCommand(latest, intent);
          if (!planned.command) throw new Error(planned.error);
          const result = await trackProjectWrite(
            api.executeCanvasPlotCommand(ownerProjectId, planned.command),
            { saveKey },
          );
          if (result.canvas_plot.project_id !== ownerProjectId) {
            throw new Error("The updated Canvas Plot belongs to another project.");
          }

          const active = inspectorDraftRef.current;
          const savedValue = authoritativeEdit(result.canvas_plot, current.selection);
          if (active && selectionKey(active.selection) === ownerKey && active.projectId === ownerProjectId && savedValue) {
            active.baseline = savedValue;
            active.value = rebaseEdit(active.value, submittedValue, savedValue);
            active.dirty = !editsEqual(active.value, savedValue);
            if (active.dirty) {
              // A newer edit may have landed after the first request's revision
              // was allocated. Re-mark its keyed owner so that write success
              // cannot make the handoff barrier briefly appear clean.
              markProjectSavePending(saveKey);
            } else {
              discardProjectSavePending(saveKey);
            }
            if (mounted.current) {
              setInspectorDirty(active.dirty);
              if (projectIdRef.current === ownerProjectId
                && selectionKey(selectionRef.current) === ownerKey) {
                replaceEdit(active.value);
              } else if (!active.dirty) {
                setMutationError("");
                setStatus("Previous Canvas Plot inspector draft saved.");
              }
            }
          }
          if (mounted.current && projectIdRef.current === ownerProjectId) {
            setCommandSnapshot(result.canvas_plot);
            setRetryIntent(null);
            setMutationError("");
            setStatus(result.changed ? "Canvas Plot inspector saved." : "Canvas Plot inspector already matched.");
            refetch();
          }
          if (!inspectorDraftRef.current?.dirty) return true;
        } catch (failure) {
          if (mounted.current) {
            const conflict = failure instanceof ApiRequestError
              && (failure.code === "canvas_plot_conflict" || failure.status === 409);
            setMutationError(conflict
              ? "The Canvas Plot changed before the inspector could be saved. Your draft was kept; retry Save or Revert it."
              : `Couldn't save the Canvas Plot inspector — ${failure instanceof Error ? failure.message : String(failure)}`);
            setStatus("");
            if (projectIdRef.current === ownerProjectId) refetch();
          }
          return false;
        }
      }
    })();
    inspectorSaveInFlightRef.current = operation;
    try {
      return await operation;
    } finally {
      if (inspectorSaveInFlightRef.current === operation) inspectorSaveInFlightRef.current = null;
      if (ownsToken && requestRef.current === token) {
        requestRef.current = null;
        if (mounted.current) setBusy("");
      }
      if (inspectorDetachedRef.current && !inspectorDraftRef.current?.dirty) {
        unregisterInspectorFlusherRef.current?.();
        unregisterInspectorFlusherRef.current = null;
      }
    }
  };

  useEffect(() => {
    inspectorDetachedRef.current = false;
    const unregister = registerProjectFlusher(inspectorFlusherRef.current);
    unregisterInspectorFlusherRef.current = unregister;
    return () => {
      inspectorDetachedRef.current = true;
      if (!inspectorDraftRef.current?.dirty && !inspectorSaveInFlightRef.current) {
        unregister();
        unregisterInspectorFlusherRef.current = null;
        return;
      }
      // Panel/workspace closes normally drain this editor first. If React tears
      // it down unexpectedly, finish the owned save without touching UI state;
      // keep the flusher registered on failure so the global barrier can retry.
      const detachedSave = persistInspectorRef.current(requestRef.current ?? undefined);
      const detachedPersistence = detachedSave.then((saved) => {
        if (!saved) throw new Error("Canvas Plot inspector draft is still unsaved.");
        return saved;
      });
      trackProjectOperation(detachedPersistence, {
        ownerFlusher: inspectorFlusherRef.current,
        persistence: true,
      });
      void detachedSave.finally(() => {
        if (!inspectorDraftRef.current?.dirty && !inspectorSaveInFlightRef.current) {
          unregisterInspectorFlusherRef.current?.();
          unregisterInspectorFlusherRef.current = null;
        }
      });
    };
  }, []);

  const runIntent = useCallback(async (intent: CanvasPlotCommandIntent) => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null || requestRef.current != null) return;
    const token = {};
    requestRef.current = token;
    setBusy(intent.kind);
    setMutationError("");
    setStatus("Saving Canvas Plot change…");
    try {
      if (!await persistInspectorRef.current(token)) {
        throw new Error("Save or Revert the Canvas Plot inspector draft before continuing.");
      }
      await flushPendingProjectSaves({
        commitActiveField: true,
        excludeFlusher: inspectorFlusherRef.current,
      });
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      const latest = await api.getCanvasPlot(ownerProjectId);
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      if (latest.project_id !== ownerProjectId) throw new Error("The latest Canvas Plot belongs to another project.");
      setCommandSnapshot(latest);
      const planned = planCanvasPlotCommand(latest, intent);
      if (!planned.command) {
        setMutationError(planned.error);
        setStatus("");
        setRetryIntent(null);
        clearDrafts();
        refetch();
        return;
      }
      const result = await trackProjectWrite(
        api.executeCanvasPlotCommand(ownerProjectId, planned.command),
      );
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      if (result.canvas_plot.project_id !== ownerProjectId) throw new Error("The updated Canvas Plot belongs to another project.");
      setCommandSnapshot(result.canvas_plot);
      setRetryIntent(null);
      setMutationError("");
      setPendingSource(null);
      setConfirmDelete("");
      clearDrafts();
      let nextSelection: Selection | undefined;
      if (result.created_node_id != null) nextSelection = { kind: "node", id: result.created_node_id };
      else if (result.created_link_id != null) nextSelection = { kind: "link", id: result.created_link_id };
      else if (result.created_frame_id != null) nextSelection = { kind: "frame", id: result.created_frame_id };
      else if (intent.kind.startsWith("delete_")) nextSelection = null;
      if (nextSelection !== undefined) {
        selectionRef.current = nextSelection;
        setSelection(nextSelection);
      }
      setStatus(result.changed ? "Canvas Plot change saved." : "Canvas Plot already matched that change.");
      refetch();
    } catch (failure) {
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      const conflict = failure instanceof ApiRequestError
        && (failure.code === "canvas_plot_conflict" || failure.status === 409);
      const retryable = conflict && canvasPlotIntentCanRetry(intent);
      setRetryIntent(retryable ? intent : null);
      setMutationError(conflict
        ? retryable
          ? `The Canvas Plot changed before this action could be saved. Review the refreshed board, then retry: ${describeCanvasPlotIntent(intent)}.`
          : "The Canvas Plot changed before this edit could be saved. The board was refreshed; repeat the edit against its current state."
        : `Couldn't update the Canvas Plot — ${failure instanceof Error ? failure.message : String(failure)}`);
      setStatus("");
      clearDrafts();
      refetch();
    } finally {
      if (requestRef.current === token) {
        requestRef.current = null;
        if (mounted.current && projectIdRef.current === ownerProjectId) setBusy("");
      }
    }
  }, [api, clearDrafts, mounted, refetch]);

  const nodes = useMemo(() => (canvas?.nodes ?? [])
    .map((node) => draftNode?.id === node.id ? { ...node, ...draftNode } : node)
    .sort((left, right) => left.sort_order - right.sort_order || left.id - right.id), [canvas?.nodes, draftNode]);
  const frames = useMemo(() => (canvas?.frames ?? [])
    .map((frame) => draftFrame?.id === frame.id ? { ...frame, ...draftFrame } : frame), [canvas?.frames, draftFrame]);
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const links = canvas?.links ?? [];
  const selectedNode = selection?.kind === "node" ? nodeById.get(selection.id) : undefined;
  const selectedLink = selection?.kind === "link" ? links.find((link) => link.id === selection.id) : undefined;
  const selectedFrame = selection?.kind === "frame" ? frames.find((frame) => frame.id === selection.id) : undefined;
  const disabled = Boolean(busy) || loading || !canvas || projectId == null || !viewportReady;

  useEffect(() => {
    const authoritative = authoritativeEdit(canvas, selection);
    if (!selection) {
      if (!inspectorDraftRef.current?.dirty) inspectorDraftRef.current = null;
      replaceEdit(EMPTY_EDIT);
      setInspectorDirty(Boolean(inspectorDraftRef.current?.dirty));
      publishSelection({ sceneId: null, text: "", section: "Canvas Plot", nodeId: null });
      return;
    }
    const existing = inspectorDraftRef.current;
    const sameDraft = existing != null
      && existing.projectId === projectId
      && selectionKey(existing.selection) === selectionKey(selection);
    if (!authoritative) {
      if (sameDraft && existing?.dirty) {
        setMutationError("This Canvas Plot item no longer exists. Revert its inspector draft before leaving.");
        setInspectorDirty(true);
        return;
      }
      setSelection(null);
      return;
    }

    let effective = authoritative;
    if (sameDraft && existing) {
      const rebased = rebaseEdit(existing.value, existing.baseline, authoritative);
      existing.baseline = authoritative;
      existing.value = rebased;
      existing.dirty = !editsEqual(rebased, authoritative);
      effective = rebased;
      if (existing.dirty) {
        setInspectorDirty(true);
      } else {
        discardProjectSavePending(inspectorSaveKey(existing));
        setInspectorDirty(false);
      }
    } else if (projectId != null) {
      inspectorDraftRef.current = {
        projectId,
        selection,
        baseline: authoritative,
        value: authoritative,
        generation: 0,
        dirty: false,
      };
      setInspectorDirty(false);
    }
    replaceEdit(effective);

    if (selection.kind === "node") {
      const node = canvas?.nodes.find((candidate) => candidate.id === selection.id);
      publishSelection({
        sceneId: node?.scene_id ?? null,
        text: [effective.title, effective.body].filter(Boolean).join("\n"),
        section: "Canvas Plot",
        nodeId: selection.id,
      });
    } else if (selection.kind === "link") {
      publishSelection({ sceneId: null, text: [effective.label, effective.linkType].filter(Boolean).join(" · "), section: "Canvas Plot", nodeId: `link:${selection.id}` });
    } else {
      publishSelection({ sceneId: null, text: effective.title, section: "Canvas Plot", nodeId: `frame:${selection.id}` });
    }
  }, [canvas, projectId, publishSelection, replaceEdit, selection]);

  const changeEdit = useCallback((patch: Partial<EditDraft>) => {
    const draft = inspectorDraftRef.current;
    if (!draft) return;
    const next = { ...editRef.current, ...patch };
    draft.value = next;
    draft.generation += 1;
    draft.dirty = !editsEqual(next, draft.baseline);
    replaceEdit(next);
    setInspectorDirty(draft.dirty);
    if (draft.dirty) markProjectSavePending(inspectorSaveKey(draft));
    else discardProjectSavePending(inspectorSaveKey(draft));
  }, [replaceEdit]);

  const revertInspector = useCallback(() => {
    if (inspectorSaveInFlightRef.current) return;
    const draft = inspectorDraftRef.current;
    if (!draft) return;
    discardProjectSavePending(inspectorSaveKey(draft));
    draft.generation += 1;
    draft.dirty = false;
    const authoritative = canvas?.project_id === draft.projectId
      ? authoritativeEdit(canvas, draft.selection)
      : null;
    if (!authoritative) {
      inspectorDraftRef.current = null;
      selectionRef.current = null;
      setSelection(null);
      replaceEdit(EMPTY_EDIT);
    } else {
      draft.baseline = authoritative;
      draft.value = authoritative;
      replaceEdit(authoritative);
    }
    setInspectorDirty(false);
    setMutationError("");
    setStatus("Inspector draft reverted.");
  }, [canvas, replaceEdit]);

  const chooseSelection = useCallback(async (next: Selection): Promise<boolean> => {
    if (selectionKey(selectionRef.current) === selectionKey(next)) {
      setConfirmDelete("");
      return true;
    }
    if (!await persistInspectorRef.current()) return false;
    if (!mounted.current) return false;
    selectionRef.current = next;
    setSelection(next);
    setConfirmDelete("");
    return true;
  }, [mounted]);

  const beginGesture = useCallback((
    event: PointerEvent,
    kind: Gesture["kind"],
    rect?: CanvasRect,
    id?: number,
  ) => {
    if (disabled || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    viewportElementRef.current?.setPointerCapture?.(event.pointerId);
    gestureRef.current = {
      kind,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startViewport: viewport,
      rect,
      id,
    };
    if (kind === "move_node" || kind === "resize_node") setDraftNode(rect && id != null ? { id, ...rect } : null);
    if (kind === "move_frame" || kind === "resize_frame") setDraftFrame(rect && id != null ? { id, ...rect } : null);
  }, [disabled, viewport]);

  const rectForPointer = useCallback((gesture: Gesture, clientX: number, clientY: number): CanvasRect | null => {
    if (!gesture.rect) return null;
    const delta = {
      x: (clientX - gesture.startClientX) / gesture.startViewport.zoom,
      y: (clientY - gesture.startClientY) / gesture.startViewport.zoom,
    };
    if (gesture.kind === "move_node" || gesture.kind === "move_frame") return moveCanvasRect(gesture.rect, delta);
    if (gesture.kind === "resize_node") return resizeCanvasRect(gesture.rect, delta, "node");
    if (gesture.kind === "resize_frame") return resizeCanvasRect(gesture.rect, delta, "frame");
    return null;
  }, []);

  const onPointerMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    event.preventDefault();
    if (gesture.kind === "pan") {
      setViewport(panCanvasViewport(gesture.startViewport, {
        x: event.clientX - gesture.startClientX,
        y: event.clientY - gesture.startClientY,
      }));
      return;
    }
    const rect = rectForPointer(gesture, event.clientX, event.clientY);
    if (!rect || gesture.id == null) return;
    if (gesture.kind === "move_node" || gesture.kind === "resize_node") setDraftNode({ id: gesture.id, ...rect });
    else setDraftFrame({ id: gesture.id, ...rect });
  }, [rectForPointer]);

  const finishGesture = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    gestureRef.current = null;
    viewportElementRef.current?.releasePointerCapture?.(event.pointerId);
    if (gesture.kind === "pan") {
      const next = panCanvasViewport(gesture.startViewport, {
        x: event.clientX - gesture.startClientX,
        y: event.clientY - gesture.startClientY,
      });
      setViewport(next);
      persistViewport(next);
      return;
    }
    const rect = rectForPointer(gesture, event.clientX, event.clientY);
    if (!rect || gesture.id == null) { clearDrafts(); return; }
    if (gesture.kind === "move_node" || gesture.kind === "resize_node") {
      void runIntent({ kind: "update_node", nodeId: gesture.id, ...rect });
    } else {
      void runIntent({ kind: "update_frame", frameId: gesture.id, ...rect });
    }
  }, [clearDrafts, persistViewport, rectForPointer, runIntent]);

  const cancelGesture = useCallback(() => {
    const gesture = gestureRef.current;
    gestureRef.current = null;
    if (gesture?.kind === "pan") setViewport(gesture.startViewport);
    clearDrafts();
  }, [clearDrafts]);

  const onWheel = useCallback((event: globalThis.WheelEvent) => {
    if (disabled) return;
    event.preventDefault();
    const rect = viewportElementRef.current?.getBoundingClientRect();
    const size = rect && rect.width > 0 && rect.height > 0
      ? { width: rect.width, height: rect.height }
      : viewportSize;
    const anchor = { x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) };
    const next = zoomCanvasViewportAt(viewport, viewport.zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15), anchor, size);
    applyViewport(next, true);
  }, [applyViewport, disabled, viewport, viewportSize]);

  useEffect(() => {
    const element = viewportElementRef.current;
    if (!element) return undefined;
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [onWheel]);

  const selectNode = useCallback((node: CanvasPlotNodeDTO) => {
    void chooseSelection({ kind: "node", id: node.id });
  }, [chooseSelection]);

  const beginNodeGesture = useCallback((
    event: PointerEvent,
    node: CanvasPlotNodeDTO,
    kind: "move_node" | "resize_node",
  ) => {
    const nextSelection: Selection = { kind: "node", id: node.id };
    if (selectionKey(selectionRef.current) !== selectionKey(nextSelection)) {
      event.preventDefault();
      event.stopPropagation();
      void chooseSelection(nextSelection);
      return;
    }
    beginGesture(event, kind, boundsOf(node), node.id);
  }, [beginGesture, chooseSelection]);

  const beginFrameGesture = useCallback((
    event: PointerEvent,
    frame: CanvasPlotFrameDTO,
    kind: "move_frame" | "resize_frame",
  ) => {
    const nextSelection: Selection = { kind: "frame", id: frame.id };
    if (selectionKey(selectionRef.current) !== selectionKey(nextSelection)) {
      event.preventDefault();
      event.stopPropagation();
      void chooseSelection(nextSelection);
      return;
    }
    beginGesture(event, kind, boundsOf(frame), frame.id);
  }, [beginGesture, chooseSelection]);

  const nudgeNode = useCallback((event: KeyboardEvent, node: CanvasPlotNodeDTO, resize: boolean) => {
    const delta = keyboardDelta(event);
    if (!delta || disabled) return;
    event.preventDefault();
    const rect = resize ? resizeCanvasRect(boundsOf(node), delta, "node") : moveCanvasRect(boundsOf(node), delta);
    void runIntent({ kind: "update_node", nodeId: node.id, ...rect });
  }, [disabled, runIntent]);

  const nudgeFrame = useCallback((event: KeyboardEvent, frame: CanvasPlotFrameDTO, resize: boolean) => {
    const delta = keyboardDelta(event);
    if (!delta || disabled) return;
    event.preventDefault();
    const rect = resize ? resizeCanvasRect(boundsOf(frame), delta, "frame") : moveCanvasRect(boundsOf(frame), delta);
    void runIntent({ kind: "update_frame", frameId: frame.id, ...rect });
  }, [disabled, runIntent]);

  const connectNode = useCallback((event: { stopPropagation(): void }, nodeId: number) => {
    event.stopPropagation();
    if (disabled) return;
    if (pendingSource == null) {
      setPendingSource(nodeId);
      setStatus(`Choose a target block for connection from #${nodeId}.`);
      return;
    }
    if (pendingSource === nodeId) {
      setPendingSource(null);
      setStatus("");
      return;
    }
    const sourceNodeId = pendingSource;
    setPendingSource(null);
    void runIntent({ kind: "create_link", sourceNodeId, targetNodeId: nodeId, colorLabel: "gray" });
  }, [disabled, pendingSource, runIntent]);

  const selectedKey = selectionKey(selection);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Canvas Plot" style={panelBox}>
        <div style={{ minHeight: 42, flex: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, padding: "5px 12px", borderBottom: "1px solid var(--line)", background: "var(--tint)", zIndex: 70 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>CANVAS PLOT</span>
          <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{nodes.length} BLOCKS · {links.length} LINKS · {frames.length} FRAMES</span>
          <button type="button" aria-label="Add Canvas Plot block" disabled={disabled} onClick={() => void runIntent({
            kind: "create_node",
            title: "New block",
            x: viewport.cx - 94 + (nodes.length % 6) * 24,
            y: viewport.cy - 58 + (nodes.length % 6) * 24,
            width: 188,
            height: 116,
          })} style={toolbarButton}>＋ BLOCK</button>
          <button type="button" aria-label="Add Canvas Plot frame" disabled={disabled} onClick={() => void runIntent({
            kind: "create_frame",
            title: "Group",
            x: viewport.cx - 180 + (frames.length % 5) * 30,
            y: viewport.cy - 130 + (frames.length % 5) * 30,
            width: 360,
            height: 260,
          })} style={toolbarButton}>＋ FRAME</button>
          {pendingSource != null && <button type="button" onClick={() => { setPendingSource(null); setStatus(""); }} style={{ ...toolbarButton, color: "var(--amber)", borderColor: "var(--amber)" }}>CANCEL LINK</button>}
          <div style={{ flex: 1 }} />
          <button type="button" aria-label="Pan Canvas Plot left" disabled={disabled} onClick={() => applyViewport({ ...viewport, cx: viewport.cx - 80 / viewport.zoom })} style={toolbarButton}>←</button>
          <button type="button" aria-label="Pan Canvas Plot right" disabled={disabled} onClick={() => applyViewport({ ...viewport, cx: viewport.cx + 80 / viewport.zoom })} style={toolbarButton}>→</button>
          <button type="button" aria-label="Zoom Canvas Plot out" disabled={disabled} onClick={() => applyViewport(zoomCanvasViewportAt(viewport, viewport.zoom / 1.15, { x: viewportSize.width / 2, y: viewportSize.height / 2 }, viewportSize))} style={toolbarButton}>−</button>
          <button type="button" aria-label="Reset Canvas Plot view" disabled={disabled} onClick={() => applyViewport({ ...DEFAULT_CANVAS_VIEWPORT })} style={{ ...toolbarButton, minWidth: 48 }}>{Math.round(viewport.zoom * 100)}%</button>
          <button type="button" aria-label="Zoom Canvas Plot in" disabled={disabled} onClick={() => applyViewport(zoomCanvasViewportAt(viewport, viewport.zoom * 1.15, { x: viewportSize.width / 2, y: viewportSize.height / 2 }, viewportSize))} style={toolbarButton}>＋</button>
          <button type="button" disabled={disabled} onClick={() => applyViewport(fitCanvasViewport(canvasContentBounds(nodes, frames), viewportSize))} style={toolbarButton}>FIT</button>
        </div>

        {(mutationError || status || settings.error || inspectorDirty) && (
          <div role={mutationError || settings.error ? "alert" : "status"} aria-live="polite" style={{ flex: "none", zIndex: 70, display: "flex", alignItems: "center", gap: 8, padding: "5px 12px", borderBottom: "1px solid var(--line2)", background: "var(--panel)", color: mutationError || settings.error ? "var(--crimson)" : "var(--green)", fontSize: 8 }}>
            <span style={{ flex: 1 }}>{mutationError || settings.error || status || "Canvas Plot inspector has unsaved changes."}</span>
            {retryIntent && <button type="button" disabled={disabled} onClick={() => void runIntent(retryIntent)} style={toolbarButton}>RETRY</button>}
            {inspectorDirty && <button type="button" disabled={Boolean(busy)} onClick={revertInspector} style={toolbarButton}>REVERT DRAFT</button>}
            {mutationError && <button type="button" onClick={() => { setMutationError(""); setRetryIntent(null); }} style={toolbarButton}>DISMISS</button>}
          </div>
        )}

        <div
          ref={viewportElementRef}
          data-canvas-plot-board="true"
          data-canvas-viewport="true"
          data-viewport-ready={viewportReady ? "true" : "false"}
          data-zoom={viewport.zoom}
          data-center-x={viewport.cx}
          data-center-y={viewport.cy}
          role="application"
          tabIndex={0}
          aria-label="Canvas Plot board"
          style={{
            position: "relative",
            flex: 1,
            overflow: "hidden",
            touchAction: "none",
            cursor: gestureRef.current?.kind === "pan" ? "grabbing" : "grab",
            backgroundColor: "var(--panel2)",
            backgroundImage: "radial-gradient(circle,rgba(128,140,158,.15) 1px,transparent 1.3px)",
            backgroundSize: `${34 * viewport.zoom}px ${34 * viewport.zoom}px`,
            backgroundPosition: `${viewportSize.width / 2 - viewport.cx * viewport.zoom}px ${viewportSize.height / 2 - viewport.cy * viewport.zoom}px`,
          }}
          onPointerDown={(event) => {
            if (isCanvasInteractiveTarget(event.target)) return;
            beginGesture(event, "pan");
          }}
          onPointerMove={onPointerMove}
          onPointerUp={finishGesture}
          onPointerCancel={cancelGesture}
          onKeyDown={(event) => {
            if (isCanvasInteractiveTarget(event.target)) return;
            if (event.key === "Escape") {
              void chooseSelection(null).then((changed) => {
                if (!changed) return;
                setPendingSource(null);
                setStatus("");
              });
              return;
            }
            const delta = keyboardDelta(event, 80);
            if (!delta || disabled) return;
            event.preventDefault();
            applyViewport({
              ...viewport,
              cx: viewport.cx + delta.x / viewport.zoom,
              cy: viewport.cy + delta.y / viewport.zoom,
            });
          }}
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              void chooseSelection(null).then((changed) => {
                if (changed) setPendingSource(null);
              });
            }
          }}
        >
          {loading && !canvas
            ? message("Loading Canvas Plot…", "status")
            : error && !canvas
              ? message(`Couldn't load Canvas Plot — ${error}`, "alert")
              : canvas && nodes.length === 0 && frames.length === 0
                ? message("This thinking board is empty — add a block or frame to begin")
                : null}

          {canvas && (
            <div
              data-canvas-world="true"
              style={{
                position: "absolute",
                left: 0,
                top: 0,
                width: 1,
                height: 1,
                overflow: "visible",
                transformOrigin: "0 0",
                transform: canvasWorldTransform(viewport, viewportSize),
              }}
            >
              {frames.map((frame) => {
                const selected = selection?.kind === "frame" && selection.id === frame.id;
                const color = colorValue(frame.color_label, "var(--txt3)");
                return (
                  <div
                    key={frame.id}
                    data-canvas-interactive="true"
                    data-canvas-frame-id={frame.id}
                    data-x={frame.x}
                    data-y={frame.y}
                    data-width={frame.width}
                    data-height={frame.height}
                    role="group"
                    tabIndex={0}
                    aria-label={`Canvas Plot frame ${frame.id}`}
                    style={{ position: "absolute", left: frame.x, top: frame.y, width: frame.width, height: frame.height, zIndex: 0, boxSizing: "border-box", border: `${selected ? 2 : 1}px solid ${color}`, background: `color-mix(in srgb, ${color} 9%, transparent)`, borderRadius: 10 }}
                    onClick={(event) => { event.stopPropagation(); void chooseSelection({ kind: "frame", id: frame.id }); }}
                    onKeyDown={(event) => {
                      if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
                        event.preventDefault();
                        void chooseSelection({ kind: "frame", id: frame.id });
                      }
                    }}
                  >
                    <button
                      type="button"
                      data-canvas-frame-move-handle="true"
                      aria-label={`Move Canvas Plot frame ${frame.id}`}
                      disabled={disabled}
                      onPointerDown={(event) => beginFrameGesture(event, frame, "move_frame")}
                      onKeyDown={(event) => nudgeFrame(event, frame, false)}
                      style={{ width: "100%", height: 27, display: "block", border: "none", borderBottom: `1px solid ${color}`, background: `color-mix(in srgb, ${color} 22%, var(--panel2))`, color: "var(--strong)", font: "inherit", fontSize: 9, textAlign: "left", padding: "0 9px", cursor: "move", borderRadius: "9px 9px 0 0" }}
                    >{frame.title || "Frame"}</button>
                    <button
                      type="button"
                      data-canvas-frame-resize-handle="true"
                      aria-label={`Resize Canvas Plot frame ${frame.id}`}
                      disabled={disabled}
                      onPointerDown={(event) => beginFrameGesture(event, frame, "resize_frame")}
                      onKeyDown={(event) => nudgeFrame(event, frame, true)}
                      style={{ position: "absolute", right: -5, bottom: -5, width: 13, height: 13, border: `1px solid ${color}`, background: "var(--panel)", color, padding: 0, cursor: "nwse-resize" }}
                    />
                  </div>
                );
              })}

              <svg aria-label="Canvas Plot connections" style={{ position: "absolute", left: 0, top: 0, width: 1, height: 1, overflow: "visible", zIndex: 1 }}>
                {links.map((link) => {
                  const source = nodeById.get(link.source_node_id);
                  const target = nodeById.get(link.target_node_id);
                  if (!source || !target) return null;
                  const geometry = canvasLinkGeometry(boundsOf(source), boundsOf(target));
                  const selected = selection?.kind === "link" && selection.id === link.id;
                  const color = colorValue(link.color_label, "var(--txt3)");
                  return (
                    <g
                      key={link.id}
                      data-canvas-interactive="true"
                      data-canvas-link-id={link.id}
                      data-source-node-id={link.source_node_id}
                      data-target-node-id={link.target_node_id}
                      role="button"
                      tabIndex={0}
                      aria-label={`Select Canvas Plot connection ${link.id}`}
                      aria-pressed={selected}
                      onClick={(event) => { event.stopPropagation(); void chooseSelection({ kind: "link", id: link.id }); }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          void chooseSelection({ kind: "link", id: link.id });
                        }
                      }}
                    >
                      <path d={geometry.path} fill="none" stroke="transparent" strokeWidth={14} style={{ cursor: "pointer" }} />
                      <path d={geometry.path} fill="none" stroke={selected ? "var(--accent)" : color} strokeWidth={selected ? 3 : 2} strokeLinecap="round" />
                      <circle cx={geometry.source.x} cy={geometry.source.y} r={3} fill={color} />
                      <circle cx={geometry.target.x} cy={geometry.target.y} r={3} fill={color} />
                      {link.label && <text x={geometry.midpoint.x + 5} y={geometry.midpoint.y - 5} fill="var(--txt2)" fontSize={8}>{link.label}</text>}
                    </g>
                  );
                })}
              </svg>

              {nodes.map((node, index) => {
                const selected = selection?.kind === "node" && selection.id === node.id;
                const connecting = pendingSource === node.id;
                const color = colorValue(node.color_label);
                return (
                  <div
                    key={node.id}
                    role="group"
                    tabIndex={0}
                    aria-label={`Canvas Plot block ${node.id}`}
                    data-canvas-interactive="true"
                    data-canvas-node-id={node.id}
                    data-x={node.x}
                    data-y={node.y}
                    data-width={node.width}
                    data-height={node.height}
                    style={{
                      position: "absolute",
                      left: node.x,
                      top: node.y,
                      width: node.width,
                      height: node.height,
                      zIndex: 10 + index,
                      boxSizing: "border-box",
                      border: `${selected || connecting ? 2 : 1}px solid ${selected ? "var(--accent)" : connecting ? "var(--amber)" : "var(--line2)"}`,
                      borderLeft: `5px solid ${color}`,
                      background: "var(--raised)",
                      boxShadow: selected ? "0 0 22px rgba(76,194,255,.28)" : "0 8px 24px rgba(0,0,0,.45)",
                      overflow: "hidden",
                    }}
                    onClick={(event) => { event.stopPropagation(); selectNode(node); }}
                    onKeyDown={(event) => {
                      if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
                        event.preventDefault();
                        selectNode(node);
                      }
                    }}
                  >
                    <div style={{ height: 28, display: "flex", alignItems: "stretch", borderBottom: "1px solid var(--line2)" }}>
                      <button
                        type="button"
                        data-canvas-node-move-handle="true"
                        aria-label={`Move Canvas Plot block ${node.id}`}
                        disabled={disabled}
                        onPointerDown={(event) => beginNodeGesture(event, node, "move_node")}
                        onKeyDown={(event) => nudgeNode(event, node, false)}
                        style={{ flex: 1, minWidth: 0, border: "none", background: "transparent", color: "var(--strong)", font: "inherit", fontSize: 9, textAlign: "left", padding: "0 7px", cursor: "move", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                      >⠿ {node.title || "Untitled"}</button>
                      <button
                        type="button"
                        data-canvas-node-connect-handle="true"
                        aria-label={pendingSource == null ? `Start connection from Canvas Plot block ${node.id}` : pendingSource === node.id ? `Cancel connection from Canvas Plot block ${node.id}` : `Connect to Canvas Plot block ${node.id}`}
                        disabled={disabled}
                        onClick={(event) => connectNode(event, node.id)}
                        style={{ width: 28, border: "none", borderLeft: "1px solid var(--line2)", background: connecting ? "var(--amber)" : "transparent", color: connecting ? "var(--panel2)" : color, font: "inherit", cursor: "crosshair" }}
                      >●</button>
                    </div>
                    <div style={{ padding: "7px 8px", fontSize: 9, color: "var(--txt2)", lineHeight: 1.4, height: Math.max(20, node.height - 48), overflow: "hidden", whiteSpace: "pre-wrap" }}>{node.body || "Select this block to add a summary."}</div>
                    {node.group_label && <div style={{ position: "absolute", left: 8, bottom: 4, right: 18, fontSize: 7, color: "var(--txt3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}># {node.group_label}</div>}
                    <button
                      type="button"
                      data-canvas-node-resize-handle="true"
                      aria-label={`Resize Canvas Plot block ${node.id}`}
                      disabled={disabled}
                      onPointerDown={(event) => beginNodeGesture(event, node, "resize_node")}
                      onKeyDown={(event) => nudgeNode(event, node, true)}
                      style={{ position: "absolute", right: -1, bottom: -1, width: 14, height: 14, border: "1px solid var(--accent)", background: "var(--panel)", color: "var(--accent)", padding: 0, cursor: "nwse-resize" }}
                    />
                  </div>
                );
              })}
            </div>
          )}

          {(selectedNode || selectedLink || selectedFrame) && (
            <form
              key={selectedKey}
              aria-label="Canvas Plot inspector"
              data-canvas-interactive="true"
              onSubmit={(event) => {
                event.preventDefault();
                void persistInspectorRef.current();
              }}
              style={{ position: "absolute", right: 12, bottom: 12, zIndex: 80, width: 238, maxHeight: "calc(100% - 24px)", overflow: "auto", padding: 10, border: "1px solid var(--line-cy)", background: "var(--panel)", boxShadow: "0 14px 42px rgba(0,0,0,.65)" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <strong style={{ flex: 1, fontFamily: "'Chakra Petch'", fontSize: 10, letterSpacing: ".1em" }}>{selection?.kind.toUpperCase()} INSPECTOR</strong>
                <button type="button" aria-label="Close Canvas Plot inspector" disabled={Boolean(busy)} onClick={() => void chooseSelection(null)} style={toolbarButton}>×</button>
              </div>
              {(selectedNode || selectedFrame) && <input aria-label={`${selectedNode ? "Block" : "Frame"} title`} value={edit.title} disabled={disabled} onChange={(event) => changeEdit({ title: event.currentTarget.value })} style={field} />}
              {selectedNode && <textarea aria-label="Block summary" value={edit.body} disabled={disabled} onChange={(event) => changeEdit({ body: event.currentTarget.value })} rows={4} style={{ ...field, resize: "vertical", marginTop: 6 }} />}
              {selectedNode && <input aria-label="Block category" value={edit.groupLabel} disabled={disabled} onChange={(event) => changeEdit({ groupLabel: event.currentTarget.value })} placeholder="category" style={{ ...field, marginTop: 6 }} />}
              {selectedLink && <input aria-label="Connection label" value={edit.label} disabled={disabled} onChange={(event) => changeEdit({ label: event.currentTarget.value })} placeholder="connection label" style={field} />}
              {selectedLink && <input aria-label="Connection type" value={edit.linkType} disabled={disabled} onChange={(event) => changeEdit({ linkType: event.currentTarget.value })} placeholder="type: cause, echo…" style={{ ...field, marginTop: 6 }} />}
              <select aria-label={`${selection?.kind} color`} value={edit.colorLabel} disabled={disabled} onChange={(event) => changeEdit({ colorLabel: event.currentTarget.value })} style={{ ...field, marginTop: 6 }}><ColorOptions current={edit.colorLabel} /></select>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                <button type="submit" disabled={disabled} style={{ ...toolbarButton, color: "var(--green)", borderColor: "var(--green)" }}>SAVE</button>
                <button type="button" disabled={disabled || !inspectorDirty} onClick={revertInspector} style={toolbarButton}>REVERT</button>
                {selectedNode && <button type="button" disabled={disabled || nodes.length < 2} onClick={() => void runIntent({ kind: "update_node", nodeId: selectedNode.id, index: nodes.length - 1 })} style={toolbarButton}>FRONT</button>}
                {selectedNode && <button type="button" disabled={disabled || nodes.length < 2} onClick={() => void runIntent({ kind: "update_node", nodeId: selectedNode.id, index: 0 })} style={toolbarButton}>BACK</button>}
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    const key = selectedNode ? `node:${selectedNode.id}` : selectedLink ? `link:${selectedLink.id}` : `frame:${selectedFrame!.id}`;
                    if (confirmDelete !== key) { setConfirmDelete(key); return; }
                    if (selectedNode) void runIntent({ kind: "delete_node", nodeId: selectedNode.id });
                    else if (selectedLink) void runIntent({ kind: "delete_link", linkId: selectedLink.id });
                    else if (selectedFrame) void runIntent({ kind: "delete_frame", frameId: selectedFrame.id });
                  }}
                  style={{ ...toolbarButton, color: "var(--crimson)", borderColor: "var(--crimson)" }}
                >{confirmDelete === selectedKey ? "CONFIRM DELETE" : "DELETE"}</button>
              </div>
              {selectedNode && <div style={{ marginTop: 7, color: "var(--txt3)", fontSize: 7 }}>Arrow keys on the move/resize handles adjust by 10 units; hold Shift for 1.</div>}
            </form>
          )}
        </div>
      </div>
    </PanelShell>
  );
}
