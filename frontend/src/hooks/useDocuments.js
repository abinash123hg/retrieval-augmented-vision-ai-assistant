import { useCallback, useEffect, useState } from 'react';
import api from '../api/client';
import { errorDetail } from '../utils/formatters';

const ACTIVE_STATUSES = new Set(['waiting', 'processing']);
const POLL_INTERVAL_MS = 2500;

export default function useDocuments() {
  const [documents, setDocuments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
    if (!documents.some((d) => ACTIVE_STATUSES.has(d.processing_status))) return undefined;
    const timer = setInterval(refresh, POLL_INTERVAL_MS);
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
