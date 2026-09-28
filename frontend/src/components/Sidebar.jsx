import UploadPanel from './UploadPanel';
import DocumentCard from './DocumentCard';
import SummaryPanel from './SummaryPanel';

export default function Sidebar({ documents, onUpload, onDelete }) {
  return (
    <>
      <UploadPanel onUpload={onUpload} />
      <section className="sidebar-section">
        <h2 className="sidebar-title">
          Documents <span className="sidebar-count">{documents.length}</span>
        </h2>
        {documents.length === 0 ? (
          <p className="sidebar-empty">No documents yet.</p>
        ) : (
          <div className="document-list">
            {documents.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={() => onDelete(doc.id)}
              />
            ))}
          </div>
        )}
      </section>
      <SummaryPanel documents={documents} />
    </>
  );
}
