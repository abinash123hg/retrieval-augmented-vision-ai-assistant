import { FileSearch } from 'lucide-react';

export default function EmptyState() {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">
        <FileSearch size={40} />
      </span>
      <h2 className="empty-title">Upload a document to begin.</h2>
      <p className="empty-text">
        You can ask questions about its text, tables and important sections.
      </p>
    </div>
  );
}
