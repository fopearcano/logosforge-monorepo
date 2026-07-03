/**
 * Structure-templates picker — apply a writing-method skeleton (Three-Act,
 * Save the Cat!, Hero's Journey, …) to the outline. With existing items the
 * template appends after them; "Replace" (opt-in) swaps the whole outline.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import { TYPE_LABELS, type OutlineItemType } from './outlineModel';
import {
  OUTLINE_TEMPLATES,
  countTemplateNodes,
  type OutlineTemplate,
  type TemplateNode,
} from './outlineTemplates';

interface Props {
  open: boolean;
  hasExisting: boolean;
  onApply: (tpl: OutlineTemplate, replace: boolean) => void;
  onClose: () => void;
}

interface PreviewRow {
  title: string;
  depth: number;
  type: OutlineItemType;
}

function previewLines(nodes: TemplateNode[], depth = 0, out: PreviewRow[] = []): PreviewRow[] {
  for (const n of nodes) {
    out.push({ title: n.title, depth, type: n.type });
    if (n.children) previewLines(n.children, depth + 1, out);
  }
  return out;
}

export function OutlineTemplatesDialog({ open, hasExisting, onApply, onClose }: Props) {
  const [selectedId, setSelectedId] = useState<string>(OUTLINE_TEMPLATES[0].id);
  const [replace, setReplace] = useState(false);
  const firstRef = useRef<HTMLButtonElement>(null);

  // Reset the picks + focus ONLY on an open transition (deps: [open]). If this
  // shared an effect with the Escape listener (which must depend on the unstable
  // inline `onClose`), any parent re-render while the dialog is open — e.g. a
  // debounced autosave settling ~600ms after an edit — would silently reset the
  // chosen template and uncheck "Replace", risking the wrong template/mode.
  useEffect(() => {
    if (!open) return;
    setReplace(false);
    setSelectedId(OUTLINE_TEMPLATES[0].id);
    firstRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const selected = useMemo(
    () => OUTLINE_TEMPLATES.find((t) => t.id === selectedId) ?? OUTLINE_TEMPLATES[0],
    [selectedId],
  );
  const preview = useMemo(() => previewLines(selected.nodes), [selected]);

  if (!open) return null;

  const doReplace = hasExisting && replace;
  const applyLabel = doReplace
    ? 'Replace with template'
    : hasExisting
      ? 'Append template'
      : 'Create outline';

  return (
    <div
      className="cf-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="otpl-dialog" role="dialog" aria-modal="true" aria-labelledby="otpl-title">
        <div className="settings-head">
          <h2 id="otpl-title" className="settings-title">
            Structure templates
          </h2>
          <button type="button" className="settings-close" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <p className="settings-sub">
          Start from a proven writing method. Nodes are added to your outline — rename and reshape
          them freely.
        </p>

        <div className="otpl-body">
          <ul className="otpl-list" role="listbox" aria-label="Templates">
            {OUTLINE_TEMPLATES.map((t, i) => (
              <li key={t.id}>
                <button
                  ref={i === 0 ? firstRef : undefined}
                  type="button"
                  role="option"
                  aria-selected={t.id === selectedId}
                  className={`otpl-item${t.id === selectedId ? ' is-active' : ''}`}
                  onClick={() => setSelectedId(t.id)}
                >
                  <span className="otpl-item-name">{t.name}</span>
                  <span className="otpl-item-desc">{t.description}</span>
                  <span className="otpl-item-count">{countTemplateNodes(t)} items</span>
                </button>
              </li>
            ))}
          </ul>

          <div className="otpl-preview" aria-label={`${selected.name} preview`}>
            {preview.map((p, i) => (
              <div key={i} className="otpl-prev-row" style={{ paddingLeft: 4 + p.depth * 14 }}>
                <span className="otpl-prev-type">{TYPE_LABELS[p.type]}</span>
                <span className="otpl-prev-title">{p.title}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="otpl-foot">
          {hasExisting ? (
            <label className="otpl-replace">
              <input
                type="checkbox"
                checked={replace}
                onChange={(e) => setReplace(e.target.checked)}
              />
              <span>Replace current outline{replace ? ' (deletes existing items)' : ''}</span>
            </label>
          ) : (
            <span />
          )}
          <div className="otpl-actions">
            <button type="button" className="settings-btn" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="settings-btn is-primary"
              onClick={() => onApply(selected, doReplace)}
            >
              {applyLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
