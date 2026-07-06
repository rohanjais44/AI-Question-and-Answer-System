"""Lightweight session-token hardening.

This is NOT real authentication — see the README section on this. It does
not stop someone who intercepts or is handed a valid token from using it,
same as any bearer token sent over the wire. What it does fix: previously
the "session id" was just whatever string a client sent in X-Session-Id, so
any guessed, sequential, or made-up id was automatically a valid isolation
key for some session. Tokens are now minted and signed by the server, so a
client can only ever act as a session the server itself issued — an id
can't be forged or brute-forced into a valid one without the server's
secret.

Real auth (Supabase Auth / Clerk, tying a session to a logged-in account
instead of an anonymous signed token) is the right next step for a
production app — see README "Next steps".
"""
import hashlib
import hmac
import os
import uuid
from typing import Optional

SESSION_SECRET = os.environ.get("SESSION_SECRET", "insecure-dev-secret-change-me")


def _sig(session_id: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), session_id.encode(), hashlib.sha256).hexdigest()[:32]


def mint() -> str:
    """Creates a brand-new signed session token."""
    session_id = uuid.uuid4().hex
    return f"{session_id}.{_sig(session_id)}"


def verify(token: Optional[str]):
    """Returns the session_id if `token` carries a valid signature, else None."""
    if not token or "." not in token:
        return None
    session_id, sig = token.rsplit(".", 1)
    if hmac.compare_digest(sig, _sig(session_id)):
        return session_id
    return None
