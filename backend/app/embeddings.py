"""Persistent, per-session vector storage using Postgres + pgvector (e.g.
Supabase's free tier).

Why this instead of the old local ChromaDB:
- Supabase's free Postgres survives restarts/redeploys. Render's free web
  service tier wipes local disk on every restart, which is what made the
  Chroma-on-disk approach non-durable there — this fixes that for free.
- Same isolation model as before: every row is scoped by `session_id`, so
  one visitor's chunks are never retrievable by another.
- Public surface (`add_chunks`, `remove_source`, `sources`, `retrieve`,
  `clear`, `is_empty`) is unchanged, so main.py didn't need to change shape.
"""
from typing import List, Tuple

import numpy as np
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from .db import get_conn, put_conn

# Loaded once per process, shared across sessions/requests.
_model = SentenceTransformer("all-MiniLM-L6-v2")
EMBED_DIM = 384


def _embed(texts: List[str]) -> List[list]:
    return _model.encode(texts, normalize_embeddings=True).tolist()


class DocumentStore:
    """Retrieval store scoped to a single session (i.e. a single visitor)."""

    def __init__(self, session_id: str):
        self.session_id = session_id

    def is_empty(self) -> bool:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM chunks WHERE session_id=%s LIMIT 1", (self.session_id,)
                )
                return cur.fetchone() is None
        finally:
            put_conn(conn)

    def clear(self) -> int:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE session_id=%s", (self.session_id,))
            conn.commit()
        finally:
            put_conn(conn)
        return 0

    def add_chunks(self, chunks: List[dict]) -> int:
        if not chunks:
            return self._count()
        embeddings = _embed([c["text"] for c in chunks])
        conn = get_conn()
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks (session_id, source, chunk_text, embedding) "
                    "VALUES (%s, %s, %s, %s)",
                    [
                        (self.session_id, c["source"], c["text"], emb)
                        for c, emb in zip(chunks, embeddings)
                    ],
                )
            conn.commit()
        finally:
            put_conn(conn)
        return self._count()

    def count(self) -> int:
        return self._count()

    def _count(self) -> int:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM chunks WHERE session_id=%s", (self.session_id,)
                )
                return cur.fetchone()[0]
        finally:
            put_conn(conn)

    def remove_source(self, source: str) -> int:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM chunks WHERE session_id=%s AND source=%s",
                    (self.session_id, source),
                )
            conn.commit()
        finally:
            put_conn(conn)
        return self._count()

    def sources(self) -> List[str]:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT source FROM chunks WHERE session_id=%s ORDER BY source",
                    (self.session_id,),
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            put_conn(conn)

    def retrieve(
        self, query: str, top_k: int = 3, use_mmr: bool = True, fetch_k: int = 10
    ) -> List[Tuple[dict, float]]:
        """Returns [(chunk_dict, relevance_score), ...].

        Fetches a wider `fetch_k` candidate pool by cosine distance (pgvector's
        `<=>` operator), then (optionally) re-ranks with Maximal Marginal
        Relevance so the final top_k passages are relevant AND non-redundant.
        """
        if self.is_empty():
            return []

        q_emb = np.array(_embed([query])[0], dtype=np.float32)
        conn = get_conn()
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(
    """
    SELECT
        source,
        chunk_text,
        embedding,
        1 - (embedding <=> %s::vector) AS score
    FROM chunks
    WHERE session_id = %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
    """,
    (q_emb, self.session_id, q_emb, max(fetch_k, top_k)),
)
                rows = cur.fetchall()
        finally:
            put_conn(conn)

        candidates = [
            ({"source": r[0], "text": r[1]}, float(r[3]), np.array(r[2], dtype=float))
            for r in rows
        ]

        if use_mmr and len(candidates) > top_k:
            return self._mmr(np.array(q_emb, dtype=float), candidates, top_k)
        return [(c[0], c[1]) for c in candidates[:top_k]]

    def _mmr(self, q_emb: np.ndarray, candidates, top_k: int, lambda_mult: float = 0.6):
        doc_embeddings = [c[2] for c in candidates]

        def cos(a, b):
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

        sim_to_query = {i: cos(doc_embeddings[i], q_emb) for i in range(len(candidates))}
        selected: List[int] = []
        remaining = list(range(len(candidates)))

        while remaining and len(selected) < top_k:
            if not selected:
                next_idx = max(remaining, key=lambda i: sim_to_query[i])
            else:
                def mmr_score(i):
                    diversity = max(cos(doc_embeddings[i], doc_embeddings[j]) for j in selected)
                    return lambda_mult * sim_to_query[i] - (1 - lambda_mult) * diversity

                next_idx = max(remaining, key=mmr_score)
            selected.append(next_idx)
            remaining.remove(next_idx)

        return [(candidates[i][0], candidates[i][1]) for i in selected]
