import { useEffect, useRef, type KeyboardEvent } from 'react';

interface Props {
  open: boolean;
  requestToken: number;
  query: string;
  replacement: string;
  matchCase: boolean;
  wholeWord: boolean;
  currentIndex: number;
  matchCount: number;
  searchPending: boolean;
  surfaceLabel: string;
  announcement?: string;
  canReplace: boolean;
  canReplaceAll: boolean;
  onQueryChange: (value: string) => void;
  onReplacementChange: (value: string) => void;
  onMatchCaseChange: (value: boolean) => void;
  onWholeWordChange: (value: boolean) => void;
  onPrevious: () => void;
  onNext: () => void;
  onReplace: () => void;
  onReplaceAll: () => void;
  onClose: () => void;
}

export function FindReplaceBar({
  open,
  requestToken,
  query,
  replacement,
  matchCase,
  wholeWord,
  currentIndex,
  matchCount,
  searchPending,
  surfaceLabel,
  announcement,
  canReplace,
  canReplaceAll,
  onQueryChange,
  onReplacementChange,
  onMatchCaseChange,
  onWholeWordChange,
  onPrevious,
  onNext,
  onReplace,
  onReplaceAll,
  onClose,
}: Props) {
  const findRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      findRef.current?.focus({ preventScroll: true });
      findRef.current?.select();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open, requestToken]);

  if (!open) return null;

  const resultLabel = !query
    ? 'Type to find'
    : searchPending
      ? 'Searching…'
      : matchCount === 0
        ? 'No matches'
        : `${Math.max(0, currentIndex) + 1} of ${matchCount}`;

  const onFindKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' || event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (event.shiftKey || event.key === 'ArrowUp') onPrevious();
      else onNext();
    }
  };

  return (
    <section
      className="find-replace-bar"
      role="search"
      aria-label={`Find and replace in ${surfaceLabel}`}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="find-replace-fields">
        <label>
          <span>Find</span>
          <input
            ref={findRef}
            type="text"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={onFindKeyDown}
            spellCheck={false}
            autoComplete="off"
          />
        </label>
        <label>
          <span>Replace</span>
          <input
            type="text"
            value={replacement}
            onChange={(event) => onReplacementChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && canReplace) {
                event.preventDefault();
                onReplace();
              }
            }}
            spellCheck={false}
            autoComplete="off"
          />
        </label>
      </div>

      <div className="find-replace-options" role="group" aria-label="Search options">
        <label title="Match uppercase and lowercase exactly">
          <input
            type="checkbox"
            checked={matchCase}
            onChange={(event) => onMatchCaseChange(event.target.checked)}
          />
          Match case
        </label>
        <label title="Match complete words only">
          <input
            type="checkbox"
            checked={wholeWord}
            onChange={(event) => onWholeWordChange(event.target.checked)}
          />
          Whole word
        </label>
      </div>

      <div className="find-replace-actions">
        <span className="find-replace-count">{resultLabel}</span>
        <span className="wb-sr-only" aria-live="polite" aria-atomic="true">
          {announcement || resultLabel}
        </span>
        <button type="button" onClick={onPrevious} disabled={searchPending || matchCount === 0} aria-label="Previous match">
          ↑
        </button>
        <button type="button" onClick={onNext} disabled={searchPending || matchCount === 0} aria-label="Next match">
          ↓
        </button>
        <button type="button" onClick={onReplace} disabled={!canReplace}>
          Replace
        </button>
        <button type="button" onClick={onReplaceAll} disabled={!canReplaceAll}>
          Replace all
        </button>
        <button type="button" className="find-replace-close" onClick={onClose} aria-label="Close find and replace">
          ×
        </button>
      </div>

      <span className="find-replace-scope" title={`Searching ${surfaceLabel}`}>
        {surfaceLabel}
      </span>
    </section>
  );
}
