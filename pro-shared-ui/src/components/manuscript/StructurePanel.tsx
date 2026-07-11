import type { CSSProperties } from "react";
import type { SceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useNavigate } from "../../adapters/StudioProvider";
import { useScenes } from "../../hooks";

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

function SceneRow({ code, title, tag, tagColor, tagBorder, onClick }: { code: string; title: string; tag?: string; tagColor?: string; tagBorder?: string; onClick?: () => void }) {
  return (
    <div className="lf-nav" onClick={onClick} title={onClick ? "Open in the Manuscript editor" : undefined} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", fontSize: 10, color: "var(--txt2)", cursor: "pointer" }}>
      <span style={{ fontFamily: "'Chakra Petch'", fontSize: 9, color: "var(--txt3)", minWidth: 38 }}>{code}</span>
      <span style={{ flex: 1 }}>{title}</span>
      {tag && <span style={{ fontSize: 7, color: tagColor, border: `1px solid ${tagBorder}`, padding: "0 4px" }}>{tag}</span>}
    </div>
  );
}

const message = (text: string) => (
  <div style={{ padding: "34px 0", textAlign: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

/** Static sparkline so the act rows keep their derived-spine look (no DTO source). */
const ACT_SPARK = { points: "0,10 12,8 25,5 38,9 50,4", color: "var(--green)" };

type ChapterGroup = { chapter: string; scenes: SceneDTO[] };
type ActGroup = { act: string; chapters: ChapterGroup[] };

/** Group scenes by act → chapter, preserving sort_order. Empty `act` is excluded (it lives in the UNASSIGNED bucket). */
function groupByActChapter(scenes: SceneDTO[]): ActGroup[] {
  const sorted = [...scenes].sort((a, b) => a.sort_order - b.sort_order);
  const acts: ActGroup[] = [];
  for (const s of sorted) {
    if (!s.act) continue;
    let act = acts.find((a) => a.act === s.act);
    if (!act) {
      act = { act: s.act, chapters: [] };
      acts.push(act);
    }
    const chapterKey = s.chapter || "—";
    let chap = act.chapters.find((c) => c.chapter === chapterKey);
    if (!chap) {
      chap = { chapter: chapterKey, scenes: [] };
      act.chapters.push(chap);
    }
    chap.scenes.push(s);
  }
  return acts;
}

export function StructurePanel(props: PanelProps) {
  const navigate = useNavigate();
  const { data: scenes, loading, error } = useScenes();
  const all = scenes ?? [];
  const acts = groupByActChapter(all);
  const unassigned = all.filter((s) => !s.act).sort((a, b) => a.sort_order - b.sort_order);
  const count = all.length;

  return (
    <PanelShell {...props}>
      <div data-screen-label="Structure Panel" style={panelBox}>
        <Corners />
        <div style={{ height: 42, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "var(--strong)" }}>STRUCTURE</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 7.5, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".12em" }}>NO ACT / CHAPTER TABLES · DERIVED</span>
        </div>
        {/* repair banner — reflects the live orphan (unassigned) count */}
        {unassigned.length > 0 && (
          <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 9, padding: "8px 14px", background: "rgba(245,177,51,.08)", borderBottom: "1px solid rgba(245,177,51,.3)" }}>
            <span style={{ width: 8, height: 8, transform: "rotate(45deg)", background: "var(--warning)" }} />
            <span style={{ fontSize: 9.5, color: "var(--amber-b)", flex: 1, letterSpacing: ".03em" }}>{unassigned.length} orphan scene{unassigned.length === 1 ? "" : "s"} — assign an act/chapter in the Manuscript editor</span>
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
                    {acts.map((act) => (
                      <div key={act.act}>
                        <ActRow n={`[${act.act}]`} title={act.act} spark={ACT_SPARK} />
                        <div style={{ paddingLeft: 20 }}>
                          {act.chapters.map((chap) => (
                            <div key={chap.chapter} style={{ marginTop: 3 }}>
                              <ChapterRow code={chap.chapter} title={chap.chapter} sc={`${chap.scenes.length} sc`} />
                              <div style={{ paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
                                {chap.scenes.map((s) => (
                                  <SceneRow
                                    key={s.id}
                                    code={s.chapter || String(s.sort_order)}
                                    title={s.title}
                                    tag={s.beat || undefined}
                                    tagColor="var(--green)"
                                    tagBorder="rgba(98,217,154,.3)"
                                    onClick={() => navigate("Manuscript", { sceneId: s.id })}
                                  />
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}

                    {/* UNASSIGNED bucket — hidden when there are no orphans */}
                    {unassigned.length > 0 && (
                      <div style={{ marginTop: 14, border: "1px dashed rgba(245,177,51,.4)", background: "rgba(245,177,51,.04)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 10px", borderBottom: "1px dashed rgba(245,177,51,.25)" }}>
                          <span style={{ fontSize: 9, color: "var(--amber)", letterSpacing: ".16em" }}>⚑ UNASSIGNED</span>
                          <span style={{ fontSize: 8, color: "var(--txt3)" }}>· {unassigned.length} scene{unassigned.length === 1 ? "" : "s"} · sorts last · unnumbered</span>
                        </div>
                        <div style={{ padding: "7px 10px", display: "flex", flexDirection: "column", gap: 5 }}>
                          {unassigned.map((s) => (
                            <div key={s.id} onClick={() => navigate("Manuscript", { sceneId: s.id })} title="Open in the Manuscript editor" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10, color: "var(--txt2)", cursor: "pointer" }}>
                              <span style={{ color: "var(--amber)" }}>◇</span><span style={{ flex: 1 }}>{s.title}</span><span style={{ fontSize: 7, color: "var(--amber)" }}>ORPHAN</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
        </div>
      </div>
    </PanelShell>
  );
}
