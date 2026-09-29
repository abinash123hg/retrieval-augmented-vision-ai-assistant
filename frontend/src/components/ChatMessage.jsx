import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import SourceCard from './SourceCard';
import ReportButton from './ReportButton';
import { useToast } from './Toast';

const MAX_SOURCES = 2;

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

  const sources = (message.sources || []).slice(0, MAX_SOURCES);

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
            sources={sources}
          />
        </div>
        {sources.length > 0 && (
          <div className="sources-block">
            <h3 className="sources-heading">Sources used for this answer</h3>
            {sources.map((s, i) => (
              <SourceCard key={`${s.document_name}-${s.page_number}-${i}`} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
