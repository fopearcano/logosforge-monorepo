import type { ReactNode } from "react";
import { useScenes, useNotes, usePsykeEntries, useStoryHealth } from "../../hooks";

/** Left Navigator rail. Section badges + the health footer are wired to the
 *  live core (scenes / notes / PSYKE / story-health); the rest is design chrome. */

const wordsOf = (text: string) => (text.trim() ? text.trim().split(/\s+/).length : 0);

function GroupLabel({ children, top = 12 }: { children: ReactNode; top?: number }) {
  return (
    <div style={{ fontSize: 7.5, letterSpacing: ".3em", color: "var(--txt3)", padding: `${top}px 6px 5px` }}>
      {children}
    </div>
  );
}

function NavItem({
  icon,
  label,
  badge,
  iconColor = "var(--txt3)",
  active = false,
  quantum = false,
}: {
  icon: string;
  label: string;
  badge?: ReactNode;
  iconColor?: string;
  active?: boolean;
  quantum?: boolean;
}) {
  if (active) {
    return (
      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 10, height: 30, padding: "0 9px", background: "linear-gradient(90deg,rgba(76,194,255,.14),rgba(76,194,255,.02))", color: "#fff" }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 2, background: "var(--accent)", boxShadow: "0 0 10px var(--accent)" }} />
        <span style={{ width: 15, textAlign: "center", color: "var(--accent)" }}>{icon}</span>
        <span style={{ flex: 1, fontSize: 11, letterSpacing: ".04em", fontWeight: 500 }}>{label}</span>
        {badge}
      </div>
    );
  }
  return (
    <div className={quantum ? "lf-nav-q" : "lf-nav"} style={{ display: "flex", alignItems: "center", gap: 10, height: 28, padding: "0 9px", color: "var(--txt2)", cursor: "pointer" }}>
      <span style={{ width: 15, textAlign: "center", color: iconColor }}>{icon}</span>
      <span style={{ flex: 1, fontSize: 11, letterSpacing: ".04em" }}>{label}</span>
      {badge}
    </div>
  );
}

const countBadge = (v: string, color = "var(--txt3)") => (
  <span style={{ fontSize: 8.5, color }}>{v}</span>
);

export function Navigator({ projectTitle, modeName, spineLabel }: { projectTitle: string; modeName: string; spineLabel: string }) {
  const { data: scenes } = useScenes();
  const { data: notes } = useNotes();
  const { data: psyke } = usePsykeEntries();
  const { data: health } = useStoryHealth();

  const sceneCount = scenes?.length ?? 0;
  const noteCount = notes?.length ?? 0;
  const psykeCount = psyke?.length ?? 0;
  const wordCount = (scenes ?? []).reduce((n, s) => n + wordsOf(s.content ?? ""), 0);
  const signals = health ? [health.structure, health.characters, health.arcs, health.density] : [];
  const healthPct = signals.length
    ? Math.round((signals.reduce((n, s) => n + (s?.score ?? 0), 0) / signals.length) * 100)
    : null;

  return (
    <div style={{ width: 232, flex: "none", display: "flex", flexDirection: "column", background: "linear-gradient(180deg,#07090e,#05070b)", borderRight: "1px solid var(--line)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 30, padding: "0 12px", borderBottom: "1px solid var(--line2)" }}>
        <span style={{ fontSize: 8.5, letterSpacing: ".28em", color: "var(--txt3)" }}>NAVIGATOR</span>
        <span style={{ fontSize: 11, color: "var(--txt3)" }}>◧</span>
      </div>

      {/* project switcher → opens the Launchpad */}
      <div title="Switch project · open Launchpad" style={{ margin: "10px 10px 8px", padding: "8px 10px", border: "1px solid var(--line2)", background: "rgba(11,14,21,.55)", cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 7.5, letterSpacing: ".3em", color: "var(--txt3)" }}>PROJECT</div>
          <div style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".04em", color: "var(--txt)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{projectTitle}</div>
        </div>
        <span style={{ fontSize: 10, color: "var(--txt3)" }}>▾</span>
      </div>

      {/* mode chip */}
      <div style={{ margin: "0 10px 4px", padding: "9px 10px", border: "1px solid var(--accent)", background: "linear-gradient(135deg,rgba(76,194,255,.10),transparent)", position: "relative", boxShadow: "0 0 14px rgba(76,194,255,.10)" }}>
        <div style={{ position: "absolute", top: -1, left: -1, width: 7, height: 7, borderTop: "1px solid var(--accent)", borderLeft: "1px solid var(--accent)" }} />
        <div style={{ fontSize: 7.5, letterSpacing: ".3em", color: "var(--txt3)" }}>WRITING MODE</div>
        <div style={{ fontFamily: "'Chakra Petch'", fontWeight: 700, fontSize: 15, letterSpacing: ".08em", color: "var(--accent)", marginTop: 3, textShadow: "0 0 12px rgba(76,194,255,.4)" }}>{modeName}</div>
        <div style={{ fontSize: 8, letterSpacing: ".12em", color: "var(--txt2)", marginTop: 3 }}>{spineLabel}</div>
        <div style={{ position: "absolute", top: 8, right: 9, fontSize: 8, color: "var(--txt3)", border: "1px solid var(--line2)", padding: "1px 4px" }}>◍ LOCK</div>
      </div>

      {/* section tree */}
      <div style={{ flex: 1, overflowY: "auto", padding: "6px 8px 10px" }}>
        <GroupLabel top={8}>PLAN</GroupLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <NavItem icon="⊞" label="Dashboard" />
          <NavItem icon="▤" label="Write" active badge={<span style={{ fontSize: 8, color: "var(--accent)", letterSpacing: ".1em" }}>●</span>} />
          <NavItem icon="⧉" label="Structure" />
          <NavItem icon="▦" label="Scenes" badge={countBadge(String(sceneCount))} />
          <NavItem icon="⊟" label="Notes" badge={countBadge(String(noteCount))} />
        </div>

        <GroupLabel>NARRATIVE</GroupLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <NavItem icon="☰" label="Plot · Timeline" />
          <NavItem icon="◈" label="PSYKE" badge={countBadge(String(psykeCount))} />
          <NavItem icon="⬡" label="Graph" />
          <NavItem icon="✦" label="Quantum" iconColor="var(--violet)" quantum badge={<span style={{ fontSize: 8, color: "var(--violet)", border: "1px solid rgba(176,124,255,.4)", padding: "0 3px" }}>λ</span>} />
        </div>

        <GroupLabel>ANALYZE</GroupLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <NavItem icon="◉" label="Reviews" />
          <NavItem icon="⎇" label="Stages" />
          <NavItem icon="⌕" label="Search" />
        </div>

        <GroupLabel>SYSTEM</GroupLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <NavItem icon="◍" label="Voice · Dexter" />
          <NavItem icon="⊕" label="Plugins" />
          <NavItem icon="⊙" label="Settings" />
        </div>
      </div>

      {/* footer: project intel mini */}
      <div style={{ borderTop: "1px solid var(--line2)", padding: "9px 11px", display: "flex", alignItems: "center", gap: 9 }}>
        <div style={{ position: "relative", width: 26, height: 26, borderRadius: "50%", background: `conic-gradient(var(--green) 0 ${healthPct ?? 0}%,rgba(255,255,255,.08) ${healthPct ?? 0}% 100%)`, display: "grid", placeItems: "center" }}>
          <div style={{ width: 18, height: 18, borderRadius: "50%", background: "var(--base)", display: "grid", placeItems: "center", fontSize: 8, color: "var(--green)" }}>{healthPct ?? "—"}</div>
        </div>
        <div style={{ lineHeight: 1.3 }}>
          <div style={{ fontSize: 8, letterSpacing: ".16em", color: "var(--txt3)" }}>PROJECT HEALTH</div>
          <div style={{ fontSize: 10, color: "var(--txt2)" }}>{wordCount.toLocaleString()} words · {sceneCount} scenes</div>
        </div>
      </div>
    </div>
  );
}
