export default function DocumentList({ sources, onRemove, onClearAll, onDownload }) {
  if (sources.length === 0) {
    return <p className="empty-note">No documents indexed yet.</p>;
  }

  return (
    <>
      <ul className="doc-list">
        {sources.map((source) => (
          <li key={source} className="doc-item">
            <span className="doc-name" title={source}>
              {source}
            </span>
            <span className="doc-actions">
              {onDownload && (
                <button
                  onClick={() => onDownload(source)}
                  title="Download original file"
                  aria-label="Download"
                >
                  ↓
                </button>
              )}
              <button onClick={() => onRemove(source)} title="Remove document" aria-label="Remove">
                ×
              </button>
            </span>
          </li>
        ))}
      </ul>
      {sources.length > 1 && (
        <button className="clear-link" style={{ marginTop: 10 }} onClick={onClearAll}>
          Clear all documents
        </button>
      )}
    </>
  );
}
