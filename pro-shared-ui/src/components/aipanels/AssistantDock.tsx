import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type { ChatMessageDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useStudio } from "../../adapters/StudioProvider";
import { useSelection } from "../../adapters/selection";
import { useApplyToScene, ApplyDiffModal } from "./applyToScene";

const applyBtn: CSSProperties = { fontSize: 8, letterSpacing: ".06em", color: "var(--accent)", background: "transparent", border: "1px solid var(--line-cy,#2b6f8f)", padding: "3px 8px", cursor: "pointer" };

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

const SUGGESTIONS = [
  "Where does the story sag, and what should I cut?",
  "Summarise what happens so far.",
  "Suggest the next scene.",
  "Who is my protagonist and what do they want?",
];

export function AssistantDock(props: PanelProps) {
  const { api, projectId } = useStudio();
  const { selection } = useSelection();
  const { target, apply } = useApplyToScene();
  const [messages, setMessages] = useState<ChatMessageDTO[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pendingApply, setPendingApply] = useState<{ proposed: string; badge: string } | null>(null);
  // "Go Irrational" — per-message surreal creative provocations (needs an active scene).
  const [irrational, setIrrational] = useState(false);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // scroll to the newest message
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, pending]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || pending || projectId == null) return;
      setErr(null);
      const history = messages;
      setMessages((m) => [...m, { role: "user", content: message }]);
      setInput("");
      setPending(true);
      try {
        const res = await api.assistantChat(projectId, {
          message,
          history,
          // section-aware: whatever you've selected in the current section
          selected_text: selection.text || undefined,
          active_scene_id: selection.sceneId ?? undefined,
          irrational: irrational || undefined,
        });
        setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setPending(false);
      }
    },
    [api, projectId, pending, messages, selection, irrational],
  );

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
      e.preventDefault();
      void send(input);
    }
  };

  return (
    <PanelShell {...props} style={{ ["--accent"]: "#4cc2ff" } as CSSProperties}>
      <div data-screen-label="Billy Assistant" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 44, flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "0 14px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ width: 24, height: 24, display: "grid", placeItems: "center", border: "1px solid var(--accent)", color: "var(--accent)", fontSize: 12, boxShadow: "0 0 12px rgba(76,194,255,.25)" }}>◇</span>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 14, letterSpacing: ".1em", color: "var(--strong)" }}>BILLY</span>
          <span style={{ fontSize: 8, color: "var(--txt3)", letterSpacing: ".08em" }}>project-aware assistant</span>
          <div style={{ flex: 1 }} />
          {messages.length > 0 && (
            <button type="button" onClick={() => { setMessages([]); setErr(null); }} style={{ fontSize: 8, color: "var(--txt3)", background: "transparent", border: "1px solid var(--line2)", padding: "3px 8px", cursor: "pointer", letterSpacing: ".08em" }}>NEW CHAT</button>
          )}
        </div>

        {/* chat log */}
        <div ref={logRef} style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
          {messages.length === 0 && !pending && (
            <div style={{ margin: "auto", textAlign: "center", maxWidth: 320 }}>
              <div style={{ fontSize: 12, color: "var(--txt2)", marginBottom: 14 }}>Ask Billy about your story — he sees your scenes, outline and bible.</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => void send(s)} disabled={projectId == null} style={{ fontSize: 10, color: "var(--txt2)", background: "var(--tint)", border: "1px solid var(--line2)", padding: "8px 11px", textAlign: "left", cursor: "pointer" }}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} style={{ display: "flex", justifyContent: "flex-end" }}>
                <div style={{ maxWidth: "80%", background: "rgba(76,194,255,.08)", border: "1px solid var(--line-cy)", padding: "10px 12px", fontSize: 12.5, color: "var(--txt)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{m.content}</div>
              </div>
            ) : (
              <div key={i}>
                <div style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ width: 18, height: 18, display: "grid", placeItems: "center", border: "1px solid var(--accent)", color: "var(--accent)", fontSize: 9 }}>◇</span>
                  <span style={{ fontSize: 8, letterSpacing: ".14em", color: "var(--txt3)" }}>BILLY</span>
                </div>
                <div style={{ background: "var(--tint)", border: "1px solid var(--line2)", padding: 13, fontSize: 12.5, color: "var(--txt)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{m.content}</div>
                {target && m.content.trim() && (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
                    <span style={{ fontSize: 7.5, letterSpacing: ".1em", color: "var(--txt3)" }}>→ {target.title}</span>
                    <button type="button" style={applyBtn} title={`Rewrite ${target.title} with this (diff + confirm)`} onClick={() => setPendingApply({ proposed: m.content, badge: "REWRITE" })}>↧ REPLACE</button>
                    <button type="button" style={applyBtn} title={`Append this to ${target.title} (diff + confirm)`} onClick={() => setPendingApply({ proposed: (target.content ? target.content + "\n\n" : "") + m.content, badge: "APPEND" })}>＋ APPEND</button>
                  </div>
                )}
              </div>
            ),
          )}
          {pending && (
            <div style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--txt3)", fontSize: 10 }}>
              <span style={{ width: 18, height: 18, display: "grid", placeItems: "center", border: "1px solid var(--accent)", color: "var(--accent)", fontSize: 9 }}>◇</span>
              Billy is thinking…
            </div>
          )}
          {err && (
            <div style={{ border: "1px solid var(--crimson)", background: "rgba(232,68,58,.06)", padding: "9px 11px", fontSize: 10, color: "var(--crimson)", lineHeight: 1.5 }}>
              Billy is unavailable — he needs a running AI provider (e.g. LM Studio). <span style={{ color: "var(--txt3)" }}>{err}</span>
            </div>
          )}
        </div>

        {/* input */}
        <div style={{ flex: "none", borderTop: "1px solid var(--line2)", padding: "11px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
            <button
              type="button"
              onClick={() => setIrrational((v) => !v)}
              title="Go Irrational — inject surreal creative provocations (temporal displacement, entity blending) into the next reply. Needs an active scene."
              style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 8.5, letterSpacing: ".08em", border: `1px solid ${irrational ? "var(--violet,#b07cff)" : "var(--line2)"}`, background: irrational ? "rgba(176,124,255,.12)" : "transparent", color: irrational ? "var(--violet,#b07cff)" : "var(--txt3)", padding: "3px 9px", cursor: "pointer", font: "inherit" }}
            >
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: irrational ? "var(--violet,#b07cff)" : "var(--line2)", boxShadow: irrational ? "0 0 6px var(--violet,#b07cff)" : undefined }} />
              GO IRRATIONAL
            </button>
            {irrational && <span style={{ fontSize: 7.5, color: "var(--txt3)", letterSpacing: ".04em" }}>surreal mode on · needs an open scene</span>}
          </div>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10, padding: "10px 12px", border: "1px solid var(--line-cy)", background: "var(--raised)" }}>
            <span style={{ color: "var(--accent)", fontSize: 14, paddingTop: 6 }}>❯</span>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={projectId == null ? "Open a project to chat with Billy…" : "Ask Billy about your story…  (Enter to send)"}
              disabled={projectId == null}
              rows={2}
              aria-label="Message Billy"
              style={{ flex: 1, resize: "none", background: "transparent", border: "none", outline: "none", color: "var(--txt)", fontFamily: "inherit", fontSize: 13.5, lineHeight: 1.55, minHeight: 46, maxHeight: 180 }}
            />
            <button type="button" onClick={() => void send(input)} disabled={pending || projectId == null || !input.trim()} style={{ fontSize: 11, color: "var(--on-accent)", background: "var(--accent)", border: "none", padding: "8px 15px", fontWeight: 600, letterSpacing: ".06em", cursor: pending || !input.trim() ? "default" : "pointer", opacity: pending || projectId == null || !input.trim() ? 0.4 : 1 }}>SEND</button>
          </div>
        </div>

        {pendingApply && target && (
          <ApplyDiffModal
            title={target.title.toUpperCase()}
            badge={pendingApply.badge}
            original={target.content}
            proposed={pendingApply.proposed}
            onConfirm={() => apply(pendingApply.proposed)}
            onClose={() => setPendingApply(null)}
          />
        )}
      </div>
    </PanelShell>
  );
}
