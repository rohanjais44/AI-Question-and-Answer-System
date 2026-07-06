
import os

from psycopg2 import pool

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Create a free Supabase project, then copy "
        "Project Settings -> Database -> Connection string (URI) into "
        "DATABASE_URL. See README for the full walkthrough."
    )

_pool = pool.SimpleConnectionPool(1, 5, dsn=DATABASE_URL)


def get_conn():
    return _pool.getconn()


def put_conn(conn):
    _pool.putconn(conn)


def init_db():
    """Idempotent — safe to call on every process start."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding vector(384) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS chunks_session_idx ON chunks (session_id);")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS chunks_session_source_idx ON chunks (session_id, source);"
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    sources JSONB,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS history_session_idx ON history (session_id);")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    content_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (session_id, source)
                );
                """
            )
        conn.commit()
    finally:
        put_conn(conn)


def record_file(session_id: str, source: str, storage_path: str, content_type: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO files (session_id, source, storage_path, content_type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id, source) DO UPDATE
                SET storage_path = EXCLUDED.storage_path,
                    content_type = EXCLUDED.content_type
                """,
                (session_id, source, storage_path, content_type),
            )
        conn.commit()
    finally:
        put_conn(conn)


def get_file(session_id: str, source: str):
    """Returns (storage_path, content_type) or None."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT storage_path, content_type FROM files WHERE session_id=%s AND source=%s",
                (session_id, source),
            )
            return cur.fetchone()
    finally:
        put_conn(conn)


def delete_file_record(session_id: str, source: str = None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if source is None:
                cur.execute("DELETE FROM files WHERE session_id=%s", (session_id,))
            else:
                cur.execute(
                    "DELETE FROM files WHERE session_id=%s AND source=%s", (session_id, source)
                )
        conn.commit()
    finally:
        put_conn(conn)
