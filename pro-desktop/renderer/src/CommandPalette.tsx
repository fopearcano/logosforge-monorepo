import { useEffect, useMemo, useRef, useState } from 'react';

export interface Command {
  id: string;
  kind: string;
  label: string;
  run: () => void;
}

export function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: Command[] }) {
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) {
      setQ('');
      setSel(0);
      const t = setTimeout(() => inputRef.current?.focus(), 0);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [open]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(needle) || c.kind.toLowerCase().includes(needle));
  }, [q, commands]);

  useEffect(() => { setSel((s) => Math.min(s, Math.max(0, filtered.length - 1))); }, [filtered.length]);

  if (!open) return null;

  const run = (c: Command) => { onClose(); c.run(); };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(filtered.length - 1, s + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(0, s - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); const c = filtered[sel]; if (c) run(c); }
  };

  return (
    <div className="cmdk-backdrop" onMouseDown={onClose}>
      <div className="cmdk" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => { setQ(e.target.value); setSel(0); }}
          onKeyDown={onKey}
          placeholder="Jump to a section · open an AI tool · toggle focus…"
          aria-label="Command palette"
        />
        <div className="cmdk-list">
          {filtered.length === 0 ? (
            <div className="cmdk-empty">No matches</div>
          ) : (
            filtered.map((c, i) => (
              <button key={c.id} type="button" className={i === sel ? 'on' : ''} onMouseEnter={() => setSel(i)} onClick={() => run(c)}>
                <span className="cmdk-kind">{c.kind}</span>
                <span>{c.label}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
