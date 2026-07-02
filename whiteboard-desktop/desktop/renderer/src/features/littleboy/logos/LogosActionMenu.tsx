/** The Logos contextual action buttons. */

import type { LogosActionId } from '../littleboyTypes';
import { LOGOS_ACTIONS } from './logosTypes';

interface Props {
  onAction: (id: LogosActionId) => void;
  disabled?: boolean;
}

export function LogosActionMenu({ onAction, disabled }: Props) {
  return (
    <div className="logos-actions">
      {LOGOS_ACTIONS.map((a) => (
        <button
          key={a.id}
          type="button"
          className="logos-action"
          title={a.hint}
          disabled={disabled}
          onClick={() => onAction(a.id)}
        >
          {a.label}
        </button>
      ))}
    </div>
  );
}
