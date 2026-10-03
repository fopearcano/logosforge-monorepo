import { useCallback, useState, type CSSProperties, type ReactNode } from "react";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio, useNavigate } from "../../adapters/StudioProvider";
import { useManuscriptSnapshot, useStoryStructure } from "../../hooks";
import {
  flushPendingProjectSaves,
  trackProjectWrite,
} from "../../adapters/projectSaveCoordinator";
import { ApiRequestError } from "../../adapters/httpApiClient";
import { planAppendSceneCommand } from "./structureAuthoring";

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

function Card({ left, leftDashed = false, code, codeColor = "var(--txt3)", status, statusColor, statusBorder, flag, title, titleColor = "var(--strong)", desc, dots, meta, energy, active = false, onClick }: {
  left: string; leftDashed?: boolean; code: string; codeColor?: string;
  status?: string; statusColor?: string; statusBorder?: string; flag?: string;
  title: string; titleColor?: string; desc: ReactNode; dots?: ReactNode; meta?: string; energy?: string; active?: boolean; onClick?: () => void;
}) {
  const border = active ? "1px solid var(--accent)" : flag ? "1px solid rgba(255,82,96,.4)" : "1px solid var(--line2)";
  const bg = active ? "rgba(76,194,255,.1)" : flag ? "rgba(255,82,96,.05)" : "var(--tint)";
  return (
    <button type="button" onClick={onClick} disabled={!onClick} title={onClick ? "Open in the Manuscript editor" : undefined} style={{ position: "relative", width: "100%", textAlign: "left", font: "inherit", color: "inherit", border, borderLeft: `3px ${leftDashed ? "dashed" : "solid"} ${left}`, background: bg, padding: "9px 10px", boxShadow: active ? "0 0 16px rgba(76,194,255,.18)" : undefined, cursor: onClick ? "pointer" : undefined }}>
      {flag && <span style={{ position: "absolute", top: 7, right: 9, fontSize: 7, color: "var(--blocking)", letterSpacing: ".1em" }}>⚑ {flag}</span>}
      <span style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 5 }}>
        <span style={{ fontSize: 8, color: codeColor }}>{code}</span>
        {status && <span style={{ fontSize: 7.5, letterSpacing: ".1em", color: statusColor, border: `1px solid ${statusBorder}`, padding: "1px 5px" }}>{status}</span>}
      </span>
      <span style={{ display: "block", fontSize: 11, color: titleColor, fontFamily: "'Chakra Petch'", letterSpacing: ".03em", marginBottom: 3 }}>{title}</span>
      <span style={{ display: "block", fontSize: 9, color: "var(--txt2)", lineHeight: 1.4, marginBottom: dots || meta || energy ? 7 : 0 }}>{desc}</span>
      {(dots || meta) && (
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ display: "flex", gap: 3 }}>{dots}</span>
          {meta && <span style={{ fontSize: 7.5, color: "var(--txt3)", marginLeft: "auto" }}>{meta}</span>}
        </span>
      )}
      {energy && <span style={{ display: "block", height: 3, marginTop: 6, background: energy, opacity: 0.7 }} />}
    </button>
  );
}

function Column({ act, meta, children }: { act: string; meta: string; children: ReactNode }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", borderBottom: "1px solid var(--line2)", paddingBottom: 7, marginBottom: 10 }}>
        <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 12, letterSpacing: ".16em", color: "var(--accent)" }}>{act}</span>
        <span style={{ fontSize: 8, color: "var(--txt3)" }}>{meta}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 9, overflowY: "auto" }}>{children}</div>
    </div>
  );
}

const message = (text: string) => (
  <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** A scene with no prose yet reads as DRAFT; otherwise it's been EDITED. */
function sceneStatus(s: SceneDTO): { status: string; statusColor: string; statusBorder: string } {
  return s.content.trim()
    ? { status: "EDITED", statusColor: "var(--cyan)", statusBorder: "var(--line-cy)" }
    : { status: "DRAFT", statusColor: "var(--txt3)", statusBorder: "var(--line2)" };
}

/** Group scenes by their `act`, keeping acts in first-seen (sort) order. */
function byAct(scenes: SceneDTO[]): { act: string; scenes: SceneDTO[] }[] {
  const order: string[] = [];
  const groups = new Map<string, SceneDTO[]>();
  for (const s of scenes) {
    const act = s.act || "UNGROUPED";
    let bucket = groups.get(act);
    if (!bucket) {
      bucket = [];
      groups.set(act, bucket);
      order.push(act);
    }
    bucket.push(s);
  }
  return order.map((act) => ({ act, scenes: groups.get(act) ?? [] }));
}

export function StoryGrid(props: PanelProps) {
  const { api, projectId, writingMode } = useStudio();
  const navigate = useNavigate();
  const manuscriptResource = useManuscriptSnapshot();
  const structureResource = useStoryStructure();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const snapshot = manuscriptResource.data?.project_id === projectId
    ? manuscriptResource.data
    : undefined;
  // The manuscript snapshot is already flattened in canonical structure order.
  const ordered = snapshot?.scenes ?? [];
  const columns = byAct(ordered);
  const loading = manuscriptResource.loading || structureResource.loading;
  const error = manuscriptResource.error ?? structureResource.error;

  const refresh = useCallback(() => {
    manuscriptResource.refetch();
    structureResource.refetch();
  }, [manuscriptResource.refetch, structureResource.refetch]);

  const addScene = useCallback(async () => {
    if (projectId == null || busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await flushPendingProjectSaves();
      const latest = await api.getStoryStructure(projectId);
      if (latest.project_id !== projectId) throw new Error("The story structure belongs to another project.");
      await trackProjectWrite(api.executeStoryStructureCommand(
        projectId,
        planAppendSceneCommand(
          latest,
          `Scene ${latest.scene_count + 1}`,
          String(writingMode ?? "").toLocaleLowerCase() === "series",
        ),
      ));
      refresh();
    } catch (error) {
      refresh();
      const detail = error instanceof ApiRequestError && error.code === "structure_conflict"
        ? "The story structure changed elsewhere. It has been refreshed; review it and try again."
        : error instanceof Error ? error.message : String(error);
      setActionError(`Couldn't create the scene — ${detail}`);
    } finally {
      setBusy(false);
    }
  }, [api, busy, projectId, refresh, writingMode]);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Story Grid" style={panelBox}>
        <Corners />
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 13, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>STORY GRID</span>
          <span style={{ fontSize: 9, color: "var(--txt3)", letterSpacing: ".1em" }}>GROUPED BY ACT</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".06em" }}>DRAFT · EDITED</span>
          <button type="button" onClick={addScene} disabled={busy || projectId == null} style={{ fontSize: 9, color: "var(--on-accent)", background: "var(--accent)", padding: "5px 11px", fontWeight: 600, letterSpacing: ".08em", border: "none", cursor: busy ? "default" : "pointer", opacity: busy || projectId == null ? 0.5 : 1 }}>＋ SCENE</button>
        </div>
        {actionError && <button type="button" role="alert" title="Dismiss" onClick={() => setActionError(null)} style={{ flex: "none", width: "100%", textAlign: "left", border: "none", borderBottom: "1px solid var(--crimson)", background: "rgba(255,82,96,.08)", color: "var(--crimson)", padding: "7px 16px", font: "inherit", fontSize: 9.5, cursor: "pointer" }}>{actionError}</button>}
        <div style={{ flex: 1, display: "flex", gap: 14, padding: "14px 16px", minHeight: 0 }}>
          {loading
            ? message("Loading scenes…")
            : error
              ? message(`Couldn't load scenes — ${error}`)
              : ordered.length === 0
                ? message("No scenes yet — add one with ＋ SCENE")
                : columns.map(({ act, scenes: acts }) => (
                    <Column key={act} act={act} meta={`${acts.length} SC`}>
                      {acts.map((s) => {
                        const { status, statusColor, statusBorder } = sceneStatus(s);
                        return (
                          <Card
                            key={s.id}
                            left={s.color_label || "var(--line2)"}
                            code={s.chapter || `#${s.sort_order}`}
                            status={status}
                            statusColor={statusColor}
                            statusBorder={statusBorder}
                            title={s.title}
                            desc={s.summary}
                            onClick={() => navigate("Manuscript", { sceneId: s.id })}
                          />
                        );
                      })}
                    </Column>
                  ))}
        </div>
      </div>
    </PanelShell>
  );
}
