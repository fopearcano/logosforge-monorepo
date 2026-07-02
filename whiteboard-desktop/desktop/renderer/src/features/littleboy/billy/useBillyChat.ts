/**
 * Billy chat state — conversation kept for the app session (lives in the
 * LittleBoy provider, so closing/reopening Billy preserves the thread). Sends to
 * the backend with bounded context + recent history.
 */

import { useCallback, useRef, useState } from 'react';

import { billyChat } from '../littleboyApi';
import type { ChatMessage } from '../littleboyTypes';
import type { BillyContextInput, BillyMessage } from './billyTypes';

const HISTORY_TURNS = 10;

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

interface Options {
  baseUrl: string;
}

export interface BillyChatApi {
  messages: BillyMessage[];
  sending: boolean;
  send: (text: string, ctx: BillyContextInput) => void;
  clear: () => void;
}

export function useBillyChat({ baseUrl }: Options): BillyChatApi {
  const [messages, setMessages] = useState<BillyMessage[]>([]);
  const [sending, setSending] = useState(false);
  const conversationId = useRef<string | undefined>(undefined);
  const messagesRef = useRef<BillyMessage[]>(messages);
  messagesRef.current = messages;

  const clear = useCallback(() => {
    conversationId.current = undefined;
    setMessages([]);
  }, []);

  const send = useCallback(
    (text: string, ctx: BillyContextInput) => {
      const content = text.trim();
      if (!content || sending) return;

      const history: ChatMessage[] = messagesRef.current
        .filter((m) => !m.pending && !m.error)
        .slice(-HISTORY_TURNS)
        .map((m) => ({ role: m.role, content: m.content }));

      const userMsg: BillyMessage = { id: newId(), role: 'user', content };
      const pendingId = newId();
      setMessages((prev) => [...prev, userMsg, { id: pendingId, role: 'assistant', content: '…', pending: true }]);
      setSending(true);

      billyChat(baseUrl, {
        message: content,
        selected_text: ctx.selected_text,
        nearby_context: ctx.nearby_context,
        writing_mode: ctx.writing_mode,
        document_title: ctx.document_title,
        conversation_id: conversationId.current,
        history,
      })
        .then((res) => {
          conversationId.current = res.conversation_id;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === pendingId ? { ...m, content: res.message.content, pending: false } : m,
            ),
          );
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : String(err);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === pendingId
                ? { ...m, content: `Billy couldn’t respond (${msg}).`, pending: false, error: true }
                : m,
            ),
          );
        })
        .finally(() => setSending(false));
    },
    [baseUrl, sending],
  );

  return { messages, sending, send, clear };
}
