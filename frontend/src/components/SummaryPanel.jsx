import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import api from '../api/client';
import { errorDetail } from '../utils/formatters';

const MODES = [
  { mode: 'short', label: 'Short summary' },
  { mode: 'detailed', label: 'Detailed summary' },
  { mode: 'key_points', label: 'Key points' },
];

export default function SummaryPanel({ documents }) {
  const [activeMode, setActiveMode] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const doc = documents.find(
    (d) => d.processing_status === 'ready' || d.processing_status === 'partially_processed'
  );
  if (!doc) return null;

  const loadSummary = async (mode) => {
    setActiveMode(mode);
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get(`/documents/${doc.id}/summary`, { params: { mode } });
      setSummary(data.summary);
    } catch (err) {
      setSummary(null);
      setError(errorDetail(err, 'Could not generate the summary.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="sidebar-section summary-panel">
      <h2 className="sidebar-title">
        <Sparkles size={15} aria-hidden="true" /> Summary
      </h2>
      <p className="summary-doc" title={doc.file_name}>
        {doc.file_name}
      </p>
      <div className="summary-buttons">
        {MODES.map(({ mode, label }) => (
          <button
            key={mode}
            type="button"
            className={`btn btn-quiet summary-btn${activeMode === mode ? ' active' : ''}`}
            onClick={() => loadSummary(mode)}
            disabled={loading}
          >
            {label}
          </button>
        ))}
      </div>
      {loading && (
        <div className="skeleton-msg summary-skeleton" aria-label="Loading summary">
          <div className="skeleton-line" style={{ width: '95%' }} />
          <div className="skeleton-line" style={{ width: '80%' }} />
          <div className="skeleton-line" style={{ width: '65%' }} />
        </div>
      )}
      {!loading && error && <p className="summary-error">{error}</p>}
      {!loading && summary && (
        <div className="summary-card">
          <p className="summary-text">{summary}</p>
        </div>
      )}
    </section>
  );
}
