const STATUS_TEXT = {
  waiting: 'Waiting in queue…',
  processing: 'Extracting text… Building search index…',
};

export default function ProcessingStatus({ status, ocrPages }) {
  const text = STATUS_TEXT[status] || 'Processing…';
  return (
    <p className="processing-status">
      <span className="spinner" aria-hidden="true" />
      <span>
        {text}
        {ocrPages > 0 && ` (${ocrPages} OCR page${ocrPages > 1 ? 's' : ''})`}
      </span>
    </p>
  );
}
