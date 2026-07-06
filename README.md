# Marginalia — AI Q&A over your documents

A full rebuild of the original Streamlit + Ollama prototype into a deployable
web app: durable persistence, per-session isolation with signed tokens,
optional original-file storage, OCR fallback for scanned PDFs, better
retrieval, and streaming answers — using one extra free service (Supabase).

```
React (Vite) frontend  ──▶  FastAPI backend  ──▶  Groq API (Llama 3.3 / Gemma2)
                                   │
                                   ├──▶ Postgres + pgvector (Supabase free tier)
                                   │      - chunks + embeddings, per session
                                   │      - chat history, per session
                                   └──▶ Supabase Storage (optional)
                                          - original uploaded PDFs/TXT
```

## What's new in this version

| Area | Before | Now |
|---|---|---|
| Vector store | local ChromaDB, wiped on every Render free restart | **Postgres + pgvector** (Supabase free tier) — survives restarts/redeploys |
| Chat history | local SQLite, same restart problem | **Postgres**, same database as the vector store |
| Session isolation | any string in `X-Session-Id` was trusted as-is | backend **mints and HMAC-signs** session tokens; unsigned/forged/guessed ids are rejected and replaced |
| Uploaded files | processed once, then discarded | optionally persisted in **Supabase Storage**, re-downloadable from the Library panel |
| Scanned PDFs | text extraction silently returned nothing | falls back to **OCR** (Tesseract) when a PDF looks image-only |

### 1. Persistence — Postgres + pgvector instead of local ChromaDB/SQLite
Render's **free** web services wipe local disk on every restart/redeploy, so
anything written to disk (the old Chroma directory, the old SQLite file)
didn't survive. Supabase's free Postgres project does not reset on restart,
so moving both the vector store and chat history there fixes this for free.
`embeddings.py` and `history.py` keep the same function signatures as
before, scoped by `session_id` — one visitor's data is still never
retrievable by another.

### 2. Session hardening — signed tokens instead of trust-whatever-arrives
**This is still not real authentication.** Before, the backend treated
whatever string showed up in `X-Session-Id` as a valid isolation key — so a
guessed or made-up id worked just as well as a real one. Now the backend
mints session ids itself and signs them with HMAC (`SESSION_SECRET`); an
unsigned, tampered, or invented token is rejected and silently replaced with
a freshly minted one (see `session_auth.py`, `main.py`'s `resolve_session`).
What this buys you: nobody can forge or brute-force their way into a
session that wasn't issued to them. What it does **not** buy you: if a
token is intercepted or leaked (e.g. shared link, browser history, logs),
whoever has it can use it — same limitation as any bearer token without a
login behind it. Real auth (Supabase Auth or Clerk, tying the session to an
actual logged-in account) is the right next step for anything beyond a demo.

### 3. Original-file persistence — optional, via Supabase Storage
The vector store only ever holds extracted text chunks, not the original
bytes. If `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` are set, uploaded files
are also saved to a Supabase Storage bucket, and a download button appears
in the Library panel next to each source. Leave those env vars unset and
the app behaves exactly as before (chunks only, no original file
retrievable) — this feature is additive, not required.

### 4. OCR fallback for scanned PDFs
If a PDF's extracted-text-per-page falls below a low threshold (a strong
signal it's a scanned image rather than real text), the backend tries OCR
via `pytesseract` + `pdf2image`. This needs the `tesseract-ocr` and
`poppler-utils` **system binaries**, which is why the backend now deploys
via the included `Dockerfile` rather than Render's plain Python buildpack
(which can't apt-get install system packages). If you deploy without
Docker, OCR silently no-ops and you just get whatever normal extraction
found — it won't break the upload.

## Project structure

```
backend/            FastAPI app
  app/
    main.py         API routes, session handling, streaming endpoint
    db.py           Postgres connection pool + schema bootstrap
    document_loader.py   PDF/TXT loading + chunking + OCR fallback
    embeddings.py   Postgres/pgvector-backed per-session store + MMR retrieval
    history.py      Postgres-backed per-session chat history
    file_storage.py Supabase Storage client for original files (optional)
    session_auth.py HMAC-signed session tokens
    llm_handler.py  Groq API client (regular + streaming)
  requirements.txt
  Dockerfile        needed for OCR system binaries; used by render.yaml
  render.yaml       one-click Render deploy config (Docker env)
  Procfile          fallback start command for non-Docker hosts (no OCR)
  .env.example

frontend/           React + Vite app
  src/
    App.jsx
    api.js          fetch wrapper, signed session token, SSE stream reader
    components/     UploadPanel, DocumentList, SettingsPanel, ChatFeed, Composer
  vercel.json
  .env.example
```

## One-time setup: Supabase (free)

1. Create a project at [supabase.com](https://supabase.com) (free tier).
2. **Database**: Project Settings → Database → Connection string → URI.
   Copy it into `DATABASE_URL`. The `vector` extension and all tables are
   created automatically on backend startup (see `db.py`'s `init_db`) —
   nothing to run by hand.
3. **Storage** (optional, only for original-file downloads): Storage → New
   bucket → name it `documents` → keep it **private**. Copy Project
   Settings → API → Project URL into `SUPABASE_URL`, and the **`service_role`**
   secret key (not `anon`) into `SUPABASE_SERVICE_KEY`.
4. Generate a session-signing secret: `python -c "import secrets; print(secrets.token_hex(32))"`
   → put it in `SESSION_SECRET`.

## Run locally

**Backend**
```bash
cd backend
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env        # fill in GROQ_API_KEY, DATABASE_URL, etc. (see above)
uvicorn app.main:app --reload --port 8000
```
Get a free Groq key in about a minute at https://console.groq.com/keys.

OCR needs `tesseract-ocr` and `poppler-utils` installed locally too
(`apt install tesseract-ocr poppler-utils` on Debian/Ubuntu, `brew install
tesseract poppler` on macOS) — optional; without them, OCR just no-ops.

**Frontend**
```bash
cd frontend
npm install
cp .env.example .env        # VITE_API_URL=http://localhost:8000
npm run dev
```
Open http://localhost:5173, upload a PDF/TXT, and ask a question.

## Deploy for free (~20 minutes)

**1. Backend → Render**
- Push this repo to GitHub.
- On [Render](https://render.com), "New +" → "Web Service" → connect the
  repo, root directory `backend`. Render picks up `render.yaml`, which uses
  the included `Dockerfile` (needed for OCR's system binaries).
- Add env vars: `GROQ_API_KEY`, `DATABASE_URL`, `SESSION_SECRET`, and
  (optional) `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` / `SUPABASE_BUCKET`.
- After it deploys, set `ALLOWED_ORIGINS` to your Vercel URL once you have
  it (step 2), and redeploy.

**2. Frontend → Vercel**
- On [Vercel](https://vercel.com), "New Project" → import the repo, root
  directory `frontend`.
- Add environment variable `VITE_API_URL` = your Render backend URL.
- Deploy. Vercel builds with `npm run build` automatically.

**3. Connect them**
- Copy the Vercel URL into the backend's `ALLOWED_ORIGINS` env var on
  Render and redeploy the backend so CORS allows the frontend to call it.

## Next steps (if you want to keep leveling this up)

1. **Real auth**: Supabase Auth or Clerk, both free-tier, both with a
   straightforward React SDK. Swap the signed-anonymous-session model for
   an actual logged-in user id as the isolation key — the isolation
   mechanism (scoping every row by an id) doesn't change, only where that
   id comes from.
2. **Source highlighting inside the PDF**: now that original files persist
   in Storage, render the actual PDF page and highlight the retrieved
   passage on it, instead of showing it as plain text.
3. **Semantic chunking**: split on sentence/section boundaries instead of
   fixed character windows, for cleaner retrieval on longer documents.
4. **pgvector index tuning**: the current setup does an exact (brute-force)
   nearest-neighbor scan per session, which is fine at small-per-session
   scale. If any single session's document set gets large, add an `ivfflat`
   or `hnsw` index on the `embedding` column for approximate search.
