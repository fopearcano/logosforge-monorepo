import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import type {
  TimelineEventDTO,
  TimelineLaneDTO,
  TimelineSnapshotDTO,
} from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { useMountedRef, useTimeline } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { ApiRequestError } from "../../adapters/httpApiClient";
import {
  flushPendingProjectSaves,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import {
  describeTimelineIntent,
  moveTimelineEventIntent,
  planTimelineCommand,
  timelineIntentCanRetry,
  type TimelineCommandIntent,
} from "./timelineTransactions";

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
    <div style={{ position: "absolute", left, top: 8, width: CARD_W, height: 78, border: `1px solid ${border}`, background, padding: "5px 7px", overflow: "hidden", boxSizing: "border-box" }}>
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
  const projectIdRef = useRef(projectId);
  projectIdRef.current = projectId;
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

  useEffect(() => {
    requestRef.current = null;
    setBusy("");
    setCommandSnapshot(null);
    setMutationError("");
    setStatus("");
    setRetryIntent(null);
    setNewLane("");
    setLaneNames({});
    setOffTimelineId("");
    setConfirmLaneId(null);
    setConfirmRemoveId(null);
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
  }, [timeline]);

  useEffect(() => {
    if (offTimelineId && timeline && !timeline.off_timeline.some((scene) => String(scene.id) === offTimelineId)) {
      setOffTimelineId("");
    }
  }, [timeline, offTimelineId]);

  const runIntent = useCallback(async (intent: TimelineCommandIntent) => {
    const ownerProjectId = projectIdRef.current;
    if (ownerProjectId == null || requestRef.current != null) return;
    const token = {};
    requestRef.current = token;
    setBusy(intent.kind);
    setMutationError("");
    setStatus("Saving Timeline change…");
    try {
      await flushPendingProjectSaves({ commitActiveField: true });
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      const latest = await api.getTimeline(ownerProjectId);
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
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
      const result = await trackProjectWrite(
        api.executeTimelineCommand(ownerProjectId, planned.command),
      );
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      if (result.timeline.project_id !== ownerProjectId) throw new Error("The updated Timeline belongs to another project.");
      setCommandSnapshot(result.timeline);
      setRetryIntent(null);
      setMutationError("");
      if (intent.kind === "create_lane") setNewLane("");
      setStatus(result.changed ? "Timeline change saved." : "Timeline already matched that change.");
      refetch();
    } catch (failure) {
      if (!mounted.current || requestRef.current !== token || projectIdRef.current !== ownerProjectId) return;
      const conflict = failure instanceof ApiRequestError
        && (failure.code === "timeline_conflict" || failure.status === 409);
      const retryable = conflict && timelineIntentCanRetry(intent);
      setRetryIntent(retryable ? intent : null);
      setMutationError(conflict
        ? retryable
          ? `The Timeline changed before this action could be saved. Review the refreshed board, then retry: ${describeTimelineIntent(intent)}.`
          : "The Timeline changed before this destructive action could be saved. Review the refreshed board and confirm the action again."
        : `Couldn't update the Timeline — ${failure instanceof Error ? failure.message : String(failure)}`);
      setStatus("");
      refetch();
    } finally {
      if (mounted.current && requestRef.current === token && projectIdRef.current === ownerProjectId) {
        requestRef.current = null;
        setBusy("");
      }
    }
  }, [api, mounted, refetch]);

  const events = timeline?.events ?? [];
  const lanes = timeline?.lanes ?? [];
  const maxOrder = Math.max(events.length, 1);
  const boardWidth = LABEL_W + maxOrder * STEP + 90;
  const xOf = (event: TimelineEventDTO) => (event.order_index - 1) * STEP + 8;
  const disabled = Boolean(busy) || loading || projectId == null || !timeline;

  const renderEvent = (event: TimelineEventDTO, color: string, background: string) => {
    const index = events.findIndex((item) => item.id === event.id);
    const laneId = event.lane_id;
    const removing = confirmRemoveId === event.id;
    return (
      <Card key={event.id} left={xOf(event)} border={color} background={background}>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <button
            type="button"
            onClick={() => setSelection({ sceneId: event.id, text: "", section: "Timeline", nodeId: event.id })}
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
        <div style={{ fontSize: 6.5, color: "var(--txt3)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 3 }}>
          {[event.act, event.chapter].filter(Boolean).join(" · ") || "Unassigned structure"}
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
      </Card>
    );
  };

  const unassigned = events.filter((event) => event.lane_id == null);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Plot-Lane Timeline" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />

        <div style={{ minHeight: 42, flex: "none", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, padding: "5px 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>PLOT · TIMELINE</span>
          <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{events.length} EVENTS · {lanes.length} LANES</span>
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
            {mutationError && <button type="button" onClick={() => { setMutationError(""); setRetryIntent(null); }} style={control}>DISMISS</button>}
          </div>
        )}

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
              : lanes.length === 0 && events.length === 0
                ? message("No Timeline yet — create a plot lane or add an existing scene")
                : (
                  <div style={{ flex: 1, overflow: "auto" }}>
                    <div style={{ width: boardWidth, minWidth: boardWidth }}>
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
                            height={lane.collapsed ? 46 : 96}
                            color={palette.color}
                            background={palette.bg}
                            header={(
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                  <button type="button" disabled={disabled} aria-label={`${lane.collapsed ? "Expand" : "Collapse"} ${lane.name}`} aria-expanded={!lane.collapsed} onClick={() => void runIntent({ kind: "update_lane", laneId: lane.id, collapsed: !lane.collapsed })} style={{ ...control, padding: "1px 4px", color: palette.color }}>{lane.collapsed ? "▸" : "▾"}</button>
                                  <input aria-label={`Name for lane ${lane.name}`} disabled={disabled} value={name} onChange={(event) => setLaneNames((current) => ({ ...current, [lane.id]: event.currentTarget.value }))} onKeyDown={(event) => {
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
                          height={96}
                          color="var(--txt3)"
                          background="var(--tint2)"
                          header={<div><div style={{ fontFamily: "'Chakra Petch'", fontSize: 9, letterSpacing: ".06em" }}>UNASSIGNED EVENTS</div><div style={{ fontSize: 7, marginTop: 5 }}>{unassigned.length} ev · no persisted lane</div></div>}
                        >
                          {unassigned.map((event) => renderEvent(event, "var(--line2)", "var(--tint2)"))}
                        </Lane>
                      )}
                    </div>
                  </div>
                )}
      </div>
    </PanelShell>
  );
}
