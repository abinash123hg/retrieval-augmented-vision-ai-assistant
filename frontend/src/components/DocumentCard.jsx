import { useState } from 'react';
import { AlertTriangle, Check, FileImage, FileText, Trash2, X } from 'lucide-react';
import ProcessingStatus from './ProcessingStatus';
import { formatBytes, formatRelativeTime } from '../utils/formatters';

const STATUS_META = {
  waiting: { label: 'Waiting', cls: 'waiting' },
  processing: { label: 'Processing', cls: 'processing' },
  ready: { label: 'Ready', cls: 'ready' },
  partially_processed: { label: 'Partially processed', cls: 'partial' },
  failed: { label: 'Failed', cls: 'failed' },
};

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg'];

function isImage(doc) {
  const type = (doc.file_type || '').toLowerCase();
  const name = (doc.file_name || '').toLowerCase();
  return IMAGE_EXTENSIONS.some((ext) => type.includes(ext) || name.endsWith(`.${ext}`));
}

export default function DocumentCard({ document: doc, onDelete }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const status = STATUS_META[doc.processing_status] || {
    label: doc.processing_status,
    cls: 'waiting',
  };
  const Icon = isImage(doc) ? FileImage : FileText;

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  };

  return (
    <article className="doc-card">
      <span className="doc-card-icon" aria-hidden="true">
        <Icon size={20} />
      </span>
      <div className="doc-card-body">
        <p className="doc-card-name" title={doc.file_name}>
          {doc.file_name}
        </p>
        <p className="doc-card-meta">
          <span>{formatBytes(doc.file_size)}</span>
          {doc.page_count != null && <span>{doc.page_count} pages</span>}
          <span>{formatRelativeTime(doc.upload_time)}</span>
        </p>
        {doc.processing_status === 'failed' && doc.error_message && (
          <p className="doc-card-error">
            <AlertTriangle size={13} aria-hidden="true" /> {doc.error_message}
          </p>
        )}
        {(doc.processing_status === 'waiting' || doc.processing_status === 'processing') && (
          <ProcessingStatus status={doc.processing_status} ocrPages={doc.ocr_pages} />
        )}
      </div>
      <div className="doc-card-side">
        <span className={`badge badge-${status.cls}`}>
          <span className="badge-dot" aria-hidden="true" />
          {status.label}
        </span>
        {!confirming ? (
          <button
            type="button"
            className="icon-btn icon-btn-danger"
            onClick={() => setConfirming(true)}
            aria-label={`Delete ${doc.file_name}`}
            title="Delete document"
          >
            <Trash2 size={15} />
          </button>
        ) : (
          <span className="confirm-row">
            <button
              type="button"
              className="icon-btn icon-btn-danger"
              onClick={confirmDelete}
              disabled={deleting}
              aria-label="Confirm delete"
              title="Confirm delete"
            >
              <Check size={15} />
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={() => setConfirming(false)}
              disabled={deleting}
              aria-label="Cancel delete"
              title="Cancel"
            >
              <X size={15} />
            </button>
          </span>
        )}
      </div>
    </article>
  );
}
