import { useEffect, useRef, useState } from 'react';
import ChatMessage from './ChatMessage';
import EmptyState from './EmptyState';
import QuestionInput from './QuestionInput';

const EXAMPLE_QUESTIONS = [
  'What is the main purpose of this document?',
  'What was the total revenue?',
  'What are the important risks?',
  'Summarize this document.',
];

const ANSWERABLE_STATUSES = new Set(['ready', 'partially_processed']);

export default function ChatWindow({ documents, messages, loading, onAsk }) {
  const [question, setQuestion] = useState('');
  const bottomRef = useRef(null);
  const hasReadyDocument = documents.some((d) => ANSWERABLE_STATUSES.has(d.processing_status));

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const submit = (text) => {
    const trimmed = text.trim();
    if (!trimmed || loading || !hasReadyDocument) return;
    onAsk(trimmed);
    setQuestion('');
  };

  const showEmptyState = messages.length === 0 && documents.length === 0;
  const showChips = messages.length === 0 && !loading && hasReadyDocument;

  return (
    <div className="chat-window">
      <div className="chat-messages">
        {showEmptyState && <EmptyState />}
        {showChips && (
          <div className="chips-block">
            <p className="chips-heading">Try asking:</p>
            <div className="chips">
              {EXAMPLE_QUESTIONS.map((q) => (
                <button key={q} type="button" className="chip" onClick={() => setQuestion(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <ChatMessage key={m.id} message={m} />
        ))}
        {loading && (
          <div className="chat-msg" aria-label="Loading answer" aria-busy="true">
            <div className="skeleton-msg">
              <div className="skeleton-line" style={{ width: '90%' }} />
              <div className="skeleton-line" style={{ width: '75%' }} />
              <div className="skeleton-line" style={{ width: '60%' }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <QuestionInput
        value={question}
        onChange={setQuestion}
        onSubmit={submit}
        loading={loading}
        hasReadyDocument={hasReadyDocument}
      />
    </div>
  );
}
