const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TOKEN_KEY = "qa_session_token";

// The session token is minted and signed by the backend (see
// backend/app/session_auth.py) — the frontend never invents its own id
// anymore. On first request (no stored token), the backend mints one and
// sends it back via the X-Session-Id response header; we store whatever
// comes back on every response, since the backend will also rotate/reissue
// it if it's ever missing or invalid.
function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function storeTokenFromResponse(res) {
  const token = res.headers.get("X-Session-Id");
  if (token) localStorage.setItem(TOKEN_KEY, token);
}

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { "X-Session-Id": token, ...extra } : { ...extra };
}

async function request(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  storeTokenFromResponse(res);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => request("/api/health"),

  listModels: () => request("/api/models"),

  listDocuments: () => request("/api/documents"),

  uploadFiles: (files) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request("/api/upload", { method: "POST", body: form });
  },

  deleteDocument: (source) =>
    request(`/api/documents/${encodeURIComponent(source)}`, { method: "DELETE" }),

  clearDocuments: () => request("/api/documents", { method: "DELETE" }),

  // Triggers a browser download of the originally-uploaded file. Only works
  // if the backend has Supabase Storage configured (SUPABASE_URL /
  // SUPABASE_SERVICE_KEY) — otherwise the backend returns a clear 404.
  async downloadDocument(source) {
    const res = await fetch(`${API_URL}/api/documents/${encodeURIComponent(source)}/download`, {
      headers: authHeaders(),
    });
    storeTokenFromResponse(res);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = source;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  ask: (question, topK, model) =>
    request("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: topK, model }),
    }),

  getHistory: () => request("/api/history"),

  clearHistory: () => request("/api/history", { method: "DELETE" }),

  // Streams the answer token-by-token via Server-Sent Events. `onEvent`
  // receives parsed events: {type: "sources"|"token"|"error"|"done", ...}.
  async askStream(question, topK, model, onEvent) {
    const res = await fetch(`${API_URL}/api/ask/stream`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ question, top_k: topK, model }),
    });
    storeTokenFromResponse(res);

    if (!res.ok || !res.body) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop(); // keep the last, possibly incomplete, chunk

      for (const raw of events) {
        const line = raw.trim();
        if (!line.startsWith("data:")) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  },
};
