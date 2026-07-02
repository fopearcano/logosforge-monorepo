/**
 * The autocomplete popup shown when Tab is pressed on a screenplay line.
 *
 * It opens pre-filled with the current line text; typing filters the
 * document-derived suggestions (slugs + used characters/scenes/transitions);
 * Up/Down move the highlight; Enter or Tab choose; Escape (or blur) dismisses.
 * Choosing replaces the whole line via the hook's `onSelect`.
 *
 * The popup owns its own keyboard so it never has to intercept the editor's
 * keystrokes — minimal and safe.
 */

import { useEffect, useRef, useState } from 'react';

import { filterSuggestions } from './screenplayAutocomplete';
import type { PopupProps } from './useScreenplayAutocomplete';

export function AutocompletePopup({
  open,
  left,
  top,
  query,
  suggestions,
  onSelect,
  onClose,
}: PopupProps) {
  const [filter, setFilter] = useState(query);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Re-seed the filter with the line text every time the popup (re)opens.
  useEffect(() => {
    if (open) {
      setFilter(query);
      setActive(0);
      inputRef.current?.focus();
    }
  }, [open, query]);

  if (!open) return null;

  const items = filterSuggestions(suggestions, filter);
  const activeIndex = Math.min(active, Math.max(0, items.length - 1));

  const choose = (i: number) => {
    const text = items[i];
    if (text != null) onSelect(text);
    else onClose();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      if (items.length) choose(activeIndex);
      else onClose();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  return (
    <div className="sp-autocomplete" style={{ left, top }} role="listbox">
      <input
        ref={inputRef}
        className="sp-ac-input"
        value={filter}
        spellCheck={false}
        autoComplete="off"
        aria-label="Filter screenplay suggestions"
        onChange={(e) => {
          setFilter(e.target.value);
          setActive(0);
        }}
        onKeyDown={onKeyDown}
        onBlur={onClose}
      />
      {items.length === 0 ? (
        <div className="sp-ac-empty">No matches</div>
      ) : (
        <ul className="sp-ac-list">
          {items.map((it, i) => (
            <li key={it}>
              <button
                type="button"
                role="option"
                aria-selected={i === activeIndex}
                className={`sp-ac-item${i === activeIndex ? ' is-active' : ''}`}
                // mousedown (not click) fires before the input's blur, so
                // selecting an item isn't cancelled by onBlur → onClose.
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(i);
                }}
              >
                {it}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
