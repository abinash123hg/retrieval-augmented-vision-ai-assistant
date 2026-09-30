import { useCallback, useState } from 'react';
import api from '../api/client';
import { errorDetail } from '../utils/formatters';

const STORAGE_KEY = 'doculens.chat.messages';

function loadMessages() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Drop legacy messages that predate per-document scoping (no documentIds),
    // so old conversations can never resurface under an unrelated document.
    return parsed.filter((m) => m && Array.isArray(m.documentIds));
  } catch {
    return [];
  }
}

function saveMessages(messages) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  } catch {
    // sessionStorage full/unavailable — history persistence is best-effort
  }
}

let seq = 0;
function nextId() {
  seq += 1;
  return `msg-${Date.now()}-${seq}`;
}

// A message belongs to a single-document scope when exactly one id is attached,
// otherwise it belongs to the "all documents" scope.
export function scopeOf(message) {
  const ids = message.documentIds || [];
  return ids.length === 1 ? ids[0] : 'all';
}

export default function useChat() {
  const [messages, setMessages] = useState(loadMessages);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const append = useCallback((message) => {
    setMessages((prev) => {
      const next = [...prev, message];
      saveMessages(next);
      return next;
    });
  }, []);

  const ask = useCallback(
    async (question, documentIds = []) => {
      const scope = [...documentIds];
      append({
        id: nextId(),
        role: 'user',
        text: question,
        documentIds: scope,
        createdAt: new Date().toISOString(),
      });
      setLoading(true);
      setError(null);
      try {
        const { data } = await api.post('/chat', {
          question,
          document_ids: scope,
        });
        append({
          id: nextId(),
          role: 'assistant',
          question,
          text: data.answer,
          documentIds: scope,
          evidenceStatus: data.evidence_status,
          // Defensive limit: never keep more than two sources even if the backend sends more.
          sources: (data.sources || []).slice(0, 2),
          verification: data.verification || null,
          createdAt: data.created_at || new Date().toISOString(),
        });
      } catch (err) {
        setError(errorDetail(err, 'The answer service could not be reached. Please try again.'));
      } finally {
        setLoading(false);
      }
    },
    [append]
  );

  // Remove only the messages that belong to the deleted document, leaving every
  // other document's conversation intact.
  const removeDocument = useCallback((documentId) => {
    if (!documentId) return;
    setMessages((prev) => {
      const next = prev.filter((m) => !(m.documentIds || []).includes(documentId));
      if (next.length !== prev.length) saveMessages(next);
      return next;
    });
  }, []);

  return { messages, loading, error, ask, removeDocument };
}
