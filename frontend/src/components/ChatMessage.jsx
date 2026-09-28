import { useState } from 'react';
import { AlertTriangle, Check, Copy, ShieldCheck } from 'lucide-react';
import SourceCard from './SourceCard';
import ReportButton from './ReportButton';
import { useToast } from './Toast';

const EVIDENCE_META = {
  supported: { label: 'Supported', cls: 'ok' },
  partially_supported: { label: 'Partially supported', cls: 'warn' },
  not_found: { label: 'Not found', cls: 'bad' },
  conflicting_sources: { label: 'Conflicting sources', cls: 'warn' },
  low_quality_source: { label: 'Low-quality source', cls: 'warn' },
};

export default function ChatMessage({ message }) {
  const [copied, setCopied] = useState(false);
  const showToast = useToast();

  if (message.role === 'user') {
    return (
      <div className="chat-row chat-row-user">
        <p className="chat-bubble-user">{message.text}</p>
      </div>
    );
  }

  const evidence = EVIDENCE_META[message.evidenceStatus];
  const warnings = message.verification?.warnings || [];

  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      showToast('Could not copy to the clipboard.', 'error');
    }
  };

  return (
    <div className="chat-row chat-row-assistant">
      <div className="chat-msg">
        <p className="answer-text">{message.text}</p>
        <div className="chat-msg-footer">
          {evidence && (
            <span className={`evidence-badge evidence-${evidence.cls}`}>
              <ShieldCheck size={13} aria-hidden="true" />
              {evidence.label}
            </span>
          )}
          <button
            type="button"
            className="btn btn-quiet copy-btn"
            onClick={copyAnswer}
            title="Copy answer to clipboard"
          >
            {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
            {copied ? 'Copied' : 'Copy answer'}
          </button>
          <ReportButton
            question={message.question}
            answer={message.text}
            evidenceStatus={message.evidenceStatus}
            sources={message.sources}
          />
        </div>
        {warnings.length > 0 && (
          <div className="verification-box" role="note">
            <p className="verification-title">
              <AlertTriangle size={14} aria-hidden="true" /> Verification warnings
            </p>
            <ul>
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        {message.sources.length > 0 && (
          <div className="sources-block">
            <h3 className="sources-heading">Sources used for this answer</h3>
            {message.sources.map((s, i) => (
              <SourceCard key={`${s.document_name}-${s.page_number}-${i}`} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
