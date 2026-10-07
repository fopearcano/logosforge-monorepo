import type { CSSProperties } from "react";
import type {
  TimelineModeProjectionDTO,
  TimelinePacingWarningDTO,
  TimelineStoryFlowDTO,
  TimelineStoryFlowPointDTO,
} from "@logosforge/ui-contracts";

interface TimelineEventView {
  id: number;
  order_index: number;
  title: string;
}

const facetStyle: CSSProperties = {
  border: "1px solid var(--line2)",
  color: "var(--txt2)",
  padding: "2px 6px",
  whiteSpace: "nowrap",
};

function plural(count: number, singular: string, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`;
}

function uniqueNonEmpty(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function Facet({ children, title }: { children: string; title?: string }) {
  return <span title={title} style={facetStyle}>{children}</span>;
}

export function TimelineModeProjection({ projection }: { projection: TimelineModeProjectionDTO }) {
  let label = "NOVEL";
  let facets = <Facet>BASE PROSE LENS · manuscript scene rhythm</Facet>;

  if (projection.kind === "screenplay") {
    const settings = uniqueNonEmpty(projection.scenes.map((scene) => scene.interior_exterior));
    const pacing = uniqueNonEmpty(projection.scenes.map((scene) => scene.cinematic_pacing));
    const turns = projection.scenes.filter((scene) => (
      scene.dramatic_turn || scene.emotional_turn || scene.turning_point || scene.emotional_shift
    )).length;
    const objectives = projection.scenes.filter((scene) => scene.objective).length;
    const conflicts = projection.scenes.filter((scene) => scene.conflict).length;
    const visualBeats = projection.scenes.reduce((sum, scene) => sum + scene.visual_beat_count, 0);
    label = "SCREENPLAY";
    facets = <>
      <Facet>{plural(projection.scenes.length, "scene")}</Facet>
      <Facet>{plural(visualBeats, "visual beat")}</Facet>
      <Facet>{`${turns} turns · ${objectives} objectives · ${conflicts} conflicts`}</Facet>
      {settings.length > 0 && <Facet title={settings.join(", ")}>{`SETTINGS · ${settings.join(" / ")}`}</Facet>}
      {pacing.length > 0 && <Facet title={pacing.join(", ")}>{`PACING · ${pacing.join(" / ")}`}</Facet>}
    </>;
  } else if (projection.kind === "graphic_novel") {
    const panels = projection.pages.reduce((sum, page) => sum + page.panel_count, 0);
    const splashes = projection.pages.filter((page) => page.splash_page).length;
    const silentPages = projection.pages.filter((page) => page.is_silence).length;
    const actionPages = projection.pages.filter((page) => page.is_action).length;
    const rhythms = uniqueNonEmpty(projection.pages.map((page) => page.rhythm));
    label = "GRAPHIC NOVEL";
    facets = <>
      <Facet>{`${plural(projection.pages.length, "page")} · ${plural(panels, "panel")}`}</Facet>
      <Facet>{`${plural(splashes, "splash", "splashes")} · ${plural(projection.page_turns.length, "page-turn reveal")}`}</Facet>
      <Facet>{`${silentPages} silent · ${actionPages} action`}</Facet>
      {rhythms.length > 0 && <Facet title={rhythms.join(", ")}>{`RHYTHM · ${rhythms.join(" / ")}`}</Facet>}
    </>;
  } else if (projection.kind === "stage_script") {
    const entrances = projection.scenes.reduce((sum, scene) => (
      sum + scene.entrances_exits.filter((moment) => moment.type === "entrance").length
    ), 0);
    const exits = projection.scenes.reduce((sum, scene) => (
      sum + scene.entrances_exits.filter((moment) => moment.type === "exit").length
    ), 0);
    const cues = projection.scenes.reduce((sum, scene) => sum + scene.cues.length, 0);
    const props = new Set(projection.scenes.flatMap((scene) => scene.props)).size;
    const offstage = projection.scenes.filter((scene) => scene.has_offstage_events).length;
    const pressures = uniqueNonEmpty(projection.scenes.map((scene) => scene.emotional_pressure));
    label = "STAGE SCRIPT";
    facets = <>
      <Facet>{plural(projection.scenes.length, "stage scene")}</Facet>
      <Facet>{`${plural(entrances, "entrance")} · ${plural(exits, "exit", "exits")} · ${plural(cues, "cue")}`}</Facet>
      <Facet>{`${props} props · ${offstage} offstage events`}</Facet>
      {pressures.length > 0 && <Facet>{`PRESSURE · ${pressures.join(" / ")}`}</Facet>}
    </>;
  } else if (projection.kind === "series") {
    const arcIds = new Set(projection.episodes.flatMap((episode) => episode.active_arcs.map((arc) => arc.arc_id)));
    const cliffhangers = projection.episodes.filter((episode) => episode.cliffhanger).length;
    const setups = projection.episodes.reduce((sum, episode) => sum + episode.setup_arc_ids.length, 0);
    const payoffs = projection.episodes.reduce((sum, episode) => sum + episode.payoff_arc_ids.length, 0);
    label = "SERIES";
    facets = <>
      <Facet>{`${plural(projection.episodes.length, "episode")} · ${plural(arcIds.size, "active arc")}`}</Facet>
      <Facet>{`${plural(cliffhangers, "cliffhanger")} · ${plural(setups, "setup")} · ${plural(payoffs, "payoff")}`}</Facet>
      <Facet>{`${projection.arc_chains.length} arc chains · ${projection.unassigned_scene_ids.length} unassigned scenes`}</Facet>
    </>;
  }

  return (
    <aside
      aria-label="Timeline mode lens"
      style={{
        minHeight: 32,
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderBottom: "1px solid var(--line2)",
        background: "var(--tint2)",
        fontSize: 7,
        overflow: "hidden",
      }}
    >
      <strong style={{ color: "var(--violet)", letterSpacing: ".12em", whiteSpace: "nowrap" }}>MODE LENS · {label}</strong>
      <div style={{ display: "flex", gap: 4, alignItems: "center", overflow: "hidden" }}>{facets}</div>
    </aside>
  );
}

const warningText: Record<TimelinePacingWarningDTO["reason"], string> = {
  monotone_low: "LOW TENSION PLATEAU",
  monotone_high: "HIGH TENSION PLATEAU",
  no_variation: "NO TENSION VARIATION",
};

function flowLevel(value: number): string {
  if (value >= 8) return "peak";
  if (value >= 6) return "high";
  if (value >= 3.5) return "building";
  return "low";
}

function flowColor(value: number): string {
  if (value >= 8) return "rgba(232,68,58,.62)";
  if (value >= 6) return "rgba(245,177,51,.55)";
  if (value >= 3.5) return "rgba(176,124,255,.42)";
  return "rgba(76,194,255,.28)";
}

function ratioPercent(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}

export function TimelineStoryFlow({
  flow,
  events,
  labelWidth,
  step,
  cardWidth,
}: {
  flow: TimelineStoryFlowDTO;
  events: TimelineEventView[];
  labelWidth: number;
  step: number;
  cardWidth: number;
}) {
  const pointsByScene = new Map(flow.points.map((point) => [point.scene_id, point]));
  const eventsByScene = new Map(events.map((event) => [event.id, event]));
  const orderedPoints = events
    .map((event) => pointsByScene.get(event.id))
    .filter((point): point is TimelineStoryFlowPointDTO => point != null);
  const average = orderedPoints.length > 0
    ? orderedPoints.reduce((sum, point) => sum + point.tension_value, 0) / orderedPoints.length
    : 0;
  const peak = orderedPoints.length > 0
    ? Math.max(...orderedPoints.map((point) => point.tension_value))
    : 0;
  const dialogue = orderedPoints.length > 0
    ? orderedPoints.reduce((sum, point) => sum + point.dialogue_ratio, 0) / orderedPoints.length
    : 0;
  const action = orderedPoints.length > 0
    ? orderedPoints.reduce((sum, point) => sum + point.action_ratio, 0) / orderedPoints.length
    : 0;
  const warningRows = flow.warnings.length;

  return (
    <section
      aria-label="Timeline story flow"
      style={{
        minHeight: 52 + warningRows * 18,
        display: "flex",
        borderBottom: "1px solid var(--line2)",
        background: "rgba(0,0,0,.16)",
      }}
    >
      <div
        role="group"
        aria-label="Timeline Story Pulse"
        style={{
          width: labelWidth,
          flex: "none",
          boxSizing: "border-box",
          borderRight: "1px solid var(--line2)",
          padding: "7px 9px",
          color: "var(--txt2)",
          fontSize: 7,
          lineHeight: 1.45,
        }}
      >
        <strong style={{ display: "block", color: "var(--cyan)", letterSpacing: ".11em" }}>STORY PULSE</strong>
        <span>{`AVG ${average.toFixed(1)}/10 · PEAK ${peak.toFixed(1)}`}</span><br />
        <span>{`DIALOGUE ${ratioPercent(dialogue)}% · ACTION ${ratioPercent(action)}%`}</span><br />
        <span style={{ color: warningRows > 0 ? "var(--crimson)" : "var(--green)" }}>{warningRows > 0 ? plural(warningRows, "WARNING") : "NO PACING WARNINGS"}</span>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 52 + warningRows * 18 }}>
        {events.map((event) => {
          const point = pointsByScene.get(event.id);
          const title = event.title || "Untitled";
          if (!point) {
            return (
              <div
                key={event.id}
                role="img"
                aria-label={`${title}: no story flow data`}
                data-flow-scene-id={event.id}
                style={{ position: "absolute", left: (event.order_index - 1) * step + 8, top: 6, width: cardWidth, height: 36, boxSizing: "border-box", border: "1px dashed var(--line2)", padding: "5px 7px", color: "var(--txt3)", fontSize: 7 }}
              >NO FLOW DATA</div>
            );
          }
          const level = flowLevel(point.tension_value);
          const accessible = `${title}: tension ${point.tension_value.toFixed(1)} out of 10, ${level}; ${point.scene_type} scene; ${point.tension_source} source; dialogue ${ratioPercent(point.dialogue_ratio)}%; action ${ratioPercent(point.action_ratio)}%`;
          return (
            <div
              key={event.id}
              role="img"
              aria-label={accessible}
              title={accessible}
              data-flow-scene-id={event.id}
              style={{
                position: "absolute",
                left: (event.order_index - 1) * step + 8,
                top: 6,
                width: cardWidth,
                height: 36,
                boxSizing: "border-box",
                border: "1px solid var(--line2)",
                borderTop: `4px solid ${flowColor(point.tension_value)}`,
                background: flowColor(point.tension_value),
                padding: "3px 7px",
                color: "var(--strong)",
                overflow: "hidden",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 6 }}>
                <strong style={{ fontSize: 10 }}>{point.tension_value.toFixed(1)}</strong>
                <span style={{ fontSize: 6.5, letterSpacing: ".12em" }}>{level.toUpperCase()}</span>
              </div>
              <div style={{ fontSize: 6.5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{`${point.scene_type.toUpperCase()} · D${ratioPercent(point.dialogue_ratio)} · A${ratioPercent(point.action_ratio)}`}</div>
            </div>
          );
        })}
        {flow.warnings.map((warning, index) => {
          const warningEvents = warning.scene_ids
            .map((sceneId) => eventsByScene.get(sceneId))
            .filter((event): event is TimelineEventView => event != null);
          const startOrder = Math.min(...warningEvents.map((event) => event.order_index));
          const endOrder = Math.max(...warningEvents.map((event) => event.order_index));
          const startTitle = eventsByScene.get(warning.start_scene_id)?.title || `Scene ${warning.start_scene_id}`;
          const endTitle = eventsByScene.get(warning.end_scene_id)?.title || `Scene ${warning.end_scene_id}`;
          const range = warning.start_scene_id === warning.end_scene_id ? startTitle : `${startTitle} to ${endTitle}`;
          const text = warningText[warning.reason];
          return (
            <span
              key={`${warning.reason}-${warning.start_scene_id}-${warning.end_scene_id}-${index}`}
              role="note"
              aria-label={`Pacing warning: ${text.toLowerCase()} from ${range}`}
              style={{
                position: "absolute",
                left: Number.isFinite(startOrder) ? (startOrder - 1) * step + 8 : 8,
                top: 48 + index * 18,
                width: Number.isFinite(startOrder) && Number.isFinite(endOrder)
                  ? Math.max(cardWidth, (endOrder - startOrder) * step + cardWidth)
                  : cardWidth,
                height: 15,
                boxSizing: "border-box",
                border: "1px solid var(--crimson)",
                background: "rgba(232,68,58,.16)",
                color: "var(--crimson)",
                fontSize: 6.5,
                fontWeight: 700,
                letterSpacing: ".07em",
                padding: "2px 5px",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >⚠ {text} · {range}</span>
          );
        })}
      </div>
    </section>
  );
}
