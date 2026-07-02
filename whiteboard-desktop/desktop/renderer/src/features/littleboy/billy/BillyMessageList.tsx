/** Billy chat transcript. Assistant replies may carry <action> suggestions,
 *  which render as clickable cards (click → ask Billy to apply them). */

import { Fragment, useEffect, useRef } from 'react';

import { parseBillyMessage } from './billyText';
import type { BillyMessage } from './billyTypes';

interface Props {
  messages: BillyMessage[];
  /** Apply a suggestion card → sends a follow-up asking Billy to carry it out. */
  onSuggestion?: (label: string) => void;
}

export function BillyMessageList({ messages, onSuggestion }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="billy-empty">
        Ask Billy about your draft. Your selection and nearby text are included as
        context.
      </div>
    );
  }

  return (
    <div className="billy-messages">
      {messages.map((m) => {
        if (m.role !== 'assistant') {
          return (
            <div key={m.id} className="billy-msg billy-msg-user">
              {m.content}
            </div>
          );
        }
        // Assistant: split prose from any <action> suggestion directives.
        const { text, actions } = parseBillyMessage(m.content);
        const cls = `billy-msg billy-msg-assistant${m.error ? ' is-error' : ''}${m.pending ? ' is-pending' : ''}`;
        return (
          <Fragment key={m.id}>
            {(text || m.pending || actions.length === 0) && <div className={cls}>{text}</div>}
            {!m.pending &&
              actions.map((a, i) => (
                <button
                  key={`${m.id}-a${i}`}
                  type="button"
                  className="billy-suggestion"
                  onClick={() => onSuggestion?.(a.label)}
                  title={a.raw}
                >
                  <span className="billy-suggestion-tag">Suggested action</span>
                  <span className="billy-suggestion-label">{a.label}</span>
                  <span className="billy-suggestion-cta">Ask Billy to apply →</span>
                </button>
              ))}
          </Fragment>
        );
      })}
      <div ref={endRef} />
    </div>
  );
}
