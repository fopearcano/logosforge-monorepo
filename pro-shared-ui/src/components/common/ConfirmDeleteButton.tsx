import { useEffect, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";

const baseButton: CSSProperties = {
  border: "1px solid var(--line2)", background: "transparent", color: "var(--txt3)",
  font: "inherit", fontSize: 9, lineHeight: 1, padding: "3px 5px", cursor: "pointer",
};

export function ConfirmDeleteButton({
  label,
  onConfirm,
  disabled = false,
  trigger = "✕",
  title,
  containerStyle,
  triggerStyle,
}: {
  label: string;
  onConfirm: () => void;
  disabled?: boolean;
  trigger?: ReactNode;
  title?: string;
  containerStyle?: CSSProperties;
  triggerStyle?: CSSProperties;
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => setArmed(false), [label]);

  return (
    <span onKeyDown={(event: KeyboardEvent) => { if (armed && event.key === "Escape") { event.preventDefault(); setArmed(false); } }} style={{ display: "inline-flex", alignItems: "center", gap: 3, flex: "none", ...containerStyle }}>
      {armed ? (
        <>
          <button type="button" disabled={disabled} aria-label={`Confirm delete ${label}`} title={`Delete ${label}`} onClick={(event) => { event.stopPropagation(); if (!disabled) { setArmed(false); onConfirm(); } }} style={{ ...baseButton, color: "var(--crimson)", borderColor: "var(--crimson)", opacity: disabled ? 0.45 : 1 }}>✓</button>
          <button type="button" disabled={disabled} aria-label={`Cancel delete ${label}`} title="Cancel" onClick={(event) => { event.stopPropagation(); if (!disabled) setArmed(false); }} style={{ ...baseButton, opacity: disabled ? 0.45 : 1 }}>×</button>
        </>
      ) : (
        <button type="button" disabled={disabled} aria-label={`Delete ${label}`} title={title ?? `Delete ${label}`} onClick={(event) => { event.stopPropagation(); if (!disabled) setArmed(true); }} style={{ ...baseButton, ...triggerStyle, opacity: disabled ? 0.45 : (triggerStyle?.opacity ?? 1) }}>{trigger}</button>
      )}
    </span>
  );
}
