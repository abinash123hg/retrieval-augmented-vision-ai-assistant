import { SendHorizonal } from 'lucide-react';

export default function QuestionInput({ value, onChange, onSubmit, loading, hasReadyDocument }) {
  const empty = value.trim().length === 0;
  const disabled = empty || loading || !hasReadyDocument;

  let disabledReason = '';
  if (loading) disabledReason = 'Waiting for the current answer to finish…';
  else if (!hasReadyDocument) disabledReason = 'Ask is available once a document finishes processing.';
  else if (empty) disabledReason = 'Type a question first.';

  const handleKeyDown = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!disabled) onSubmit(value);
    }
  };

  return (
    <div className="question-bar">
      <textarea
        className="question-input"
        rows={2}
        value={value}
        placeholder="Ask a question about your documents…"
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        aria-label="Your question"
      />
      <button
        type="button"
        className="btn btn-primary ask-btn"
        disabled={disabled}
        title={disabledReason || 'Ask (Ctrl+Enter)'}
        onClick={() => onSubmit(value)}
      >
        <SendHorizonal size={16} aria-hidden="true" /> Ask
      </button>
    </div>
  );
}
