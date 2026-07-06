import { useEffect, useState } from "react";
import { api } from "./api";
import UploadPanel from "./components/UploadPanel";
import DocumentList from "./components/DocumentList";
import SettingsPanel from "./components/SettingsPanel";
import ChatFeed from "./components/ChatFeed";
import Composer from "./components/Composer";

const FALLBACK_MODELS = [
  { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B — best quality" },
  { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B — fastest" },
  { id: "gemma2-9b-it", label: "Gemma2 9B" },
];

export default function App() {
  const [sources, setSources] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState({ message: "", error: false });

  const [models, setModels] = useState(FALLBACK_MODELS);
  const [model, setModel] = useState(FALLBACK_MODELS[0].id);
  const [topK, setTopK] = useState(3);

  const [turns, setTurns] = useState([]);
  const [asking, setAsking] = useState(false);
  const [fileStorageEnabled, setFileStorageEnabled] = useState(false);

  useEffect(() => {
    api
      .listDocuments()
      .then((d) => {
        setSources(d.sources);
        setFileStorageEnabled(!!d.file_storage_enabled);
      })
      .catch(() => {});
    api
      .listModels()
      .then((d) => {
        if (d.models?.length) {
          setModels(d.models);
          setModel(d.models[0].id);
        }
      })
      .catch(() => {});

    // Restore this browser's previous conversation, if any.
    api
      .getHistory()
      .then((d) => {
        const restored = (d.turns || []).map((t) => ({
          id: `h-${t.id}`,
          question: t.question,
          status: "done",
          answer: t.answer,
          sources: t.sources,
        }));
        if (restored.length) setTurns(restored);
      })
      .catch(() => {});
  }, []);

  const handleUpload = async (files) => {
    setUploading(true);
    setUploadStatus({ message: "", error: false });
    try {
      const res = await api.uploadFiles(files);
      setSources(res.sources);
      setFileStorageEnabled(!!res.file_storage_enabled);
      setUploadStatus({
        message: `✓ Indexed ${res.uploaded.length} file(s) — ${res.chunk_count} chunks total`,
        error: false,
      });
    } catch (e) {
      setUploadStatus({ message: e.message, error: true });
    } finally {
      setUploading(false);
    }
  };

  const handleRemove = async (source) => {
    try {
      const res = await api.deleteDocument(source);
      setSources(res.sources);
    } catch (e) {
      setUploadStatus({ message: e.message, error: true });
    }
  };

  const handleDownload = async (source) => {
    try {
      await api.downloadDocument(source);
    } catch (e) {
      setUploadStatus({ message: e.message, error: true });
    }
  };

  const handleClearAllDocuments = async () => {
    try {
      const res = await api.clearDocuments();
      setSources(res.sources);
    } catch (e) {
      setUploadStatus({ message: e.message, error: true });
    }
  };

  const handleAsk = async (question) => {
    const id = crypto.randomUUID();
    setTurns((prev) => [...prev, { id, question, status: "loading", answer: "" }]);
    setAsking(true);

    try {
      await api.askStream(question, topK, model, (event) => {
        if (event.type === "sources") {
          setTurns((prev) =>
            prev.map((t) => (t.id === id ? { ...t, sources: event.sources } : t))
          );
        } else if (event.type === "token") {
          setTurns((prev) =>
            prev.map((t) =>
              t.id === id
                ? { ...t, status: "streaming", answer: (t.answer || "") + event.text }
                : t
            )
          );
        } else if (event.type === "error") {
          setTurns((prev) =>
            prev.map((t) => (t.id === id ? { ...t, status: "error", error: event.message } : t))
          );
        } else if (event.type === "done") {
          setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, status: "done" } : t)));
        }
      });
    } catch (e) {
      setTurns((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: "error", error: e.message } : t))
      );
    } finally {
      setAsking(false);
    }
  };

  const handleClearConversation = async () => {
    try {
      await api.clearHistory();
      setTurns([]);
    } catch (e) {
      setUploadStatus({ message: e.message, error: true });
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <span className="dot" />
            <h1>Marginalia</h1>
          </div>
          <p>AI Q&A over your documents</p>
        </div>

        <div className="sidebar-section">
          <p className="section-label">Upload</p>
          <UploadPanel
            onUpload={handleUpload}
            uploading={uploading}
            statusMessage={uploadStatus.message}
            statusError={uploadStatus.error}
          />
        </div>

        <div className="sidebar-section">
          <p className="section-label">Library ({sources.length})</p>
          <DocumentList
            sources={sources}
            onRemove={handleRemove}
            onClearAll={handleClearAllDocuments}
            onDownload={fileStorageEnabled ? handleDownload : undefined}
          />
        </div>

        <div className="sidebar-section">
          <p className="section-label">Settings</p>
          <SettingsPanel
            models={models}
            model={model}
            setModel={setModel}
            topK={topK}
            setTopK={setTopK}
          />
        </div>
      </aside>

      <main className="main">
        <div className="feed">
          <ChatFeed turns={turns} />
        </div>
        <Composer
          onSend={handleAsk}
          disabled={asking || sources.length === 0}
          onClear={turns.length > 0 ? handleClearConversation : undefined}
        />
      </main>
    </div>
  );
}
