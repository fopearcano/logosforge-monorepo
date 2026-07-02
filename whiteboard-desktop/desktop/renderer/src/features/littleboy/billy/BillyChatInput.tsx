/** Billy input: Enter sends, Shift+Enter inserts a newline. */

import { useState, type KeyboardEvent } from 'react';

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function BillyChatInput({ onSend, disabled }: Props) {
  const [text, setText] = useState('');

  const submit = () => {
    const t = text.trim();
    if (!t || disabled) return;
    onSend(t);
    setText('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      submit();
    }
  };

  return (
    <div className="billy-input-row">
      <textarea
        className="billy-input"
        rows={2}
        placeholder="Message Billy…  (Enter to send · Shift+Enter for a new line)"
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button
        type="button"
        className="billy-send"
        onClick={submit}
        disabled={disabled || !text.trim()}
        title="Send (Enter)"
      >
        Send
      </button>
    </div>
  );
}
