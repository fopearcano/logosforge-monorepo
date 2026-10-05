import { useCallback, useId, useState } from 'react';

import {
  loadPanelTransparency,
  normalizePanelTransparency,
  opacityForPanelTransparency,
  PANEL_TRANSPARENCY_MAX,
  savePanelTransparency,
} from './panelTransparency';

interface Props {
  label: string;
  value: number;
  onChange: (value: number) => void;
}

export function usePanelTransparency(storageKey: string) {
  const [transparency, setTransparencyState] = useState(() => loadPanelTransparency(storageKey));
  const setTransparency = useCallback(
    (value: number) => {
      const normalized = normalizePanelTransparency(value);
      setTransparencyState(normalized);
      savePanelTransparency(storageKey, normalized);
    },
    [storageKey],
  );

  return {
    transparency,
    opacity: opacityForPanelTransparency(transparency),
    setTransparency,
  };
}

export function PanelTransparencyControl({ label, value, onChange }: Props) {
  const inputId = useId();

  return (
    <label
      className="panel-transparency-control"
      htmlFor={inputId}
      title={`${label} transparency: ${value}%`}
    >
      <input
        id={inputId}
        type="range"
        min={0}
        max={PANEL_TRANSPARENCY_MAX}
        step={5}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label={`${label} transparency`}
        aria-valuetext={`${value}% transparent`}
      />
      <output htmlFor={inputId} aria-hidden="true">{value}%</output>
    </label>
  );
}
