import { ScanSearch } from 'lucide-react';

function HealthIndicator({ health }) {
  if (!health || health.status === 'loading') {
    return (
      <div className="health" title="Checking backend status…">
        <span className="health-dot health-dot-loading" aria-hidden="true" />
        <span className="health-label">Checking…</span>
      </div>
    );
  }
  if (!health.ollama || health.status === 'unreachable') {
    return (
      <div className="health" title="Ollama or the backend is not available — answers will fail until it is running.">
        <span className="health-dot health-dot-bad" aria-hidden="true" />
        <span className="health-label">
          {health.status === 'unreachable' ? 'Backend offline' : 'Ollama unavailable'}
        </span>
      </div>
    );
  }
  return (
    <div
      className="health"
      title={`Chat model: ${health.chat_model || 'unknown'}\nEmbedding model: ${health.embedding_model || 'unknown'}`}
    >
      <span className="health-dot health-dot-ok" aria-hidden="true" />
      <span className="health-label">Ollama connected</span>
    </div>
  );
}

export default function Layout({ health, sidebar, children }) {
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-icon" aria-hidden="true">
            <ScanSearch size={22} />
          </span>
          <div>
            <h1 className="brand-title">DocuLens</h1>
            <p className="brand-tagline">Ask your documents. Get grounded answers.</p>
          </div>
        </div>
        <HealthIndicator health={health} />
      </header>
      <div className="app-body">
        <aside className="sidebar">{sidebar}</aside>
        <main className="main">{children}</main>
      </div>
    </div>
  );
}
