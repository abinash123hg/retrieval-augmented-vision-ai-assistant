import { useEffect, useState } from 'react';
import api from './api/client';
import useDocuments from './hooks/useDocuments';
import useChat from './hooks/useChat';
import { useToast } from './components/Toast';
import { errorDetail } from './utils/formatters';
import Layout from './components/Layout';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';

export default function App() {
  const [health, setHealth] = useState(null);
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

  const handleDelete = async (id) => {
    try {
      await docs.remove(id);
      showToast('Document deleted', 'success');
    } catch (err) {
      showToast(errorDetail(err, 'Could not delete the document.'), 'error');
    }
  };

  const handleAsk = (question) => {
    // empty document_ids = search across all documents
    chat.ask(question, []);
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
        messages={chat.messages}
        loading={chat.loading}
        onAsk={handleAsk}
      />
    </Layout>
  );
}
