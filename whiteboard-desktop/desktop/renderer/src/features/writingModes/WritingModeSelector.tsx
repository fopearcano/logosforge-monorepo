/** A minimal, keyboard-accessible Writing Mode dropdown + structural vocabulary. */

import type { WritingMode } from './types';

interface Props {
  modes: WritingMode[];
  value: string;
  onChange: (mode: string) => void;
  disabled?: boolean;
}

export function WritingModeSelector({ modes, value, onChange, disabled }: Props) {
  const active = modes.find((m) => m.id === value);
  return (
    <div className="mode-selector">
      <label className="mode-label" htmlFor="writing-mode">
        Mode
      </label>
      <select
        id="writing-mode"
        className="mode-select"
        value={value}
        disabled={disabled || modes.length === 0}
        onChange={(e) => {
          onChange(e.target.value);
          // If the parent VETOES the change (e.g. the mode-switch confirm was
          // cancelled), the controlled `value` is unchanged and React won't
          // re-render the <select> back — leaving it stuck displaying a mode the
          // document is not in. Resync the DOM to the source of truth. On an
          // ACCEPTED change the parent re-renders with the new value and overrides
          // this line, so the select still lands on the new mode.
          e.currentTarget.value = value;
        }}
        title="Writing Mode"
      >
        {modes.length === 0 && <option value={value}>{value}</option>}
        {modes.map((m) => (
          <option key={m.id} value={m.id}>
            {m.label}
          </option>
        ))}
      </select>
      {active && (
        <span className="mode-vocab" title={active.medium_constraints}>
          {active.structural_units.join(' / ')}
        </span>
      )}
    </div>
  );
}
