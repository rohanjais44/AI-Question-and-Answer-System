"""Per-session chat history, persisted in Postgres (same database as the
vector store — see embeddings.py / db.py). This is what makes chat history
survive a Render free-tier restart, which the old local SQLite file did not.
"""
import json
from typing import List, Optional

from .db import get_conn, put_conn


def save_turn(session_id: str, question: str, answer: str, sources: Optional[list] = None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO history (session_id, question, answer, sources) "
                "VALUES (%s, %s, %s, %s)",
                (session_id, question, answer, json.dumps(sources or [])),
            )
        conn.commit()
    finally:
        put_conn(conn)


def get_history(session_id: str, limit: int = 100) -> List[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, question, answer, sources, extract(epoch from created_at) "
                "FROM history WHERE session_id = %s ORDER BY id ASC LIMIT %s",
                (session_id, limit),
            )
            rows = cur.fetchall()
    finally:
        put_conn(conn)
    return [
        {
            "id": row_id,
            "question": q,
            "answer": a,
            "sources": s or [],  # psycopg2 already decodes jsonb into a list
            "created_at": t,
        }
        for row_id, q, a, s, t in rows
    ]


def clear_history(session_id: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM history WHERE session_id = %s", (session_id,))
        conn.commit()
    finally:
        put_conn(conn)
