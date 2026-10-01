import type { CSSProperties } from "react";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useNavigate, useStudio } from "../../adapters/StudioProvider";
import { useStoryStructure } from "../../hooks";

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

function Spark({ points, color }: { points: string; color: string }) {
  return (
    <svg viewBox="0 0 50 14" style={{ width: 50, height: 14 }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.3} />
    </svg>
  );
}

function ActRow({ n, title, spark }: { n: string; title: string; spark: { points: string; color: string } }) {
  return (
    <div style={{ margin: "10px 0 5px", display: "flex", alignItems: "center", gap: 9, padding: "7px 6px", borderBottom: "1px solid var(--line2)" }}>
      <span style={{ fontFamily: "'Chakra Petch'", fontSize: 12, color: "var(--accent)", minWidth: 30 }}>{n}</span>
      <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".08em", color: "var(--strong)", flex: 1 }}>{title}</span>
      <Spark points={spark.points} color={spark.color} />
    </div>
  );
}

function ChapterRow({ code, title, sc }: { code: string; title: string; sc: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 6px", color: "var(--txt2)" }}>
      <span style={{ fontFamily: "'Chakra Petch'", fontSize: 10, color: "var(--txt3)", minWidth: 34 }}>{code}</span>
      <span style={{ fontSize: 11, flex: 1 }}>{title}</span>
      <span style={{ fontSize: 8, color: "var(--txt3)" }}>{sc}</span>
    </div>
  );
}

function SceneRow({ number, title, tag, tagColor, tagBorder, onClick }: { number: string; title: string; tag?: string; tagColor?: string; tagBorder?: string; onClick?: () => void }) {
  const structuralNumber = number.trim();
  return (
    <button type="button" className="lf-nav" onClick={onClick} disabled={!onClick} title={onClick ? "Open in the Manuscript editor" : undefined} style={{ width: "100%", border: "none", background: "transparent", font: "inherit", textAlign: "left", display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", fontSize: 10, color: "var(--txt2)", cursor: onClick ? "pointer" : "default" }}>
      <span
        data-structure-number={structuralNumber}
        aria-label={structuralNumber ? undefined : "Unnumbered scene"}
        style={{ fontFamily: "'Chakra Petch'", fontSize: 9, color: "var(--txt3)", minWidth: 38 }}
      >
        {structuralNumber || "—"}
      </span>
      <span style={{ flex: 1 }}>{title}</span>
      {tag && <span style={{ fontSize: 7, color: tagColor, border: `1px solid ${tagBorder}`, padding: "0 4px" }}>{tag}</span>}
    </button>
  );
}

const message = (text: string) => (
  <div style={{ padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** Static sparkline so the act rows keep their derived-spine look (no DTO source). */
const ACT_SPARK = { points: "0,10 12,8 25,5 38,9 50,4", color: "var(--green)" };

export function StructurePanel(props: PanelProps) {
  const navigate = useNavigate();
  const { projectId } = useStudio();
  const { data: loadedStructure, loading, error } = useStoryStructure();
  const structure = loadedStructure?.project_id === projectId ? loadedStructure : undefined;
  const acts = structure?.acts ?? [];
  const orphanCount = structure?.orphan_count ?? 0;
  const count = structure?.scene_count ?? 0;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Structure Panel" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>STRUCTURE</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 7.5, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".12em" }}>CORE CANONICAL · DERIVED</span>
        </div>
        {/* repair banner — reflects the live orphan (unassigned) count */}
        {orphanCount > 0 && (
          <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 9, padding: "8px 14px", background: "rgba(245,177,51,.08)", borderBottom: "1px solid rgba(245,177,51,.3)" }}>
            <span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: "var(--warning)" }} />
            <span style={{ fontSize: 9.5, color: "var(--amber-b)", flex: 1, letterSpacing: ".03em" }}>{orphanCount} orphan scene{orphanCount === 1 ? "" : "s"} — assign its missing structure in the Manuscript editor</span>
          </div>
        )}
        {/* spine */}
        <div style={{ flex: 1, overflowY: "auto", padding: 13 }}>
          {loading
            ? message("Loading structure…")
            : error
              ? message(`Couldn't load structure — ${error}`)
              : count === 0
                ? message("No scenes yet — the spine appears as you draft")
                : (
                  <>
                    {acts.map((act) => {
                      const flatScenes = act.chapters.flatMap((chapter) => chapter.scenes);
                      return (
                        <div key={`${act.unassigned ? "unassigned" : "act"}:${act.name}`} data-structure-source="core">
                          <ActRow n={`[${act.number || "—"}]`} title={act.name} spark={ACT_SPARK} />
                          <div style={{ paddingLeft: 20 }}>
                            {structure?.chapter_level ? act.chapters.map((chapter) => (
                              <div key={`${chapter.unassigned ? "unassigned" : "chapter"}:${chapter.name}`} style={{ marginTop: 3 }}>
                                <ChapterRow code={chapter.number || "—"} title={chapter.name} sc={`${chapter.scene_count} sc`} />
                                <div style={{ paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
                                  {chapter.scenes.map((scene) => (
                                    <SceneRow
                                      key={scene.id}
                                      number={scene.number}
                                      title={scene.title}
                                      tag={scene.beat || undefined}
                                      tagColor={scene.is_orphan ? "var(--amber)" : "var(--green)"}
                                      tagBorder={scene.is_orphan ? "rgba(245,177,51,.4)" : "rgba(98,217,154,.3)"}
                                      onClick={() => navigate("Manuscript", { sceneId: scene.id })}
                                    />
                                  ))}
                                </div>
                              </div>
                            )) : (
                              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                {flatScenes.map((scene) => (
                                  <SceneRow
                                    key={scene.id}
                                    number={scene.number}
                                    title={scene.title}
                                    tag={scene.beat || undefined}
                                    tagColor={scene.is_orphan ? "var(--amber)" : "var(--green)"}
                                    tagBorder={scene.is_orphan ? "rgba(245,177,51,.4)" : "rgba(98,217,154,.3)"}
                                    onClick={() => navigate("Manuscript", { sceneId: scene.id })}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
        </div>
      </div>
    </PanelShell>
  );
}
