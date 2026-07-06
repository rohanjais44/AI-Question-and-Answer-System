"""Original-file persistence via Supabase Storage (S3-compatible object
storage, free tier).

Postgres/pgvector (embeddings.py) only ever stores the extracted text
chunks, not the original bytes — so without this, an uploaded PDF is
processed once and then gone, and there's no way to re-download it,
re-view it, or eventually highlight source pages inside it.

This module is optional: if SUPABASE_URL / SUPABASE_SERVICE_KEY aren't set,
`enabled()` returns False and the app falls back to its old behavior
(process the file, keep only the chunks).
"""
import os

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "documents")

_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def enabled() -> bool:
    return _ENABLED


def _headers(content_type: str = None) -> dict:
    # The service_role key is required (not the anon/public key) since the
    # backend reads/writes on behalf of arbitrary sessions, not a logged-in
    # Supabase Auth user — anon key + RLS would block that.
    h = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


def upload(session_id: str, filename: str, data: bytes, content_type: str) -> str:
    """Uploads bytes, returns the storage path used to look it up later."""
    path = f"{session_id}/{filename}"
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}"
    resp = requests.post(
        url,
        headers={**_headers(content_type or "application/octet-stream"), "x-upsert": "true"},
        data=data,
        timeout=30,
    )
    resp.raise_for_status()
    return path


def download(storage_path: str) -> bytes:
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    resp = requests.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.content


def delete(storage_path: str):
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    try:
        requests.delete(url, headers=_headers(), timeout=15)
    except requests.RequestException:
        pass  # best-effort cleanup; chunk deletion is the source of truth
