import { useState } from 'react';
import { FileDown } from 'lucide-react';
import api from '../api/client';
import { useToast } from './Toast';
import { errorDetail } from '../utils/formatters';

export default function ReportButton({ question, answer, evidenceStatus, sources }) {
  const [generating, setGenerating] = useState(false);
  const showToast = useToast();

  const generate = async () => {
    setGenerating(true);
    try {
      const { data } = await api.post('/reports', {
        question,
        answer,
        evidence_status: evidenceStatus,
        sources,
      });
      // download_url is a path like /api/reports/{id}/download; strip /api since it is the baseURL
      const res = await api.get(data.download_url.replace(/^\/api/, ''), {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = data.file_name || 'report.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast('Report downloaded', 'success');
    } catch (err) {
      const detail =
        err.response?.data instanceof Blob
          ? `Report generation failed (HTTP ${err.response.status}).`
          : errorDetail(err, 'Report generation failed.');
      showToast(detail, 'error');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <button
      type="button"
      className="btn btn-quiet"
      onClick={generate}
      disabled={generating}
      title="Download this answer as a PDF report"
    >
      {generating ? (
        <span className="spinner" aria-hidden="true" />
      ) : (
        <FileDown size={14} aria-hidden="true" />
      )}
      {generating ? 'Generating…' : 'Download report'}
    </button>
  );
}
