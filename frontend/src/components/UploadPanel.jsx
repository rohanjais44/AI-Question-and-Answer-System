import { useRef, useState } from "react";

export default function UploadPanel({ onUpload, uploading, statusMessage, statusError }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = (fileList) => {
    const files = Array.from(fileList).filter((f) =>
      /\.(pdf|txt)$/i.test(f.name)
    );
    if (files.length > 0) onUpload(files);
  };

  return (
    <div
      className={`dropzone ${dragging ? "dragging" : ""}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      <span className="dropzone-icon">📄</span>
      <div className="dropzone-text">
        {uploading ? (
          "Uploading & indexing…"
        ) : (
          <>
            <strong>Click to upload</strong> or drop PDF / TXT files
          </>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.txt"
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
      />
      {statusMessage && (
        <div className={`upload-status ${statusError ? "error" : ""}`}>
          {statusMessage}
        </div>
      )}
    </div>
  );
}
