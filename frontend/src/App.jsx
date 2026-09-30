import { useEffect, useMemo, useState } from 'react';
import api from './api/client';
import useDocuments from './hooks/useDocuments';
import useChat, { scopeOf } from './hooks/useChat';
import { useToast } from './components/Toast';
import { errorDetail } from './utils/formatters';
import Layout from './components/Layout';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';

export default function App() {
  const [health, setHealth] = useState(null);
  // Single source of truth for the selected document scope. ChatWindow is
  // controlled by this so deletion and selection changes stay in sync.
  const [selectedDocId, setSelectedDocId] = useState('');
  const docs = useDocuments();
  const chat = useChat();
  const showToast = useToast();

  useEffect(() => {
    api
      .get('/health')
      .then(({ data }) => setHealth(data))
      .catch(() => setHealth({ status: 'unreachable', ollama: false }));
  }, []);

  useEffect(() => {
    if (docs.error) showToast(docs.error, 'error');
  }, [docs.error, showToast]);

  useEffect(() => {
    if (chat.error) showToast(chat.error, 'error');
  }, [chat.error, showToast]);

  // Show only the conversation that belongs to the current document scope.
  const currentScope = selectedDocId || 'all';
  const visibleMessages = useMemo(
    () => chat.messages.filter((m) => scopeOf(m) === currentScope),
    [chat.messages, currentScope]
  );

  const handleDelete = async (id) => {
    try {
      await docs.remove(id);
      // Remove the deleted document's conversation and clear the selection if
      // it was the active scope, so the chat starts clean.
      chat.removeDocument(id);
      setSelectedDocId((prev) => (prev === id ? '' : prev));
      showToast('Document deleted', 'success');
    } catch (err) {
      showToast(errorDetail(err, 'Could not delete the document.'), 'error');
    }
  };

  const handleAsk = (question) => {
    // empty scope = search across all documents; a selected document scopes the
    // question (and its stored history) to that document for isolation.
    chat.ask(question, selectedDocId ? [selectedDocId] : []);
  };

  return (
    <Layout
      health={health}
      sidebar={
        <Sidebar documents={docs.documents} onUpload={docs.upload} onDelete={handleDelete} />
      }
    >
      <ChatWindow
        documents={docs.documents}
        messages={visibleMessages}
        loading={chat.loading}
        selectedDocId={selectedDocId}
        onSelectDocument={setSelectedDocId}
        onAsk={handleAsk}
      />
    </Layout>
  );
}
