/** The PSYKE search input (autofocuses + selects on open). */

import { useEffect, useRef } from 'react';

interface Props {
  query: string;
  onChange: (q: string) => void;
}

export function PsykeSearch({ query, onChange }: Props) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);

  return (
    <div className="psyke-search">
      <input
        ref={ref}
        type="search"
        className="psyke-input"
        placeholder="Search PSYKE…"
        value={query}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Search PSYKE"
      />
    </div>
  );
}
