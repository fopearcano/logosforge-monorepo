import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import type {
  TimelineCommandDTO,
  TimelineEventDTO,
  TimelineLaneDTO,
  TimelineLinkType,
  TimelineSnapshotDTO,
  TimelineStructureTargetType,
} from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { useMountedRef, useTimeline } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { ApiRequestError, ApiRequestTimeoutError } from "../../adapters/httpApiClient";
import {
  flushPendingProjectSaves,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import {
  describeTimelineIntent,
  createTimelineIdempotencyKey,
  moveTimelineEventIntent,
  planTimelineCommand,
  TIMELINE_LINK_TYPES,
  timelineIntentCanRetry,
  type TimelineCommandIntent,
} from "./timelineTransactions";
import {
  TimelineModeProjection,
  TimelineStoryFlow,
} from "./TimelineModeProjection";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "linear-gradient(180deg,var(--panel),var(--base))",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const STEP = 184;
const LABEL_W = 180;
const CARD_W = 166;
const OPEN_LANE_H = 112;
const COLLAPSED_LANE_H = 46;

const COLORS = [
  { key: "", label: "Auto", color: "var(--cyan)", bg: "rgba(76,194,255,.05)" },
  { key: "cyan", label: "Cyan", color: "var(--cyan)", bg: "rgba(76,194,255,.05)" },
  { key: "green", label: "Green", color: "var(--green)", bg: "rgba(98,217,154,.05)" },
  { key: "amber", label: "Amber", color: "var(--amber)", bg: "rgba(245,177,51,.05)" },
  { key: "crimson", label: "Crimson", color: "var(--crimson)", bg: "rgba(232,68,58,.05)" },
  { key: "red", label: "Red", color: "var(--crimson)", bg: "rgba(232,68,58,.05)" },
  { key: "violet", label: "Violet", color: "var(--violet)", bg: "rgba(176,124,255,.05)" },
  { key: "purple", label: "Purple", color: "var(--violet)", bg: "rgba(176,124,255,.05)" },
  { key: "teal", label: "Teal", color: "var(--cyan)", bg: "rgba(76,194,255,.05)" },
  { key: "blue", label: "Blue", color: "#79a7ff", bg: "rgba(121,167,255,.06)" },
  { key: "gray", label: "Gray", color: "var(--txt3)", bg: "var(--tint2)" },
] as const;

const fallbackColors = [COLORS[1], COLORS[2], COLORS[3], COLORS[4], COLORS[6], COLORS[9]];

function laneColor(lane: TimelineLaneDTO, index: number) {
  return COLORS.find((item) => item.key === lane.color_label)
    ?? fallbackColors[index % fallbackColors.length]
    ?? COLORS[0];
}

function relationshipColor(colorLabel: string): string {
  return COLORS.find((item) => item.key === colorLabel)?.color ?? "var(--amber)";
}

function isAmbiguousTimelineFailure(failure: unknown): boolean {
  if (failure instanceof ApiRequestTimeoutError) return failure.outcomeUnknown;
  if (failure instanceof ApiRequestError) {
    return failure.status >= 500 || failure.status === 408 || failure.status === 429;
  }
  return true;
}

function isTimelineReceiptMiss(failure: unknown): boolean {
  return failure instanceof ApiRequestError
    && failure.code === "timeline_receipt_not_found";
}

interface PendingTimelineDelivery {
  ownerProjectId: number;
  intent: TimelineCommandIntent;
  command: TimelineCommandDTO;
  idempotencyKey: string;
  resendAttempted: boolean;
  receiptOnly: boolean;
}

interface LinkDraft {
  linkType: TimelineLinkType;
  colorLabel: string;
  label: string;
}

interface StructureDraft {
  targetType: TimelineStructureTargetType;
  targetRef: string;
}

const EMPTY_LINK_DRAFT: LinkDraft = {
  linkType: "causality",
  colorLabel: "amber",
  label: "",
};

const EMPTY_STRUCTURE_DRAFT: StructureDraft = {
  targetType: "act",
  targetRef: "",
};

const control: CSSProperties = {
  font: "inherit",
  fontSize: 8,
  color: "var(--txt2)",
  border: "1px solid var(--line2)",
  background: "var(--tint)",
  padding: "3px 6px",
};

const activeControl: CSSProperties = {
  ...control,
  color: "var(--strong)",
  borderColor: "var(--accent)",
  cursor: "pointer",
};

const input: CSSProperties = {
  ...control,
  color: "var(--txt)",
  outline: "none",
  minWidth: 0,
};

function Lane({
  height,
  color,
  background,
  header,
  children,
}: {
  height: number;
  color: string;
  background: string;
  header: ReactNode;
  children: ReactNode;
}) {
  return (
    <div style={{ display: "flex", height, borderBottom: "1px solid var(--line2)" }}>
      <div style={{ width: LABEL_W, flex: "none", borderRight: "1px solid var(--line2)", padding: "7px 8px", background, boxSizing: "border-box", color }}>
        {header}
      </div>
      <div style={{ flex: 1, position: "relative", background }}>{children}</div>
    </div>
  );
}

function Card({ left, border, background, children }: {
  left: number;
  border: string;
  background: string;
  children: ReactNode;
}) {
  return (
    <div style={{ position: "absolute", left, top: 8, zIndex: 3, width: CARD_W, height: 96, border: `1px solid ${border}`, background, padding: "5px 7px", overflow: "hidden", boxSizing: "border-box" }}>
      {children}
    </div>
  );
}

const message = (text: string) => (
  <div style={{ flex: 1, display: "grid", placeItems: "center", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function TimelinePanel(props: PanelProps) {
  const { data, loading, error, refetch } = useTimeline();
  const { api, projectId } = useStudio();
  const { setSelection } = useSelection();
  const mounted = useMountedRef();
  const apiRef = useRef(api);
  apiRef.current = api;
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
  const displayedProjectIdRef = useRef(projectId);
  const requestRef = useRef<object | null>(null);
  const [commandSnapshot, setCommandSnapshot] = useState<TimelineSnapshotDTO | null>(null);
  const [busy, setBusy] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [status, setStatus] = useState("");
  const [retryIntent, setRetryIntent] = useState<TimelineCommandIntent | null>(null);
  const [newLane, setNewLane] = useState("");
  const [laneNames, setLaneNames] = useState<Record<number, string>>({});
  const [offTimelineId, setOffTimelineId] = useState("");
  const [confirmLaneId, setConfirmLaneId] = useState<number | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<number | null>(null);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [showAllLinks, setShowAllLinks] = useState(false);
  const [showFlow, setShowFlow] = useState(true);
  const [pendingSourceId, setPendingSourceId] = useState<number | null>(null);
  const [linkDraft, setLinkDraft] = useState<LinkDraft>(EMPTY_LINK_DRAFT);
  const [editingLinkId, setEditingLinkId] = useState<number | null>(null);
  const [linkEditDraft, setLinkEditDraft] = useState<LinkDraft>(EMPTY_LINK_DRAFT);
  const [confirmLinkId, setConfirmLinkId] = useState<number | null>(null);
  const [structureDraft, setStructureDraft] = useState<StructureDraft>(EMPTY_STRUCTURE_DRAFT);
  const [editingStructureLinkId, setEditingStructureLinkId] = useState<number | null>(null);
  const [structureEditDraft, setStructureEditDraft] = useState<StructureDraft>(EMPTY_STRUCTURE_DRAFT);
  const [confirmStructureLinkId, setConfirmStructureLinkId] = useState<number | null>(null);
  const [pendingDelivery, setPendingDelivery] = useState<PendingTimelineDelivery | null>(null);
  const pendingDeliveryRef = useRef<PendingTimelineDelivery | null>(null);
  const pendingDeliveriesRef = useRef(new Map<number, PendingTimelineDelivery>());
  const replacePendingDelivery = useCallback((
    next: PendingTimelineDelivery | null,
    ownerProjectId = next?.ownerProjectId ?? projectIdRef.current,
  ) => {
    if (ownerProjectId != null) {
      if (next) pendingDeliveriesRef.current.set(ownerProjectId, next);
      else pendingDeliveriesRef.current.delete(ownerProjectId);
    }
    if (ownerProjectId == null || projectIdRef.current === ownerProjectId) {
      pendingDeliveryRef.current = next;
      setPendingDelivery(next);
    }
  }, []);

  useEffect(() => {
    const previousProjectId = displayedProjectIdRef.current;
    if (previousProjectId != null && previousProjectId !== projectId) {
      const unresolved = pendingDeliveriesRef.current.get(previousProjectId);
      if (unresolved) {
        pendingDeliveriesRef.current.set(previousProjectId, {
          ...unresolved,
          receiptOnly: true,
        });
      }
    }
    displayedProjectIdRef.current = projectId;
    const restoredDelivery = projectId == null
      ? null
      : pendingDeliveriesRef.current.get(projectId) ?? null;
    pendingDeliveryRef.current = restoredDelivery;
    setPendingDelivery(restoredDelivery);
    requestRef.current = null;
    setBusy("");
    setCommandSnapshot(null);
    setMutationError(restoredDelivery
      ? "This project has an unresolved Timeline delivery. Only its durable receipt may be checked; the original command will not be resent."
      : "");
    setStatus("");
    setRetryIntent(null);
    setNewLane("");
    setLaneNames({});
    setOffTimelineId("");
    setConfirmLaneId(null);
    setConfirmRemoveId(null);
    setSelectedEventId(null);
    setShowAllLinks(false);
    setShowFlow(true);
    setPendingSourceId(null);
    setLinkDraft(EMPTY_LINK_DRAFT);
    setEditingLinkId(null);
    setConfirmLinkId(null);
    setStructureDraft(EMPTY_STRUCTURE_DRAFT);
    setEditingStructureLinkId(null);
    setConfirmStructureLinkId(null);
  }, [projectId]);

  const timeline = commandSnapshot?.project_id === projectId
    ? commandSnapshot
    : data?.project_id === projectId
      ? data
      : undefined;

  useEffect(() => {
    if (!data || data.project_id !== projectId) return;
    setCommandSnapshot(data);
  }, [data, projectId]);

  useEffect(() => {
    if (!timeline) return;
    setLaneNames((current) => {
      const authoritative = new Map(timeline.lanes.map((lane) => [lane.id, lane.name]));
      const next = Object.fromEntries(Object.entries(current).filter(([rawId, draft]) => {
        const name = authoritative.get(Number(rawId));
        return name != null && draft !== name;
      }));
      return Object.keys(next).length === Object.keys(current).length
        && Object.entries(next).every(([id, draft]) => current[Number(id)] === draft)
        ? current
        : next;
    });
    setConfirmLaneId(null);
    setConfirmRemoveId(null);
    setConfirmLinkId(null);
    setConfirmStructureLinkId(null);
  }, [timeline]);

  useEffect(() => {
    if (!timeline) return;
    const active = new Set(timeline.events.map((event) => event.id));
    if (selectedEventId != null && !active.has(selectedEventId)) setSelectedEventId(null);
    if (pendingSourceId != null && !active.has(pendingSourceId)) setPendingSourceId(null);
    if (editingLinkId != null && !timeline.links.some((link) => link.id === editingLinkId)) {
      setEditingLinkId(null);
    }
    if (editingStructureLinkId != null
      && !timeline.structure_links.some((link) => link.id === editingStructureLinkId)) {
      setEditingStructureLinkId(null);
    }
  }, [editingLinkId, editingStructureLinkId, pendingSourceId, selectedEventId, timeline]);

  useEffect(() => {
    if (offTimelineId && timeline && !timeline.off_timeline.some((scene) => String(scene.id) === offTimelineId)) {
      setOffTimelineId("");
    }
  }, [timeline, offTimelineId]);

  const finishRelationshipIntent = useCallback((intent: TimelineCommandIntent) => {
    if (intent.kind === "create_link") {
      setPendingSourceId(null);
      setLinkDraft(EMPTY_LINK_DRAFT);
    } else if (intent.kind === "update_link") {
      setEditingLinkId(null);
    } else if (intent.kind === "delete_link") {
      setConfirmLinkId(null);
    } else if (intent.kind === "create_structure_link") {
      setStructureDraft(EMPTY_STRUCTURE_DRAFT);
    } else if (intent.kind === "update_structure_link") {
      setEditingStructureLinkId(null);
    } else if (intent.kind === "delete_structure_link") {
      setConfirmStructureLinkId(null);
    }
  }, []);

  const runIntent = useCallback(async (intent: TimelineCommandIntent) => {
    const ownerProjectId = projectIdRef.current;
    const ownerApi = apiRef.current;
    if (ownerProjectId == null || requestRef.current != null || pendingDeliveryRef.current != null) return;
    const token = {};
    requestRef.current = token;
    setBusy(intent.kind);
    setMutationError("");
    setStatus("Saving Timeline change…");
    const ownsRequest = () => mounted.current
      && requestRef.current === token
      && projectIdRef.current === ownerProjectId
      && apiRef.current === ownerApi;

    const publishResult = (result: Awaited<ReturnType<typeof ownerApi.executeTimelineCommand>>) => {
      if (!ownsRequest()) return;
      if (result.timeline.project_id !== ownerProjectId) {
        throw new Error("The updated Timeline belongs to another project.");
      }
      setCommandSnapshot(result.timeline);
      replacePendingDelivery(null);
      setRetryIntent(null);
      setMutationError("");
      if (intent.kind === "create_lane") setNewLane("");
      finishRelationshipIntent(intent);
      setStatus(result.replayed
        ? "Recovered the previously committed Timeline change."
        : result.changed
          ? "Timeline change saved."
          : "Timeline already matched that change.");
      refetch();
    };

    const publishReceipt = async (delivery: PendingTimelineDelivery, changed: boolean) => {
      replacePendingDelivery(null);
      setRetryIntent(null);
      finishRelationshipIntent(delivery.intent);
      try {
        ownerApi.invalidatePendingReads?.();
        const refreshed = await ownerApi.getTimeline(ownerProjectId);
        if (!ownsRequest()) return;
        if (refreshed.project_id !== ownerProjectId) {
          throw new Error("The recovered Timeline belongs to another project.");
        }
        setCommandSnapshot(refreshed);
        setMutationError("");
        setStatus(changed
          ? "Recovered the committed Timeline change from its durable receipt."
          : "The durable receipt confirms that the Timeline already matched that change.");
      } catch (refreshFailure) {
        if (!ownsRequest()) return;
        setStatus("");
        setMutationError(`The Timeline change was committed, but the board could not refresh — ${refreshFailure instanceof Error ? refreshFailure.message : String(refreshFailure)}. Reload the Timeline; do not repeat the change.`);
      } finally {
        if (ownsRequest()) refetch();
      }
    };

    const checkReceipt = async (delivery: PendingTimelineDelivery): Promise<"found" | "missing" | "uncertain"> => {
      try {
        const receipt = await ownerApi.getTimelineCommandReceipt(
          ownerProjectId,
          delivery.idempotencyKey,
          delivery.command,
        );
        if (!ownsRequest()) return "uncertain";
        await publishReceipt(delivery, receipt.original_changed);
        return "found";
      } catch (receiptFailure) {
        if (!ownsRequest()) return "uncertain";
        if (isTimelineReceiptMiss(receiptFailure)) return "missing";
        const locked = { ...delivery, receiptOnly: true };
        replacePendingDelivery(locked);
        setStatus("");
        setMutationError(`The write outcome could not be verified — ${receiptFailure instanceof Error ? receiptFailure.message : String(receiptFailure)}. Only receipt checks are now allowed; the Timeline will not resend this command.`);
        return "uncertain";
      }
    };

    try {
      await flushPendingProjectSaves({ commitActiveField: true });
      if (!ownsRequest()) return;
      ownerApi.invalidatePendingReads?.();
      const latest = await ownerApi.getTimeline(ownerProjectId);
      if (!ownsRequest()) return;
      if (latest.project_id !== ownerProjectId) throw new Error("The latest Timeline belongs to another project.");
      setCommandSnapshot(latest);
      const planned = planTimelineCommand(latest, intent);
      if (!planned.command) {
        setMutationError(planned.error);
        setStatus("");
        setRetryIntent(null);
        refetch();
        return;
      }
      let delivery: PendingTimelineDelivery = {
        ownerProjectId,
        intent,
        command: planned.command,
        idempotencyKey: createTimelineIdempotencyKey(),
        resendAttempted: false,
        receiptOnly: false,
      };
      replacePendingDelivery(delivery);
      try {
        const result = await trackProjectWrite(ownerApi.executeTimelineCommand(
          ownerProjectId,
          delivery.command,
          delivery.idempotencyKey,
        ));
        publishResult(result);
      } catch (failure) {
        if (!ownsRequest()) return;
        if (!isAmbiguousTimelineFailure(failure)) throw failure;
        setStatus("The write response was interrupted. Checking its durable receipt…");
        const receiptState = await checkReceipt(delivery);
        if (!ownsRequest() || receiptState !== "missing") return;

        delivery = { ...delivery, resendAttempted: true };
        replacePendingDelivery(delivery);
        setStatus("No receipt was found. Retrying the exact command once with the same key…");
        try {
          const result = await trackProjectWrite(ownerApi.executeTimelineCommand(
            ownerProjectId,
            delivery.command,
            delivery.idempotencyKey,
          ));
          publishResult(result);
        } catch (resendFailure) {
          if (!ownsRequest()) return;
          if (!isAmbiguousTimelineFailure(resendFailure)) throw resendFailure;
          setStatus("The one allowed resend was interrupted. Checking its durable receipt…");
          const secondReceiptState = await checkReceipt(delivery);
          if (!ownsRequest() || secondReceiptState === "found" || secondReceiptState === "uncertain") return;
          const locked = { ...delivery, receiptOnly: true };
          replacePendingDelivery(locked);
          setStatus("");
          setMutationError("No durable receipt is available yet after the one allowed same-key resend. Use CHECK RECEIPT; this command will not be sent again.");
          refetch();
        }
      }
    } catch (failure) {
      if (!ownsRequest()) return;
      replacePendingDelivery(null);
      const keyConflict = failure instanceof ApiRequestError
        && failure.code === "idempotency_key_conflict";
      const conflict = failure instanceof ApiRequestError
        && !keyConflict
        && (failure.code === "timeline_conflict" || failure.status === 409);
      const retryable = conflict && timelineIntentCanRetry(intent);
      setRetryIntent(retryable ? intent : null);
      setMutationError(conflict
        ? retryable
          ? `The Timeline changed before this action could be saved. Review the refreshed board, then retry: ${describeTimelineIntent(intent)}.`
          : "The Timeline changed before this destructive action could be saved. Review the refreshed board and confirm the action again."
        : keyConflict
          ? "The command key was already used for a different Timeline change. Review the board and try the action again."
          : `Couldn't update the Timeline — ${failure instanceof Error ? failure.message : String(failure)}`);
      setStatus("");
      refetch();
    } finally {
      if (mounted.current && requestRef.current === token && projectIdRef.current === ownerProjectId) {
        requestRef.current = null;
        setBusy("");
      }
    }
  }, [finishRelationshipIntent, mounted, refetch, replacePendingDelivery]);

  const checkPendingReceipt = useCallback(async () => {
    const delivery = pendingDeliveryRef.current;
    const ownerApi = apiRef.current;
    if (!delivery || requestRef.current != null || projectIdRef.current !== delivery.ownerProjectId) return;
    const token = {};
    requestRef.current = token;
    setBusy("check_receipt");
    setMutationError("");
    setStatus("Checking the durable Timeline receipt…");
    const ownsRequest = () => mounted.current
      && requestRef.current === token
      && projectIdRef.current === delivery.ownerProjectId
      && apiRef.current === ownerApi;
    const ownsDelivery = () => ownsRequest()
      && pendingDeliveryRef.current?.idempotencyKey === delivery.idempotencyKey;
    try {
      const receipt = await ownerApi.getTimelineCommandReceipt(
        delivery.ownerProjectId,
        delivery.idempotencyKey,
        delivery.command,
      );
      if (!ownsDelivery()) return;
      replacePendingDelivery(null);
      finishRelationshipIntent(delivery.intent);
      try {
        ownerApi.invalidatePendingReads?.();
        const refreshed = await ownerApi.getTimeline(delivery.ownerProjectId);
        if (!ownsRequest()) return;
        setCommandSnapshot(refreshed);
        setStatus(receipt.original_changed
          ? "Recovered the committed Timeline change from its durable receipt."
          : "The durable receipt confirms that the Timeline already matched that change.");
      } catch (refreshFailure) {
        if (!ownsRequest()) return;
        setStatus("");
        setMutationError(`The Timeline change was committed, but the board could not refresh — ${refreshFailure instanceof Error ? refreshFailure.message : String(refreshFailure)}. Reload the Timeline; do not repeat the change.`);
      }
      if (ownsRequest()) refetch();
    } catch (failure) {
      if (!ownsDelivery()) return;
      setStatus("");
      setMutationError(isTimelineReceiptMiss(failure)
        ? "No durable receipt is available yet. This command remains receipt-only and will not be resent."
        : `The receipt check failed — ${failure instanceof Error ? failure.message : String(failure)}. The command remains receipt-only.`);
    } finally {
      if (requestRef.current === token) {
        requestRef.current = null;
        if (mounted.current && projectIdRef.current === delivery.ownerProjectId) setBusy("");
      }
    }
  }, [finishRelationshipIntent, mounted, refetch, replacePendingDelivery]);

  const events = timeline?.events ?? [];
  const lanes = timeline?.lanes ?? [];
  const maxOrder = Math.max(events.length, 1);
  const boardWidth = LABEL_W + maxOrder * STEP + 90;
  const xOf = (event: TimelineEventDTO) => (event.order_index - 1) * STEP + 8;
  const disabled = Boolean(busy) || pendingDelivery != null || loading || projectId == null || !timeline;
  const selectedEvent = events.find((event) => event.id === selectedEventId) ?? null;
  const selectedLinks = timeline?.links.filter((link) => (
    link.source_scene_id === selectedEventId || link.target_scene_id === selectedEventId
  )) ?? [];
  const selectedStructureLinks = timeline?.structure_links.filter((link) => (
    link.source_scene_id === selectedEventId
  )) ?? [];
  const workspaceLinks = showAllLinks ? timeline?.links ?? [] : selectedLinks;
  const workspaceStructureLinks = showAllLinks
    ? timeline?.structure_links ?? []
    : selectedStructureLinks;
  const structureOptions = (targetType: TimelineStructureTargetType) => Array.from(new Set(
    [...events, ...(timeline?.off_timeline ?? [])]
      .map((scene) => targetType === "act" ? scene.act : scene.chapter)
      .filter((value) => value.trim()),
  )).sort((left, right) => left.localeCompare(right));

  const selectTimelineEvent = (event: TimelineEventDTO) => {
    setSelectedEventId(event.id);
    setShowAllLinks(false);
    setSelection({ sceneId: event.id, text: "", section: "Timeline", nodeId: event.id });
  };

  const beginLink = (event: TimelineEventDTO) => {
    selectTimelineEvent(event);
    setPendingSourceId(event.id);
    setEditingLinkId(null);
    setMutationError("");
    setStatus(`Choose a target event for a ${linkDraft.linkType.replaceAll("_", " ")} relationship.`);
  };

  const chooseLinkEndpoint = (event: TimelineEventDTO) => {
    if (pendingSourceId == null) {
      beginLink(event);
      return;
    }
    if (pendingSourceId === event.id) return;
    void runIntent({
      kind: "create_link",
      sourceSceneId: pendingSourceId,
      targetSceneId: event.id,
      linkType: linkDraft.linkType,
      colorLabel: linkDraft.colorLabel,
      label: linkDraft.label,
    });
  };

  const renderEvent = (event: TimelineEventDTO, color: string, background: string) => {
    const index = events.findIndex((item) => item.id === event.id);
    const laneId = event.lane_id;
    const removing = confirmRemoveId === event.id;
    const selected = selectedEventId === event.id;
    const pendingSource = pendingSourceId === event.id;
    const structureLinks = timeline?.structure_links.filter((link) => link.source_scene_id === event.id) ?? [];
    const flowPoint = timeline?.story_flow.points.find((point) => point.scene_id === event.id);
    return (
      <Card key={event.id} left={xOf(event)} border={selected || pendingSource ? "var(--amber)" : color} background={background}>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <button
            type="button"
            onClick={() => selectTimelineEvent(event)}
            aria-pressed={selected}
            title="Select this event for Timeline-aware tools"
            style={{ flex: 1, minWidth: 0, border: "none", background: "transparent", color: "var(--strong)", font: "inherit", fontSize: 8, lineHeight: 1.2, textAlign: "left", padding: 0, cursor: "pointer", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
          >
            {event.structural_number ? `${event.structural_number} · ` : ""}{event.title || "Untitled"}
          </button>
          <button
            type="button"
            disabled={disabled}
            aria-label={`${removing ? "Confirm removal of" : "Remove"} ${event.title || "Untitled"} from Timeline`}
            title="Remove from Timeline; the Scene and manuscript stay intact"
            onClick={() => {
              if (!removing) setConfirmRemoveId(event.id);
              else { setConfirmRemoveId(null); void runIntent({ kind: "remove_event", sceneId: event.id }); }
            }}
            style={{ ...control, padding: "1px 4px", color: "var(--crimson)", borderColor: "var(--crimson)", cursor: disabled ? "default" : "pointer" }}
          >{removing ? "OK" : "×"}</button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 3, minWidth: 0 }}>
          <span style={{ flex: 1, minWidth: 0, fontSize: 6.5, color: "var(--txt3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {[event.act, event.chapter].filter(Boolean).join(" · ") || "Unassigned structure"}
          </span>
          {showFlow && flowPoint && (
            <span
              aria-label={`Scene type for ${event.title || "Untitled"}: ${flowPoint.scene_type}`}
              title={`Scene type: ${flowPoint.scene_type}; dialogue ${Math.round(flowPoint.dialogue_ratio * 100)}%; action ${Math.round(flowPoint.action_ratio * 100)}%`}
              style={{ flex: "none", border: "1px solid var(--line2)", color: "var(--cyan)", padding: "1px 3px", fontSize: 5.8, letterSpacing: ".05em" }}
            >TYPE · {flowPoint.scene_type.toUpperCase()}</span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 5 }}>
          <button type="button" disabled={disabled || index <= 0} aria-label={`Move ${event.title || "event"} earlier`} onClick={() => {
            if (!timeline) return;
            const intent = moveTimelineEventIntent(timeline, event.id, -1);
            if (intent) void runIntent(intent);
          }} style={{ ...control, padding: "1px 4px", cursor: disabled || index <= 0 ? "default" : "pointer" }}>←</button>
          <button type="button" disabled={disabled || index >= events.length - 1} aria-label={`Move ${event.title || "event"} later`} onClick={() => {
            if (!timeline) return;
            const intent = moveTimelineEventIntent(timeline, event.id, 1);
            if (intent) void runIntent(intent);
          }} style={{ ...control, padding: "1px 4px", cursor: disabled || index >= events.length - 1 ? "default" : "pointer" }}>→</button>
          <select
            aria-label={`Lane for ${event.title || "Untitled"}`}
            disabled={disabled}
            value={laneId == null ? "" : String(laneId)}
            onChange={(change) => void runIntent({
              kind: "place_event",
              sceneId: event.id,
              laneId: change.currentTarget.value ? Number(change.currentTarget.value) : null,
            })}
            style={{ ...control, flex: 1, minWidth: 0, padding: "1px 3px" }}
          >
            <option value="">Unassigned</option>
            {lanes.map((lane) => <option key={lane.id} value={lane.id}>{lane.name}</option>)}
          </select>
        </div>
        <div style={{ display: "flex", gap: 5, marginTop: 4, fontSize: 6.5, color: "var(--txt3)" }}>
          {event.time_of_day && <span style={{ color: "var(--amber)" }}>{event.time_of_day}</span>}
          {event.location && <span title={event.location} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{event.location}</span>}
          {event.duration_minutes > 0 && <span>{event.duration_minutes}m</span>}
        </div>
        <div style={{ display: "flex", gap: 3, alignItems: "center", marginTop: 4, minWidth: 0 }}>
          <button
            type="button"
            disabled={disabled || (pendingSource && pendingSourceId != null)}
            aria-label={pendingSourceId == null
              ? `Start relationship from ${event.title || "Untitled"}`
              : pendingSource
                ? `${event.title || "Untitled"} is the relationship source`
                : `Use ${event.title || "Untitled"} as relationship target`}
            onClick={() => chooseLinkEndpoint(event)}
            style={{
              ...control,
              padding: "1px 4px",
              color: pendingSource ? "var(--amber)" : pendingSourceId != null ? "var(--green)" : "var(--cyan)",
              borderColor: pendingSource ? "var(--amber)" : undefined,
              cursor: disabled || pendingSource ? "default" : "pointer",
            }}
          >{pendingSource ? "SOURCE" : pendingSourceId != null ? "TARGET" : "LINK"}</button>
          <div aria-label={`Structure relationships for ${event.title || "Untitled"}`} style={{ display: "flex", gap: 2, overflow: "hidden", minWidth: 0 }}>
            {structureLinks.slice(0, 2).map((link) => (
              <span
                key={link.id}
                title={`${link.target_type}: ${link.target_ref}${link.target_exists ? "" : " (target missing)"}`}
                style={{ fontSize: 6, padding: "1px 3px", border: `1px solid ${link.target_exists ? "var(--line2)" : "var(--crimson)"}`, color: link.target_exists ? "var(--txt2)" : "var(--crimson)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >{link.target_exists ? "" : "⚠ "}{link.target_type === "act" ? "A" : "C"} · {link.target_ref}</span>
            ))}
            {structureLinks.length > 2 && <span style={{ fontSize: 6, color: "var(--txt3)" }}>+{structureLinks.length - 2}</span>}
          </div>
        </div>
      </Card>
    );
  };

  const unassigned = events.filter((event) => event.lane_id == null);
  const eventPoints = new Map<number, { x: number; y: number }>();
  let boardRowsHeight = 0;
  for (const lane of lanes) {
    const height = lane.collapsed ? COLLAPSED_LANE_H : OPEN_LANE_H;
    if (!lane.collapsed) {
      for (const event of events.filter((candidate) => candidate.lane_id === lane.id)) {
        eventPoints.set(event.id, { x: xOf(event) + CARD_W / 2, y: boardRowsHeight + height / 2 });
      }
    }
    boardRowsHeight += height;
  }
  if (unassigned.length > 0) {
    for (const event of unassigned) {
      eventPoints.set(event.id, { x: xOf(event) + CARD_W / 2, y: boardRowsHeight + OPEN_LANE_H / 2 });
    }
    boardRowsHeight += OPEN_LANE_H;
  }
  const visibleLinks = (timeline?.links ?? []).filter((link) => (
    eventPoints.has(link.source_scene_id) && eventPoints.has(link.target_scene_id)
  ));

  const relationshipWorkspace = timeline && (selectedEvent || pendingSourceId != null || showAllLinks) ? (
    <section aria-label="Timeline relationship editor" style={{ flex: "none", maxHeight: 188, overflow: "auto", padding: "7px 14px", borderBottom: "1px solid var(--line2)", background: "var(--base)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
        <strong style={{ fontFamily: "'Chakra Petch'", fontSize: 9, letterSpacing: ".08em", color: "var(--strong)" }}>
          {showAllLinks ? "ALL RELATIONSHIPS" : `RELATIONSHIPS · ${selectedEvent?.title || `SCENE #${pendingSourceId}`}`}
        </strong>
        {pendingSourceId != null && (
          <span style={{ fontSize: 7, color: "var(--amber)" }}>
            SOURCE SET · choose a TARGET card
          </span>
        )}
        <div style={{ flex: 1 }} />
        {pendingSourceId == null && selectedEvent && (
          <button type="button" disabled={disabled} onClick={() => beginLink(selectedEvent)} style={activeControl}>START LINK</button>
        )}
        {pendingSourceId != null && (
          <button type="button" disabled={Boolean(busy)} onClick={() => {
            setPendingSourceId(null);
            setStatus("");
          }} style={control}>CANCEL LINK</button>
        )}
        <button type="button" disabled={Boolean(busy)} aria-label="Close relationship editor" onClick={() => {
          setSelectedEventId(null);
          setShowAllLinks(false);
          setPendingSourceId(null);
          setEditingLinkId(null);
          setEditingStructureLinkId(null);
        }} style={control}>CLOSE</button>
      </div>

      {pendingSourceId != null && (
        <div style={{ display: "flex", gap: 5, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
          <label style={{ fontSize: 7, color: "var(--txt3)" }}>TYPE{" "}
            <select aria-label="New relationship type" disabled={disabled} value={linkDraft.linkType} onChange={(event) => {
              const linkType = event.currentTarget.value as TimelineLinkType;
              setLinkDraft((current) => ({ ...current, linkType }));
            }} style={control}>
              {TIMELINE_LINK_TYPES.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 7, color: "var(--txt3)" }}>COLOR{" "}
            <select aria-label="New relationship color" disabled={disabled} value={linkDraft.colorLabel} onChange={(event) => {
              const colorLabel = event.currentTarget.value;
              setLinkDraft((current) => ({ ...current, colorLabel }));
            }} style={control}>
              {COLORS.filter((item) => item.key).map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select>
          </label>
          <input aria-label="New relationship label" disabled={disabled} value={linkDraft.label} onChange={(event) => {
            const label = event.currentTarget.value;
            setLinkDraft((current) => ({ ...current, label }));
          }} placeholder="optional label…" style={{ ...input, width: 170 }} />
        </div>
      )}

      {(selectedEvent || showAllLinks) && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px,1fr) minmax(280px,1fr)", gap: 12, marginTop: 7 }}>
          <div>
            <div style={{ fontSize: 7, color: "var(--txt3)", letterSpacing: ".08em" }}>EVENT LINKS · {workspaceLinks.length}</div>
            {workspaceLinks.length === 0 && <div style={{ marginTop: 5, fontSize: 7, color: "var(--txt3)" }}>No event relationships yet.</div>}
            {workspaceLinks.map((link) => {
              const outgoing = selectedEvent == null || link.source_scene_id === selectedEvent.id;
              const otherId = outgoing ? link.target_scene_id : link.source_scene_id;
              const source = [...events, ...timeline.off_timeline].find((event) => event.id === link.source_scene_id);
              const target = [...events, ...timeline.off_timeline].find((event) => event.id === link.target_scene_id);
              const other = [...events, ...timeline.off_timeline].find((event) => event.id === otherId);
              const editing = editingLinkId === link.id;
              const deleting = confirmLinkId === link.id;
              return (
                <div key={link.id} style={{ marginTop: 4, padding: 5, border: "1px solid var(--line2)", borderLeft: `3px solid ${relationshipColor(link.color_label)}` }}>
                  {editing ? (
                    <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                      <select aria-label={`Type for relationship ${link.id}`} disabled={disabled} value={linkEditDraft.linkType} onChange={(event) => {
                        const linkType = event.currentTarget.value as TimelineLinkType;
                        setLinkEditDraft((current) => ({ ...current, linkType }));
                      }} style={control}>
                        {TIMELINE_LINK_TYPES.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
                      </select>
                      <select aria-label={`Color for relationship ${link.id}`} disabled={disabled} value={linkEditDraft.colorLabel} onChange={(event) => {
                        const colorLabel = event.currentTarget.value;
                        setLinkEditDraft((current) => ({ ...current, colorLabel }));
                      }} style={control}>
                        {linkEditDraft.colorLabel && !COLORS.some((item) => item.key === linkEditDraft.colorLabel) && <option value={linkEditDraft.colorLabel}>{linkEditDraft.colorLabel}</option>}
                        {COLORS.map((item) => <option key={item.key || "auto"} value={item.key}>{item.label}</option>)}
                      </select>
                      <input aria-label={`Label for relationship ${link.id}`} disabled={disabled} value={linkEditDraft.label} onChange={(event) => {
                        const label = event.currentTarget.value;
                        setLinkEditDraft((current) => ({ ...current, label }));
                      }} style={{ ...input, width: 120 }} />
                      <button type="button" disabled={disabled || !linkEditDraft.linkType.trim()} onClick={() => void runIntent({ kind: "update_link", linkId: link.id, ...linkEditDraft })} style={activeControl}>SAVE</button>
                      <button type="button" disabled={Boolean(busy)} onClick={() => setEditingLinkId(null)} style={control}>CANCEL</button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 7 }}>
                      <span style={{ color: relationshipColor(link.color_label), fontWeight: 700 }}>{link.link_type.replaceAll("_", " ")}</span>
                      <span style={{ color: "var(--txt2)", flex: 1 }}>
                        {showAllLinks
                          ? `${source?.title || `Scene #${link.source_scene_id}`} → ${target?.title || `Scene #${link.target_scene_id}`}`
                          : `${outgoing ? "→" : "←"} ${other?.title || `Scene #${otherId}`}`}
                        {link.label ? ` · ${link.label}` : ""}
                      </span>
                      <button type="button" disabled={disabled} aria-label={`Edit relationship ${link.id}`} onClick={() => {
                        setEditingLinkId(link.id);
                        setLinkEditDraft({ linkType: link.link_type, colorLabel: link.color_label, label: link.label });
                      }} style={control}>EDIT</button>
                      <button type="button" disabled={disabled} aria-label={`${deleting ? "Confirm deletion of" : "Delete"} relationship ${link.id}`} onClick={() => {
                        if (!deleting) setConfirmLinkId(link.id);
                        else void runIntent({ kind: "delete_link", linkId: link.id });
                      }} style={{ ...control, color: "var(--crimson)", borderColor: "var(--crimson)" }}>{deleting ? "CONFIRM" : "DEL"}</button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div>
            <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 7, color: "var(--txt3)", letterSpacing: ".08em" }}>STRUCTURE LINKS · {workspaceStructureLinks.length}</span>
              {selectedEvent && <select aria-label="New structure target type" disabled={disabled} value={structureDraft.targetType} onChange={(event) => {
                const targetType = event.currentTarget.value as TimelineStructureTargetType;
                setStructureDraft({ targetType, targetRef: "" });
              }} style={control}>
                <option value="act">Act</option><option value="chapter">Chapter</option>
              </select>}
              {selectedEvent && <select aria-label="New structure target" disabled={disabled} value={structureDraft.targetRef} onChange={(event) => {
                const targetRef = event.currentTarget.value;
                setStructureDraft((current) => ({ ...current, targetRef }));
              }} style={{ ...control, maxWidth: 150 }}>
                <option value="">choose {structureDraft.targetType}…</option>
                {structureOptions(structureDraft.targetType).map((value) => <option key={value} value={value}>{value}</option>)}
              </select>}
              {selectedEvent && <button type="button" aria-label="Add structure relationship" disabled={disabled || !structureDraft.targetRef} onClick={() => void runIntent({ kind: "create_structure_link", sourceSceneId: selectedEvent.id, targetType: structureDraft.targetType, targetRef: structureDraft.targetRef })} style={activeControl}>ADD</button>}
            </div>
            {workspaceStructureLinks.length === 0 && <div style={{ marginTop: 5, fontSize: 7, color: "var(--txt3)" }}>No act or chapter relationships yet.</div>}
            {workspaceStructureLinks.map((link) => {
              const editing = editingStructureLinkId === link.id;
              const deleting = confirmStructureLinkId === link.id;
              return (
                <div key={link.id} style={{ marginTop: 4, padding: 5, border: `1px solid ${link.target_exists ? "var(--line2)" : "var(--crimson)"}` }}>
                  {editing ? (
                    <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                      <select aria-label={`Target type for structure relationship ${link.id}`} disabled={disabled} value={structureEditDraft.targetType} onChange={(event) => {
                        const targetType = event.currentTarget.value as TimelineStructureTargetType;
                        setStructureEditDraft({ targetType, targetRef: "" });
                      }} style={control}>
                        <option value="act">Act</option><option value="chapter">Chapter</option>
                      </select>
                      <select aria-label={`Target for structure relationship ${link.id}`} disabled={disabled} value={structureEditDraft.targetRef} onChange={(event) => {
                        const targetRef = event.currentTarget.value;
                        setStructureEditDraft((current) => ({ ...current, targetRef }));
                      }} style={control}>
                        {!structureOptions(structureEditDraft.targetType).includes(structureEditDraft.targetRef) && structureEditDraft.targetRef && <option value={structureEditDraft.targetRef}>{structureEditDraft.targetRef} (missing)</option>}
                        <option value="">choose target…</option>
                        {structureOptions(structureEditDraft.targetType).map((value) => <option key={value} value={value}>{value}</option>)}
                      </select>
                      <button type="button" disabled={disabled || !structureEditDraft.targetRef} onClick={() => void runIntent({ kind: "update_structure_link", structureLinkId: link.id, targetType: structureEditDraft.targetType, targetRef: structureEditDraft.targetRef })} style={activeControl}>SAVE</button>
                      <button type="button" disabled={Boolean(busy)} onClick={() => setEditingStructureLinkId(null)} style={control}>CANCEL</button>
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: 5, alignItems: "center", fontSize: 7 }}>
                      <span style={{ color: link.target_exists ? "var(--txt2)" : "var(--crimson)", flex: 1 }}>
                        {showAllLinks ? `${[...events, ...timeline.off_timeline].find((event) => event.id === link.source_scene_id)?.title || `Scene #${link.source_scene_id}`} → ` : ""}
                        {link.target_exists ? "" : "⚠ DANGLING · "}{link.target_type.toUpperCase()} · {link.target_ref}
                      </span>
                      <button type="button" disabled={disabled} aria-label={`Edit structure relationship ${link.id}`} onClick={() => {
                        setEditingStructureLinkId(link.id);
                        setStructureEditDraft({ targetType: link.target_type, targetRef: link.target_ref });
                      }} style={control}>EDIT</button>
                      <button type="button" disabled={disabled} aria-label={`${deleting ? "Confirm deletion of" : "Delete"} structure relationship ${link.id}`} onClick={() => {
                        if (!deleting) setConfirmStructureLinkId(link.id);
                        else void runIntent({ kind: "delete_structure_link", structureLinkId: link.id });
                      }} style={{ ...control, color: "var(--crimson)", borderColor: "var(--crimson)" }}>{deleting ? "CONFIRM" : "DEL"}</button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  ) : null;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Plot-Lane Timeline" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />

        <div style={{ minHeight: 42, flex: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, padding: "5px 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>PLOT · TIMELINE</span>
          <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{events.length} EVENTS · {lanes.length} LANES</span>
          {timeline && (timeline.links.length > 0 || timeline.structure_links.length > 0) && (
            <button type="button" disabled={Boolean(busy)} aria-pressed={showAllLinks} onClick={() => {
              setShowAllLinks((current) => !current);
              setSelectedEventId(null);
              setPendingSourceId(null);
            }} style={{ ...control, color: showAllLinks ? "var(--amber)" : "var(--txt2)" }}>
              RELATIONSHIPS · {timeline.links.length + timeline.structure_links.length}
            </button>
          )}
          {timeline && (
            <button
              type="button"
              disabled={disabled}
              aria-pressed={timeline.order_mode === "custom"}
              title={timeline.order_mode === "custom" ? "Switch back to canonical manuscript order" : "Start an independent Timeline order"}
              onClick={() => void runIntent({ kind: "set_order_mode", mode: timeline.order_mode === "custom" ? "structural" : "custom" })}
              style={{ ...activeControl, color: timeline.order_mode === "custom" ? "var(--amber)" : "var(--txt2)", cursor: disabled ? "default" : "pointer" }}
            >ORDER · {timeline.order_mode.toUpperCase()}</button>
          )}
          {timeline && (
            <button
              type="button"
              aria-label="Toggle Timeline story flow"
              aria-pressed={showFlow}
              onClick={() => setShowFlow((current) => !current)}
              style={{ ...activeControl, color: showFlow ? "var(--cyan)" : "var(--txt3)" }}
            >FLOW · {showFlow ? "ON" : "OFF"}</button>
          )}
          <div style={{ flex: 1 }} />
          {timeline && timeline.off_timeline.length > 0 && (
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <select aria-label="Scene to add to Timeline" disabled={disabled} value={offTimelineId} onChange={(event) => setOffTimelineId(event.currentTarget.value)} style={{ ...control, maxWidth: 170 }}>
                <option value="">＋ {timeline.off_timeline.length} OFF TIMELINE</option>
                {timeline.off_timeline.map((scene) => <option key={scene.id} value={scene.id}>{scene.structural_number ? `${scene.structural_number} · ` : ""}{scene.title || "Untitled"}</option>)}
              </select>
              <button type="button" disabled={disabled || !offTimelineId} onClick={() => {
                const sceneId = Number(offTimelineId);
                void runIntent({ kind: "place_event", sceneId, laneId: null });
              }} style={{ ...activeControl, cursor: disabled || !offTimelineId ? "default" : "pointer" }}>ADD</button>
            </div>
          )}
          <form onSubmit={(event) => {
            event.preventDefault();
            if (!newLane.trim()) return;
            const name = newLane;
            void runIntent({ kind: "create_lane", name });
          }} style={{ display: "flex", gap: 4 }}>
            <input aria-label="New Timeline lane name" disabled={disabled} value={newLane} onChange={(event) => setNewLane(event.currentTarget.value)} placeholder="new plot lane…" style={{ ...input, width: 116 }} />
            <button type="submit" disabled={disabled || !newLane.trim()} style={{ ...activeControl, cursor: disabled || !newLane.trim() ? "default" : "pointer" }}>＋ LANE</button>
          </form>
        </div>

        {(mutationError || status) && (
          <div role={mutationError ? "alert" : "status"} aria-live="polite" style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 14px", borderBottom: "1px solid var(--line2)", color: mutationError ? "var(--crimson)" : "var(--green)", fontSize: 8 }}>
            <span style={{ flex: 1 }}>{mutationError || status}</span>
            {retryIntent && <button type="button" disabled={disabled} onClick={() => void runIntent(retryIntent)} style={activeControl}>RETRY</button>}
            {pendingDelivery?.receiptOnly && <button type="button" disabled={Boolean(busy)} onClick={() => void checkPendingReceipt()} style={activeControl}>CHECK RECEIPT</button>}
            {mutationError && <button type="button" onClick={() => { setMutationError(""); setRetryIntent(null); }} style={control}>DISMISS</button>}
          </div>
        )}

        {relationshipWorkspace}

        {loading
          ? message("Loading Timeline…")
          : error
            ? (
              <div role="alert" style={{ flex: 1, display: "grid", placeItems: "center", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>
                <div>
                  <div>{`Couldn't load Timeline — ${error}`}</div>
                  <button type="button" onClick={() => refetch()} style={{ ...activeControl, marginTop: 10 }}>RETRY LOAD</button>
                </div>
              </div>
            )
            : !timeline
              ? message("Timeline unavailable")
              : (
                <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
                  {lanes.length === 0 && events.length === 0
                    ? (
                      <>
                        <TimelineModeProjection projection={timeline.mode_projection} />
                        {message("No Timeline yet — create a plot lane or add an existing scene")}
                      </>
                    )
                    : (
                    <div data-timeline-board-scroll="true" style={{ flex: 1, overflow: "auto" }}>
                    <div style={{ width: boardWidth, minWidth: boardWidth }}>
                      {showFlow && (
                        <TimelineStoryFlow
                          flow={timeline.story_flow}
                          events={events}
                          labelWidth={LABEL_W}
                          step={STEP}
                          cardWidth={CARD_W}
                        />
                      )}
                      <TimelineModeProjection projection={timeline.mode_projection} />
                      <div style={{ position: "relative" }}>
                        <div style={{ height: 20, display: "flex", alignItems: "center", borderBottom: "1px solid var(--line2)", backgroundImage: `repeating-linear-gradient(90deg,transparent 0 ${STEP - 1}px,rgba(245,177,51,.35) ${STEP - 1}px ${STEP}px)`, backgroundPosition: `${LABEL_W}px 0`, paddingLeft: 14 }}>
                          <span style={{ fontSize: 7, letterSpacing: ".16em", color: "var(--txt3)" }}>STORY TIME → · MANUSCRIPT ORDER IS NEVER CHANGED HERE</span>
                        </div>
                      {lanes.map((lane, laneIndex) => {
                        const palette = laneColor(lane, laneIndex);
                        const laneEvents = events.filter((event) => event.lane_id === lane.id);
                        const name = laneNames[lane.id] ?? lane.name;
                        const deleting = confirmLaneId === lane.id;
                        return (
                          <Lane
                            key={lane.id}
                            height={lane.collapsed ? COLLAPSED_LANE_H : OPEN_LANE_H}
                            color={palette.color}
                            background={palette.bg}
                            header={(
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                  <button type="button" disabled={disabled} aria-label={`${lane.collapsed ? "Expand" : "Collapse"} ${lane.name}`} aria-expanded={!lane.collapsed} onClick={() => void runIntent({ kind: "update_lane", laneId: lane.id, collapsed: !lane.collapsed })} style={{ ...control, padding: "1px 4px", color: palette.color }}>{lane.collapsed ? "▸" : "▾"}</button>
                                  <input aria-label={`Name for lane ${lane.name}`} disabled={disabled} value={name} onChange={(event) => {
                                    const nextName = event.currentTarget.value;
                                    setLaneNames((current) => ({ ...current, [lane.id]: nextName }));
                                  }} onKeyDown={(event) => {
                                    if (event.key === "Enter" && name.trim() !== lane.name) void runIntent({ kind: "update_lane", laneId: lane.id, name });
                                  }} style={{ ...input, width: 82, color: palette.color }} />
                                  {name.trim() !== lane.name && <button type="button" disabled={disabled} aria-label={`Save lane name ${name}`} onClick={() => void runIntent({ kind: "update_lane", laneId: lane.id, name })} style={{ ...activeControl, padding: "2px 4px" }}>SAVE</button>}
                                </div>
                                {!lane.collapsed && (
                                  <div style={{ display: "flex", alignItems: "center", gap: 3, marginTop: 5 }}>
                                    <select aria-label={`Color for lane ${lane.name}`} disabled={disabled} value={lane.color_label} onChange={(event) => void runIntent({ kind: "update_lane", laneId: lane.id, colorLabel: event.currentTarget.value })} style={{ ...control, width: 64, padding: "1px 2px" }}>
                                      {lane.color_label && !COLORS.some((item) => item.key === lane.color_label) && (
                                        <option value={lane.color_label}>{lane.color_label}</option>
                                      )}
                                      {COLORS.map((item) => <option key={item.key || "auto"} value={item.key}>{item.label}</option>)}
                                    </select>
                                    <button type="button" disabled={disabled || laneIndex === 0} aria-label={`Move lane ${lane.name} up`} onClick={() => void runIntent({ kind: "move_lane", laneId: lane.id, delta: -1 })} style={{ ...control, padding: "1px 4px" }}>↑</button>
                                    <button type="button" disabled={disabled || laneIndex === lanes.length - 1} aria-label={`Move lane ${lane.name} down`} onClick={() => void runIntent({ kind: "move_lane", laneId: lane.id, delta: 1 })} style={{ ...control, padding: "1px 4px" }}>↓</button>
                                    <button type="button" disabled={disabled} aria-label={`${deleting ? "Confirm deletion of" : "Delete"} lane ${lane.name}`} title="Delete lane; its events stay on the Timeline as Unassigned" onClick={() => {
                                      if (!deleting) setConfirmLaneId(lane.id);
                                      else { setConfirmLaneId(null); void runIntent({ kind: "delete_lane", laneId: lane.id }); }
                                    }} style={{ ...control, padding: "1px 4px", color: "var(--crimson)", borderColor: "var(--crimson)" }}>{deleting ? "CONFIRM" : "DEL"}</button>
                                    <span style={{ marginLeft: "auto", fontSize: 6.5, color: "var(--txt3)" }}>{laneEvents.length} ev</span>
                                  </div>
                                )}
                              </div>
                            )}
                          >
                            {!lane.collapsed && laneEvents.map((event) => renderEvent(event, palette.color, palette.bg))}
                          </Lane>
                        );
                      })}
                      {unassigned.length > 0 && (
                        <Lane
                          height={OPEN_LANE_H}
                          color="var(--txt3)"
                          background="var(--tint2)"
                          header={<div><div style={{ fontFamily: "'Chakra Petch'", fontSize: 9, letterSpacing: ".06em" }}>UNASSIGNED EVENTS</div><div style={{ fontSize: 7, marginTop: 5 }}>{unassigned.length} ev · no persisted lane</div></div>}
                        >
                          {unassigned.map((event) => renderEvent(event, "var(--line2)", "var(--tint2)"))}
                        </Lane>
                      )}
                      {visibleLinks.length > 0 && (
                        <svg
                          aria-hidden="true"
                          width={boardWidth - LABEL_W}
                          height={boardRowsHeight}
                          viewBox={`0 0 ${boardWidth - LABEL_W} ${boardRowsHeight}`}
                          style={{ position: "absolute", left: LABEL_W, top: 20, zIndex: 2, overflow: "visible", pointerEvents: "none" }}
                        >
                          {visibleLinks.map((link) => {
                            const source = eventPoints.get(link.source_scene_id)!;
                            const target = eventPoints.get(link.target_scene_id)!;
                            const midX = (source.x + target.x) / 2;
                            const midY = source.y === target.y
                              ? source.y - 24 - (link.id % 3) * 6
                              : (source.y + target.y) / 2 - 10;
                            const color = relationshipColor(link.color_label);
                            const label = `${link.link_type.replaceAll("_", " ")} →${link.label ? ` · ${link.label}` : ""}`;
                            return (
                              <g key={link.id}>
                                <title>{label}</title>
                                <path d={`M ${source.x} ${source.y} Q ${midX} ${midY} ${target.x} ${target.y}`} fill="none" stroke={color} strokeWidth="1.5" strokeDasharray={link.link_type === "echo" ? "5 3" : undefined} opacity=".8" />
                                <circle cx={target.x} cy={target.y} r="3" fill={color} />
                                <text x={midX} y={midY - 3} fill={color} fontSize="7" textAnchor="middle">{label}</text>
                              </g>
                            );
                          })}
                        </svg>
                      )}
                      </div>
                    </div>
                  </div>
                    )}
                </div>
              )}
      </div>
    </PanelShell>
  );
}
