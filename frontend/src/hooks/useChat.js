import { useCallback, useState } from 'react';
import api from '../api/client';
import { errorDetail } from '../utils/formatters';

const STORAGE_KEY = 'doculens.chat.messages';

function loadMessages() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
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
      append({
        id: nextId(),
        role: 'user',
        text: question,
        createdAt: new Date().toISOString(),
      });
      setLoading(true);
      setError(null);
      try {
        const { data } = await api.post('/chat', {
          question,
          document_ids: documentIds,
        });
        append({
          id: nextId(),
          role: 'assistant',
          question,
          text: data.answer,
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

  return { messages, loading, error, ask };
}
