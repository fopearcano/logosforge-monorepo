import { useCallback, useRef, type PointerEvent as ReactPointerEvent, type ReactElement } from 'react';
import {
  AssistantDock,
  Logos,
  QuantumOutliner,
  CounterpartPanel,
  ExtractionReview,
} from '@logosforge/pro-shared-ui';

interface AiTool {
  key: string;
  label: string;
  glyph: string;
  node: ReactElement;
}

// The AI companions — available while you work in ANY section (they read the
// active project + the cross-panel selection, so they act on the current view).
const AI_TOOLS: AiTool[] = [
  { key: 'Billy', label: 'Billy', glyph: '◇', node: <AssistantDock /> },
  { key: 'Logos', label: 'Logos', glyph: '❖', node: <Logos /> },
  { key: 'Quantum', label: 'Quantum', glyph: 'ψ', node: <QuantumOutliner /> },
  { key: 'Counterpart', label: 'Counterpart', glyph: '☯', node: <CounterpartPanel /> },
  { key: 'Extraction', label: 'Extract', glyph: '⛭', node: <ExtractionReview /> },
];

export const AI_TOOL_KEYS = AI_TOOLS.map((t) => t.key);

const MIN_W = 340;
const MAX_W = 900;

export function AiDock({
  open,
  tab,
  width,
  onOpenChange,
  onTabChange,
  onWidthChange,
}: {
  open: boolean;
  tab: string;
  width: number;
  onOpenChange: (o: boolean) => void;
  onTabChange: (t: string) => void;
  onWidthChange: (w: number) => void;
}) {
  const dragging = useRef(false);

  // Pointer capture (not window listeners) so a release OUTSIDE the Electron
  // window still ends the drag — otherwise the divider stays "stuck" to the cursor.
  const startDrag = useCallback((e: ReactPointerEvent) => {
    dragging.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);
  const onDragMove = useCallback((e: ReactPointerEvent) => {
    if (!dragging.current) return;
    const w = window.innerWidth - e.clientX;
    onWidthChange(Math.max(MIN_W, Math.min(MAX_W, w)));
  }, [onWidthChange]);
  const endDrag = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  const openTo = (key: string) => { onTabChange(key); onOpenChange(true); };

  if (!open) {
    return (
      <div className="ai-strip" title="Open the AI companions">
        <button className="ai-strip-toggle" onClick={() => onOpenChange(true)} aria-label="Open AI dock">‹ AI</button>
        {AI_TOOLS.map((t) => (
          <button key={t.key} className="ai-strip-btn" title={t.label} onClick={() => openTo(t.key)}>{t.glyph}</button>
        ))}
      </div>
    );
  }

  const current = AI_TOOLS.find((t) => t.key === tab) ?? AI_TOOLS[0]!;
  return (
    <aside className="ai-dock" style={{ width }}>
      <div className="ai-resize" onPointerDown={startDrag} onPointerMove={onDragMove} onPointerUp={endDrag} title="Drag to resize the AI dock" />
      <div className="ai-tabs">
        {AI_TOOLS.map((t) => (
          <button key={t.key} className={tab === t.key ? 'on' : ''} onClick={() => onTabChange(t.key)} title={t.label}>
            <span className="ai-tab-glyph">{t.glyph}</span>{t.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button className="ai-collapse" onClick={() => onOpenChange(false)} title="Collapse the AI dock" aria-label="Collapse AI dock">›</button>
      </div>
      {/* keep every tool mounted so Billy's chat / job state survives tab switches */}
      <div className="ai-body">
        {AI_TOOLS.map((t) => (
          <div key={t.key} style={{ position: 'absolute', inset: 0, visibility: t.key === current.key ? 'visible' : 'hidden' }}>
            {t.node}
          </div>
        ))}
      </div>
    </aside>
  );
}
