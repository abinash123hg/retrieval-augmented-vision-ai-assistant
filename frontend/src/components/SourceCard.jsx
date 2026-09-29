import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText } from 'lucide-react';

export default function SourceCard({ source }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <article className="source-card">
      <div className="source-card-header">
        <span className="source-doc">
          <FileText size={14} aria-hidden="true" />
          {source.document_name}
        </span>
        <span className="source-page">Page {source.page_number}</span>
      </div>
      {source.section && <p className="source-section">{source.section}</p>}
      <p
        className={`source-excerpt${expanded ? ' expanded' : ''}`}
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        title={expanded ? 'Click to collapse' : 'Click to expand'}
      >
        {source.excerpt}
      </p>
      <button
        type="button"
        className="source-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        {expanded ? (
          <>
            <ChevronUp size={13} aria-hidden="true" /> Show less
          </>
        ) : (
          <>
            <ChevronDown size={13} aria-hidden="true" /> Show more
          </>
        )}
      </button>
    </article>
  );
}
