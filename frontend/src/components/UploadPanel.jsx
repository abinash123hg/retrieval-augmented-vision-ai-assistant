import { useRef, useState } from 'react';
import { CheckCircle2, FolderOpen, UploadCloud, XCircle } from 'lucide-react';
import { useToast } from './Toast';
import { errorDetail } from '../utils/formatters';

const ACCEPTED_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg'];
const MAX_FILE_BYTES = 25 * 1024 * 1024;

function extensionOf(name) {
  const parts = name.toLowerCase().split('.');
  return parts.length > 1 ? parts[parts.length - 1] : '';
}

export default function UploadPanel({ onUpload }) {
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState([]);
  const inputRef = useRef(null);
  const showToast = useToast();

  const updateUpload = (key, patch) => {
    setUploads((prev) => prev.map((u) => (u.key === key ? { ...u, ...patch } : u)));
  };

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    for (const file of files) {
      const key = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`;
      if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) {
        showToast(`"${file.name}" is not supported. Accepted: PDF, PNG, JPG.`, 'error');
        continue;
      }
      if (file.size > MAX_FILE_BYTES) {
        showToast(`"${file.name}" is larger than 25 MB.`, 'error');
        continue;
      }
      if (file.size === 0) {
        showToast(`"${file.name}" is empty.`, 'error');
        continue;
      }
      setUploads((prev) => [...prev, { key, name: file.name, progress: 0, state: 'uploading' }]);
      // finished entries linger briefly, then clear so the panel stays tidy
      const scheduleDismiss = () => {
        setTimeout(() => {
          setUploads((prev) => prev.filter((u) => u.key !== key));
        }, 4000);
      };
      try {
        await onUpload(file, (pct) => updateUpload(key, { progress: pct }));
        updateUpload(key, { state: 'done', progress: 100 });
        showToast(`"${file.name}" uploaded`, 'success');
        scheduleDismiss();
      } catch (err) {
        const detail = errorDetail(err, `Upload of "${file.name}" failed.`);
        updateUpload(key, { state: 'error', error: detail });
        showToast(detail, 'error');
        scheduleDismiss();
      }
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <section className="sidebar-section">
      <div
        className={`upload-zone${dragging ? ' dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        role="button"
        tabIndex={0}
        aria-label="Upload documents: drag and drop files here or browse"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
        }}
      >
        <UploadCloud size={28} className="upload-zone-icon" aria-hidden="true" />
        <p className="upload-zone-text">Drag &amp; drop files here</p>
        <button
          type="button"
          className="btn btn-primary browse-btn"
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
        >
          <FolderOpen size={15} aria-hidden="true" /> Browse files
        </button>
        <p className="upload-zone-hint">PDF, PNG, JPG · Max 25 MB per file</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          multiple
          hidden
          onChange={(e) => {
            handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>
      {uploads.length > 0 && (
        <ul className="upload-list">
          {uploads.map((u) => (
            <li key={u.key} className="upload-item">
              <div className="upload-item-row">
                <span className="upload-item-name" title={u.name}>{u.name}</span>
                {u.state === 'done' && (
                  <span className="upload-item-state ok">
                    <CheckCircle2 size={14} aria-hidden="true" /> Done
                  </span>
                )}
                {u.state === 'error' && (
                  <span className="upload-item-state bad">
                    <XCircle size={14} aria-hidden="true" /> Failed
                  </span>
                )}
                {u.state === 'uploading' && (
                  <span className="upload-item-state">{u.progress}%</span>
                )}
              </div>
              {u.state === 'uploading' && (
                <div
                  className="upload-progress"
                  role="progressbar"
                  aria-valuenow={u.progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div className="upload-progress-bar" style={{ width: `${u.progress}%` }} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
