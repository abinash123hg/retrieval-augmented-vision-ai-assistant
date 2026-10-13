import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../api/client';
import { errorDetail } from '../utils/formatters';

const ACTIVE_STATUSES = new Set(['waiting', 'processing']);
const POLL_INTERVAL_MS = 2500;
const MAX_POLL_MS = 10 * 60 * 1000;

export default function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  // Deadline for the current polling run; a ref so re-renders don't reset it.
  const pollDeadline = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get('/documents');
      setDocuments(data.documents);
      setError(null);
    } catch (err) {
      setError(errorDetail(err, 'Could not load the document list. Is the backend running?'));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const hasActive = documents.some((d) => ACTIVE_STATUSES.has(d.processing_status));
    if (!hasActive) {
      pollDeadline.current = null;
      return undefined;
    }
    if (pollDeadline.current === null) {
      pollDeadline.current = Date.now() + MAX_POLL_MS;
    }
    const timer = setInterval(() => {
      if (Date.now() >= pollDeadline.current) {
        clearInterval(timer);
        pollDeadline.current = null;
        setError('Document processing is taking longer than expected. Refresh to check its status.');
        return;
      }
      refresh();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  const upload = useCallback(
    async (file, onProgress) => {
      setBusy(true);
      try {
        const form = new FormData();
        form.append('file', file);
        const { data } = await api.post('/documents/upload', form, {
          onUploadProgress: (e) => {
            const pct = e.total ? Math.round((e.loaded / e.total) * 100) : 0;
            if (onProgress) onProgress(pct);
          },
        });
        await refresh();
        return data;
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const remove = useCallback(
    async (id) => {
      setBusy(true);
      try {
        await api.delete(`/documents/${id}`);
        await refresh();
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  return { documents, busy, error, refresh, upload, remove };
}
