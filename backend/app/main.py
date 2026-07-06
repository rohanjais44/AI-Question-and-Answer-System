import json as json_lib
import os
import tempfile
from typing import List, Optional

from dotenv import load_dotenv

# Load .env BEFORE importing modules that read environment variables
load_dotenv()

from fastapi import Depends, FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import db, file_storage, history, session_auth
from .document_loader import DocumentLoader
from .embeddings import DocumentStore
from .llm_handler import LLMHandler

app = FastAPI(title="AI Q&A System API")

allowed_origins = os.environ.get("ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The browser needs explicit permission to read this response header
    # cross-origin (frontend on Vercel, backend on Render) — without it,
    # `res.headers.get("X-Session-Id")` on the frontend silently returns null.
    expose_headers=["X-Session-Id"],
)


@app.on_event("startup")
def _startup():
    db.init_db()


def resolve_session(x_session_id: Optional[str]) -> tuple[str, Optional[str]]:
    """Returns (session_id, new_token_or_None).

    `x_session_id` must be a token this server signed (see session_auth.py).
    A missing or invalid token gets a freshly minted one instead of being
    trusted as-is — this is what stops a client from just inventing/guessing
    an id and having it treated as a valid isolation key.
    """
    session_id = session_auth.verify(x_session_id) if x_session_id else None
    if session_id is not None:
        return session_id, None
    new_token = session_auth.mint()
    return session_auth.verify(new_token), new_token


def get_session_id(
    response: Response, x_session_id: Optional[str] = Header(default=None)
) -> str:
    session_id, new_token = resolve_session(x_session_id)
    if new_token:
        response.headers["X-Session-Id"] = new_token
    return session_id


def get_store(session_id: str = Depends(get_session_id)) -> DocumentStore:
    return DocumentStore(session_id)


class AskRequest(BaseModel):
    question: str
    top_k: int = 3
    model: str = ""


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/models")
def list_models():
    return {"models": LLMHandler.get_available_models()}


@app.get("/api/documents")
def list_documents(store: DocumentStore = Depends(get_store)):
    return {
        "sources": store.sources(),
        "chunk_count": store.count(),
        "file_storage_enabled": file_storage.enabled(),
    }


@app.post("/api/upload")
async def upload_documents(
    files: List[UploadFile] = File(...),
    session_id: str = Depends(get_session_id),
    store: DocumentStore = Depends(get_store),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    saved_paths = []
    original_bytes: dict[str, bytes] = {}
    content_types: dict[str, str] = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        for upload in files:
            if not upload.filename.lower().endswith((".pdf", ".txt")):
                continue
            data = await upload.read()
            dest = os.path.join(tmp_dir, upload.filename)
            with open(dest, "wb") as f:
                f.write(data)
            saved_paths.append(dest)
            original_bytes[upload.filename] = data
            content_types[upload.filename] = upload.content_type or "application/octet-stream"

        if not saved_paths:
            raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported")

        records = DocumentLoader.load_documents(saved_paths)

    if not records:
        raise HTTPException(status_code=422, detail="Could not extract any text from the uploaded file(s)")

    total_chunks = store.add_chunks(records)

    # Persist the original file bytes too (optional — only if Supabase
    # Storage is configured), so the file can be re-downloaded later even
    # though only its extracted chunks live in pgvector.
    if file_storage.enabled():
        for filename, data in original_bytes.items():
            try:
                path = file_storage.upload(session_id, filename, data, content_types[filename])
                db.record_file(session_id, filename, path, content_types[filename])
            except Exception as e:
                print(f"Warning: could not persist original file {filename}: {e}")

    return {
        "uploaded": [os.path.basename(p) for p in saved_paths],
        "chunk_count": total_chunks,
        "sources": store.sources(),
        "file_storage_enabled": file_storage.enabled(),
    }


@app.get("/api/documents/{source}/download")
def download_document(source: str, session_id: str = Depends(get_session_id)):
    if not file_storage.enabled():
        raise HTTPException(
            status_code=404,
            detail="File storage isn't configured on this deployment (SUPABASE_URL/SUPABASE_SERVICE_KEY unset)",
        )
    row = db.get_file(session_id, source)
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Original file not found (it may predate file storage being enabled)",
        )
    storage_path, content_type = row
    try:
        data = file_storage.download(storage_path)
    except Exception:
        raise HTTPException(status_code=502, detail="Could not fetch the file from storage")
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{source}"'},
    )


@app.delete("/api/documents/{source}")
def delete_document(
    source: str, session_id: str = Depends(get_session_id), store: DocumentStore = Depends(get_store)
):
    remaining = store.remove_source(source)
    db.delete_file_record(session_id, source)
    return {"chunk_count": remaining, "sources": store.sources()}


@app.delete("/api/documents")
def clear_documents(session_id: str = Depends(get_session_id), store: DocumentStore = Depends(get_store)):
    store.clear()
    db.delete_file_record(session_id)
    return {"chunk_count": 0, "sources": []}


def _retrieve_or_400(store: DocumentStore, question: str, top_k: int):
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if store.is_empty():
        raise HTTPException(status_code=400, detail="Upload at least one document first")
    results = store.retrieve(question, top_k=top_k)
    if not results:
        raise HTTPException(status_code=404, detail="No relevant content found")
    return results


@app.post("/api/ask")
def ask_question(
    payload: AskRequest,
    session_id: str = Depends(get_session_id),
    store: DocumentStore = Depends(get_store),
):
    results = _retrieve_or_400(store, payload.question, payload.top_k)
    context = "\n\n".join(chunk["text"] for chunk, _ in results)
    sources = [
        {"source": chunk["source"], "excerpt": chunk["text"][:280], "score": round(score, 4)}
        for chunk, score in results
    ]

    llm = LLMHandler(model_name=payload.model or None)
    try:
        answer = llm.generate_answer(context, payload.question)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    history.save_turn(session_id, payload.question, answer, sources)
    return {"answer": answer, "sources": sources}


@app.post("/api/ask/stream")
def ask_question_stream(payload: AskRequest, x_session_id: Optional[str] = Header(default=None)):
    """Server-Sent-Events endpoint: emits a `sources` event first, then a
    stream of `token` events as Groq generates the answer, then `done`.

    Handled manually (rather than via Depends(get_session_id)) because this
    endpoint returns its own StreamingResponse, and headers set on a
    dependency-injected Response aren't reliably merged into a Response
    object the handler constructs and returns itself.
    """
    session_id, new_token = resolve_session(x_session_id)
    store = DocumentStore(session_id)

    results = _retrieve_or_400(store, payload.question, payload.top_k)
    context = "\n\n".join(chunk["text"] for chunk, _ in results)
    sources = [
        {"source": chunk["source"], "excerpt": chunk["text"][:280], "score": round(score, 4)}
        for chunk, score in results
    ]
    llm = LLMHandler(model_name=payload.model or None)

    def event_stream():
        yield f"data: {json_lib.dumps({'type': 'sources', 'sources': sources})}\n\n"
        chunks: List[str] = []
        try:
            for token in llm.generate_answer_stream(context, payload.question):
                chunks.append(token)
                yield f"data: {json_lib.dumps({'type': 'token', 'text': token})}\n\n"
        except RuntimeError as e:
            yield f"data: {json_lib.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return
        answer = "".join(chunks)
        history.save_turn(session_id, payload.question, answer, sources)
        yield f"data: {json_lib.dumps({'type': 'done'})}\n\n"

    resp = StreamingResponse(event_stream(), media_type="text/event-stream")
    if new_token:
        resp.headers["X-Session-Id"] = new_token
    return resp


@app.get("/api/history")
def get_history(session_id: str = Depends(get_session_id)):
    return {"turns": history.get_history(session_id)}


@app.delete("/api/history")
def delete_history(session_id: str = Depends(get_session_id)):
    history.clear_history(session_id)
    return {"turns": []}
