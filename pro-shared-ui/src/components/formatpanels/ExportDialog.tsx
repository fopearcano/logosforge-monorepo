import { useState, type CSSProperties } from "react";
import type { ExportRequestDTO } from "@logosforge/ui-contracts";
import { PanelShell, Corners, type PanelProps } from "../shell/PanelShell";
import { useExport } from "../../hooks";
import { useStudio } from "../../adapters/StudioProvider";

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

const ACCENT = { ["--accent"]: "#4cc2ff" } as CSSProperties;

// json/markdown/csv are the structured DATA exports the headless API serves.
const API_FORMATS = [
  { id: "markdown", label: "Markdown" },
  { id: "json", label: "JSON" },
  { id: "csv", label: "CSV" },
];
// Manuscript / screenplay DOCUMENT exports — each is its own export_type the core
// renders to a native format: text in `content`, or base64 bytes in `content_base64`
// (PDF/DOCX). All are now served by the API and saved through the platform adapter.
const DOC_EXPORTS: { id: string; label: string; binary?: boolean }[] = [
  { id: "manuscript", label: "Manuscript · TXT" },
  { id: "screenplay", label: "Screenplay · TXT" },
  { id: "screenplay_fountain", label: "Fountain" },
  { id: "production_fountain", label: "Production Fountain" },
  { id: "screenplay_fdx", label: "Final Draft · FDX" },
  { id: "screenplay_pdf", label: "Screenplay · PDF", binary: true },
  { id: "screenplay_docx", label: "Screenplay · DOCX", binary: true },
  { id: "manuscript_docx", label: "Manuscript · DOCX", binary: true },
];

// File extension per native format, for the suggested filename when the core didn't
// supply one (DATA exports) — e.g. markdown -> .md, not the literal "markdown".
const FORMAT_EXT: Record<string, string> = { markdown: "md", json: "json", csv: "csv", fountain: "fountain", fdx: "fdx", pdf: "pdf", docx: "docx", text: "txt", txt: "txt" };
const extFor = (fmt: string) => FORMAT_EXT[fmt] || fmt || "txt";

const EXPORT_TYPES = [
  { id: "full_project", label: "Full project" },
  { id: "story_elements", label: "Story elements" },
  { id: "psyke_data", label: "PSYKE data" },
];

// each SECTIONS toggle → its ExportRequest include_* flag
const SECTIONS: { key: keyof ExportRequestDTO; label: string }[] = [
  { key: "include_scenes", label: "Scenes" },
  { key: "include_outline", label: "Outline" },
  { key: "include_plot", label: "Plot" },
  { key: "include_timeline", label: "Timeline" },
  { key: "include_psyke_entries", label: "PSYKE entries" },
  { key: "include_psyke_relations", label: "PSYKE relations" },
  { key: "include_psyke_progressions", label: "PSYKE progressions" },
  { key: "include_notes", label: "Notes" },
];
const OPTIONS: { key: keyof ExportRequestDTO; label: string }[] = [
  { key: "include_project_metadata", label: "Project metadata" },
  { key: "include_ids", label: "Include ids" },
  { key: "summaries_only", label: "Summaries only" },
];

function TargetRow({ label, active = false, disabled = false, tag, onClick }: { label: string; active?: boolean; disabled?: boolean; tag?: string; onClick?: () => void }) {
  return (
    <div onClick={disabled ? undefined : onClick} style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 9px", cursor: disabled ? "default" : "pointer", border: active ? "1px solid var(--line-cy)" : "1px solid var(--line2)", background: active ? "rgba(76,194,255,.08)" : undefined, color: disabled ? "var(--txt3)" : active ? "var(--strong)" : "var(--txt2)", opacity: disabled ? 0.55 : 1 }}>
      <span style={{ flex: 1 }}>{label}{active ? " ●" : ""}</span>
      {tag && <span style={{ fontSize: 6.5, letterSpacing: ".1em", color: "var(--txt3)", border: "1px solid var(--line2)", padding: "0 4px" }}>{tag}</span>}
    </div>
  );
}

function Check({ label, checked = false, mb, onClick }: { label: string; checked?: boolean; mb?: number; onClick?: () => void }) {
  return (
    <label onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: mb, cursor: "pointer" }}>
      <span style={{ width: 10, height: 10, border: checked ? "1px solid var(--line-cy)" : "1px solid var(--line2)", background: checked ? "var(--accent)" : undefined }} />
      {label}
    </label>
  );
}

export function ExportDialog(props: PanelProps) {
  const { platform } = useStudio();
  const { run, running, result, error } = useExport();
  const [format, setFormat] = useState("markdown");
  const [exportType, setExportType] = useState("full_project");
  // When set, a manuscript/screenplay DOCUMENT export is selected (its own
  // export_type); else we're in DATA mode (scope `exportType` × `format`).
  const [docExport, setDocExport] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [incl, setIncl] = useState<Record<string, boolean>>({
    include_scenes: true, include_outline: true, include_plot: true, include_timeline: true,
    include_psyke_entries: true, include_psyke_relations: true, include_psyke_progressions: true,
    include_notes: true, include_project_metadata: true, include_ids: false, summaries_only: false,
  });
  const toggle = (k: string) => setIncl((m) => ({ ...m, [k]: !m[k] }));

  // DOCUMENT exports ignore the data format/sections (the core renders their native
  // format); DATA exports use the scope + format + section flags.
  const request: ExportRequestDTO = docExport
    ? { export_type: docExport, format: "" }
    : { export_type: exportType, format, ...incl };

  const isBinary = !!result?.content_base64;
  const text = result && !isBinary ? (result.content ?? (result.payload != null ? JSON.stringify(result.payload, null, 2) : "")) : "";
  const shown = text.slice(0, 8000);
  // base64 inflates ~4/3 over raw bytes (minus padding) — a good-enough size hint.
  const approxBytes = result?.content_base64 ? Math.floor(result.content_base64.replace(/=+$/, "").length * 0.75) : 0;
  const canCopy = !!text && typeof navigator !== "undefined" && !!navigator.clipboard;
  // platform is always injected, but the preview harness passes an empty stub — guard.
  const hasSave = typeof platform?.saveFile === "function";
  const canSave = !!result && hasSave && (isBinary || !!text);
  const onSave = async () => {
    if (!result || !hasSave) return;
    const suggestedName = result.filename ?? `export.${extFor(result.format)}`;
    const mimeType = result.mime_type ?? undefined;
    // Pass content_base64 straight through to the adapter — decoding to bytes is the
    // host's job (Buffer on desktop, atob/Blob on web); this package stays neutral.
    const opts = result.content_base64
      ? { suggestedName, contentBase64: result.content_base64, mimeType }
      : { suggestedName, content: text, mimeType };
    setSaveMsg(null);
    try {
      // A failed write must NOT look like a success — surface it (don't swallow).
      const r = await platform.saveFile(opts);
      if (!r?.canceled) setSaveMsg({ ok: true, text: r?.path ? `saved · ${r.path}` : "saved" });
    } catch (e) {
      setSaveMsg({ ok: false, text: `save failed — ${e instanceof Error ? e.message : String(e)}` });
    }
  };
  const status = running ? { t: "EXPORTING…", c: "var(--accent)" } : error ? { t: "FAILED", c: "var(--blocking)" } : result ? { t: "DONE", c: "var(--green)" } : { t: "READY", c: "var(--txt3)" };

  return (
    <PanelShell {...props} style={ACCENT}>
      <div data-screen-label="Export Studio" style={panelBox}>
        <Corners />

        {/* header */}
        <div style={{ height: 40, flex: "none", display: "flex", alignItems: "center", gap: 11, padding: "0 16px", borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontFamily: "'Chakra Petch'", fontWeight: 600, fontSize: 13, letterSpacing: ".1em", color: "var(--strong)" }}>EXPORT STUDIO</span>
          <span style={{ fontSize: 8, color: "var(--accent)", border: "1px solid var(--line-cy)", padding: "2px 7px", letterSpacing: ".1em" }}>{docExport ? docExport.replace(/_/g, " ").toUpperCase() : `${exportType.replace(/_/g, " ").toUpperCase()} · ${format.toUpperCase()}`}</span>
          <div style={{ flex: 1 }} />
          {result && <span style={{ fontSize: 9, color: "var(--txt2)" }}><span style={{ color: "var(--strong)" }}>{(isBinary ? approxBytes : text.length).toLocaleString()}</span> {isBinary ? "bytes" : "chars"}</span>}
        </div>

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* format picker */}
          <div style={{ width: 220, flex: "none", borderRight: "1px solid var(--line2)", padding: "12px 13px", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 7 }}>DATA · API-SERVED</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 13, fontSize: 9.5 }}>
              {API_FORMATS.map((f) => <TargetRow key={f.id} label={f.label} active={!docExport && format === f.id} onClick={() => { setDocExport(null); setFormat(f.id); }} />)}
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 7 }}>MANUSCRIPT · SCREENPLAY</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5 }}>
              {DOC_EXPORTS.map((d) => <TargetRow key={d.id} label={d.label} active={docExport === d.id} tag={d.binary ? "binary" : undefined} onClick={() => setDocExport(d.id)} />)}
            </div>
          </div>

          {/* preview / result */}
          <div style={{ flex: 1, borderRight: "1px solid var(--line2)", display: "flex", flexDirection: "column", minWidth: 0 }}>
            <div style={{ flex: "none", padding: "10px 16px 6px", fontSize: 7.5, letterSpacing: ".16em", color: "var(--txt3)", fontFamily: "'JetBrains Mono'" }}>
              {result ? `RESULT · ${result.format.toUpperCase()}` : "PREVIEW"}
            </div>
            <div style={{ flex: 1, padding: "4px 16px 14px", overflow: "auto", fontFamily: "'Courier Prime'", fontSize: 11.5, color: "var(--txt2)", lineHeight: 1.55, minWidth: 0 }}>
              {running ? (
                <div style={{ color: "var(--accent)" }}>Exporting {docExport ? docExport.replace(/_/g, " ") : `${exportType} as ${format}`}…</div>
              ) : error ? (
                <div style={{ color: "var(--blocking)", whiteSpace: "pre-wrap" }}>Export failed —{"\n"}{error}</div>
              ) : result && isBinary ? (
                <div style={{ color: "var(--txt2)" }}>
                  <div style={{ color: "var(--green)", marginBottom: 6 }}>◼ Binary file ready</div>
                  <div style={{ fontSize: 10, color: "var(--txt3)" }}>{result.filename ?? "export"} · {result.format.toUpperCase()} · {approxBytes.toLocaleString()} bytes</div>
                  <div style={{ fontSize: 10, color: "var(--txt3)", marginTop: 8 }}>Binary output can't be previewed as text — press <span style={{ color: "var(--green)" }}>SAVE</span> to write it to disk.</div>
                </div>
              ) : result ? (
                <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "inherit" }}>{shown}{text.length > shown.length ? `\n\n… +${(text.length - shown.length).toLocaleString()} more chars` : ""}</pre>
              ) : (
                <div style={{ color: "var(--txt3)" }}>Choose a data scope + format, or a manuscript/screenplay document, then press <span style={{ color: "var(--green)" }}>EXPORT</span>.</div>
              )}
            </div>
          </div>

          {/* controls */}
          <div style={{ width: 240, flex: "none", padding: "12px 13px", background: "var(--panel2)", overflowY: "auto" }}>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>SCOPE</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 13 }}>
              {EXPORT_TYPES.map((t) => (
                <div key={t.id} onClick={() => { setDocExport(null); setExportType(t.id); }} style={{ fontSize: 9, padding: "5px 9px", cursor: "pointer", border: !docExport && exportType === t.id ? "1px solid var(--line-cy)" : "1px solid var(--line2)", background: !docExport && exportType === t.id ? "rgba(76,194,255,.08)" : undefined, color: !docExport && exportType === t.id ? "var(--strong)" : "var(--txt2)" }}>{t.label}</div>
              ))}
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>SECTIONS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 9, color: "var(--txt2)", marginBottom: 12 }}>
              {SECTIONS.map((s) => <Check key={s.key} label={s.label} checked={!!incl[s.key]} onClick={() => toggle(s.key)} />)}
            </div>
            <div style={{ fontSize: 7.5, letterSpacing: ".18em", color: "var(--txt3)", marginBottom: 8 }}>OPTIONS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 9, color: "var(--txt2)" }}>
              {OPTIONS.map((o) => <Check key={o.key} label={o.label} checked={!!incl[o.key]} onClick={() => toggle(o.key)} />)}
            </div>
          </div>
        </div>

        {/* action bar */}
        <div style={{ flex: "none", borderTop: "1px solid var(--line)", padding: "9px 16px", display: "flex", alignItems: "center", gap: 16, background: "var(--tint)" }}>
          <span style={{ fontSize: 8, letterSpacing: ".16em", color: status.c }}>● {status.t}</span>
          <span style={{ fontSize: 9, color: "var(--txt3)" }}>{docExport ? docExport.replace(/_/g, " ") : `${exportType.replace(/_/g, " ")} · ${format}`}</span>
          {error && <span style={{ fontSize: 8.5, color: "var(--blocking)", maxWidth: 320, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{error}</span>}
          {saveMsg && <span title={saveMsg.text} style={{ fontSize: 8.5, color: saveMsg.ok ? "var(--green)" : "var(--blocking)", maxWidth: 300, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{saveMsg.ok ? "✓ " : "✕ "}{saveMsg.text}</span>}
          <div style={{ flex: 1 }} />
          <span onClick={canCopy ? () => navigator.clipboard.writeText(text) : undefined} style={{ fontSize: 9, color: canCopy ? "var(--txt2)" : "var(--txt3)", border: "1px solid var(--line2)", padding: "6px 12px", letterSpacing: ".06em", cursor: canCopy ? "pointer" : "default", opacity: canCopy ? 1 : 0.5 }}>⧉ COPY</span>
          <span onClick={canSave ? onSave : undefined} title={hasSave ? "Save the exported file" : "Saving needs the desktop or web host"} style={{ fontSize: 9, color: canSave ? "var(--txt2)" : "var(--txt3)", border: "1px solid var(--line2)", padding: "6px 12px", letterSpacing: ".06em", cursor: canSave ? "pointer" : "default", opacity: canSave ? 1 : 0.5 }}>⬇ SAVE</span>
          <span onClick={running ? undefined : () => { setSaveMsg(null); run(request); }} style={{ fontSize: 10, color: "var(--on-accent)", background: running ? "var(--txt3)" : "var(--green)", padding: "7px 18px", fontWeight: 700, letterSpacing: ".06em", cursor: running ? "default" : "pointer" }}>{running ? "EXPORTING…" : "EXPORT"}</span>
        </div>
      </div>
    </PanelShell>
  );
}
