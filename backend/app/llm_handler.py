"""Talks to Groq's free, OpenAI-compatible chat completions API.

Groq is used instead of a local Ollama model so the whole app can be deployed
to a normal web host with no GPU / local model server required. Get a free
key at https://console.groq.com/keys and set it as GROQ_API_KEY.
"""
import json
import os
from typing import Generator, List, Optional

import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# A short, current list of solid free-tier Groq models. Kept small and
# hand-picked rather than fetched dynamically, since not all models Groq
# lists are suited to this use case.
AVAILABLE_MODELS = [
    {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B — best quality"},
    {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B — fastest"},
    {"id": "gemma2-9b-it", "label": "Gemma2 9B"},
]

DEFAULT_MODEL = "llama-3.3-70b-versatile"


class LLMHandler:
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or DEFAULT_MODEL
        self.api_key = os.environ.get("GROQ_API_KEY", "")

    def generate_answer(self, context: str, question: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set on the server. Add it to your backend "
                "environment variables (see .env.example)."
            )

        system_prompt = (
            "You are a helpful study assistant. Answer the question using ONLY "
            "the provided context from the user's documents. If the context does "
            "not contain the answer, say so clearly instead of guessing. Keep "
            "answers concise and well-structured."
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 1024,
        }

        try:
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Could not reach Groq API: {str(e)}")

        if response.status_code != 200:
            raise RuntimeError(
                f"Groq API returned {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise RuntimeError("Unexpected response shape from Groq API.")

    def generate_answer_stream(self, context: str, question: str) -> Generator[str, None, None]:
        """Yields answer text incrementally as Groq streams it back, so the
        UI can render token-by-token instead of waiting for the full reply."""
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set on the server. Add it to your backend "
                "environment variables (see .env.example)."
            )

        system_prompt = (
            "You are a helpful study assistant. Answer the question using ONLY "
            "the provided context from the user's documents. If the context does "
            "not contain the answer, say so clearly instead of guessing. Keep "
            "answers concise and well-structured."
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 1024,
            "stream": True,
        }

        try:
            response = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
                stream=True,
            )
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Could not reach Groq API: {str(e)}")

        if response.status_code != 200:
            raise RuntimeError(
                f"Groq API returned {response.status_code}: {response.text[:300]}"
            )

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data_str = line[len("data:"):].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta

    @staticmethod
    def get_available_models() -> List[dict]:
        return AVAILABLE_MODELS
