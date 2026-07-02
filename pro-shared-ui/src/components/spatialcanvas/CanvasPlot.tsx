import { useState, type CSSProperties, type ReactNode } from "react";
import type { PlotBlockDTO, PlotSceneDTO } from "@logosforge/ui-contracts";
import { PanelShell, type PanelProps } from "../shell/PanelShell";
import { usePlot } from "../../hooks";

const panelBox: CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  background: "#070a0e",
  border: "1px solid var(--line)",
  boxShadow: "0 16px 60px rgba(0,0,0,.6)",
  overflow: "hidden",
};

const ROW_H = 138;
const BLOCK_W = 186;
const BLOCK_STEP = 210;
const LABEL_W = 150;
const PALETTE = ["var(--cyan)", "var(--green)", "var(--amber)", "var(--violet)", "var(--crimson)", "var(--pink)"];
const colorOf = (i: number) => PALETTE[i % PALETTE.length] ?? PALETTE[0]!;

function Block({ left, top, width, topColor, title, badge, badgeColor, body, selected = false, onClick }: { left: number; top: number; width: number; topColor: string; title: string; badge: string; badgeColor: string; body: string; selected?: boolean; onClick?: () => void }) {
  const handle = (s: CSSProperties): CSSProperties => ({ position: "absolute", width: 6, height: 6, background: "var(--accent)", ...s });
  return (
    <div onClick={onClick} style={{ position: "absolute", left, top, width, zIndex: selected ? 5 : 4, cursor: "pointer", border: selected ? "1px solid var(--accent)" : "1px solid var(--line2)", borderTop: `2px solid ${topColor}`, background: selected ? "#0c1018" : "#0b0e15", boxShadow: selected ? "0 0 18px rgba(76,194,255,.25)" : "0 8px 24px rgba(0,0,0,.5)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 8px", borderBottom: "1px solid var(--line2)" }}>
        <span style={{ color: selected ? "var(--accent)" : "var(--txt3)", fontSize: 9 }}>⠿</span>
        <span title={title} style={{ fontSize: 9, color: "#fff", flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{title}</span>
        <span style={{ fontSize: 7, color: badgeColor, whiteSpace: "nowrap" }}>{badge}</span>
      </div>
      <div style={{ padding: 8, fontSize: 9, color: "var(--txt2)", lineHeight: 1.4, height: 52, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical" }}>{body}</div>
      {selected && <>
        <div style={handle({ left: -3, top: -3 })} /><div style={handle({ right: -3, top: -3 })} />
        <div style={handle({ left: -3, bottom: -3 })} /><div style={handle({ right: -3, bottom: -3 })} />
      </>}
    </div>
  );
}

const tBtn = (t: string, color = "var(--txt2)"): ReactNode => <span style={{ fontSize: 9, color, letterSpacing: ".08em" }}>{t}</span>;
const message = (text: string) => (
  <div style={{ position: "absolute", inset: "40px 0 0 0", display: "grid", placeItems: "center", fontSize: 11, color: "var(--txt3)", letterSpacing: ".04em" }}>{text}</div>
);

export function CanvasPlot(props: PanelProps) {
  const { data, loading, error } = usePlot();
  const plot = data ?? [];
  const [selId, setSelId] = useState<string | null>(null);

  const totalScenes = plot.reduce((n, b) => n + b.scenes.length, 0);
  const maxScenes = plot.reduce((m, b) => Math.max(m, b.scenes.length), 0);
  const contentW = LABEL_W + Math.max(1, maxScenes) * BLOCK_STEP + 60;
  const contentH = 24 + plot.length * ROW_H + 40;
  const sorted = (b: PlotBlockDTO) => b.scenes.slice().sort((a, c) => a.order_index - c.order_index);
  const badgeOf = (s: PlotSceneDTO) => s.beat || (s.scene_id != null ? `SC.${s.scene_id}` : `#${s.order_index}`);

  return (
    <PanelShell {...props}>
      <div data-screen-label="Canvas Plot" style={panelBox}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 14, height: 14, borderTop: "1px solid var(--crimson)", borderLeft: "1px solid var(--crimson)", zIndex: 9 }} />
        <div style={{ position: "absolute", top: 3, left: 3, width: 5, height: 5, background: "var(--crimson)", zIndex: 9 }} />
        {/* toolbar */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 40, display: "flex", alignItems: "center", gap: 13, padding: "0 14px", borderBottom: "1px solid var(--line)", background: "rgba(6,8,12,.8)", zIndex: 6 }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".12em", color: "#fff" }}>CANVAS PLOT</span>
          <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{plot.length} PLOTLINES · {totalScenes} SCENES</span>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 7.5, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "2px 7px", letterSpacing: ".12em" }}>DERIVED FROM SCENES</span>
        </div>

        {loading
          ? message("Loading plot…")
          : error
            ? message(`Couldn't load plot — ${error}`)
            : totalScenes === 0
              ? message("No plot blocks yet — they populate as you write scenes")
              : (
                <div style={{ position: "absolute", inset: "40px 0 0 0", overflow: "auto" }}>
                  <div style={{ position: "relative", width: contentW, height: contentH, backgroundImage: "radial-gradient(circle,rgba(128,140,158,.09) 1px,transparent 1.4px)", backgroundSize: "34px 34px" }}>
                    {plot.map((block, r) => {
                      const top = 24 + r * ROW_H;
                      const color = colorOf(r);
                      return (
                        <div key={block.id}>
                          {/* plotline lane label */}
                          <div style={{ position: "absolute", left: 14, top, width: LABEL_W - 34, zIndex: 3 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 7, height: 7, background: color }} /><span style={{ fontSize: 9, color, fontFamily: "'Chakra Petch'", letterSpacing: ".06em" }}>{block.plotline}</span></div>
                            <div style={{ fontSize: 7, color: "var(--txt3)", marginTop: 4, letterSpacing: ".08em" }}>{block.scenes.length} SCENE{block.scenes.length === 1 ? "" : "S"}</div>
                          </div>
                          {sorted(block).map((s, i) => {
                            const key = `${block.id}#${i}`;
                            return (
                              <Block
                                key={key}
                                left={LABEL_W + i * BLOCK_STEP}
                                top={top}
                                width={BLOCK_W}
                                topColor={s.color_label || color}
                                title={s.title || "(untitled)"}
                                badge={badgeOf(s)}
                                badgeColor={s.color_label || color}
                                body={s.summary || s.act || ""}
                                selected={selId === key}
                                onClick={() => setSelId(key)}
                              />
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
      </div>
    </PanelShell>
  );
}
