"""LLM service for generating answers from retrieved document chunks.

Supports multiple providers: Gemini, OpenAI, and Anthropic.
Primary provider is selected via LLM_PROVIDER; an optional fallback provider
is selected via LLM_FALLBACK_PROVIDER (used when the primary call fails).
"""

import os
from typing import Any

import httpx


class LLMError(Exception):
    """Raised when an LLM provider call fails."""


class LLMService:
    """Multi-provider LLM client with optional fallback for question-answering."""

    def __init__(self) -> None:
        self.primary_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        self.primary_api_key = os.getenv("LLM_API_KEY", "").strip()
        self.primary_model = os.getenv("LLM_MODEL", "").strip()

        self.fallback_provider = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
        self.fallback_api_key = os.getenv("LLM_FALLBACK_API_KEY", "").strip()
        self.fallback_model = os.getenv("LLM_FALLBACK_MODEL", "").strip()

        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_prompt(self, question: str, chunks: list[dict[str, Any]]) -> str:
        context_parts = []
        for i, chunk in enumerate(chunks, start=1):
            filename = chunk.get("filename", "unknown")
            text = chunk.get("text", "")
            context_parts.append(f"[Source {i}] {filename}:\n{text}")
        context = "\n\n".join(context_parts)

        return (
            "You are a helpful assistant that answers questions based on provided document context. "
            "Use only the information from the sources below to answer the question. "
            "If the answer cannot be determined from the sources, say so. "
            "Cite sources using [Source N] notation where N is the source number.\n\n"
            f"Sources:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

    async def generate_answer(self, question: str, chunks: list[dict[str, Any]]) -> str:
        """Generate an answer, trying the primary provider then the fallback."""
        if not chunks:
            return "No relevant document content found to answer the question."

        prompt = self._build_prompt(question, chunks)

        providers = []
        if self.primary_provider:
            providers.append(
                (self.primary_provider, self.primary_api_key, self.primary_model, "primary")
            )
        if self.fallback_provider:
            providers.append(
                (self.fallback_provider, self.fallback_api_key, self.fallback_model, "fallback")
            )

        last_error: LLMError | None = None
        for provider, api_key, model, label in providers:
            try:
                return await self._call_provider(provider, api_key, model, prompt)
            except LLMError as exc:
                last_error = exc
                if label == "fallback":
                    break

        if last_error:
            raise last_error
        raise LLMError("No LLM provider is configured")

    async def _call_provider(
        self, provider: str, api_key: str, model: str, prompt: str
    ) -> str:
        if not provider:
            raise LLMError("LLM provider is not set")
        if not api_key:
            raise LLMError("LLM API key is not set")
        if not model:
            raise LLMError("LLM model is not set")

        if provider == "gemini":
            return await self._gemini_answer(api_key, model, prompt)
        if provider == "openai":
            return await self._openai_answer(api_key, model, prompt)
        if provider == "anthropic":
            return await self._anthropic_answer(api_key, model, prompt)

        raise LLMError(f"Unsupported LLM provider: {provider}")

    async def _gemini_answer(self, api_key: str, model: str, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
        }
        response = await self.client.post(url, headers=headers, params=params, json=payload)
        if response.status_code != 200:
            raise LLMError(f"Gemini API error ({response.status_code}): {response.text}")
        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Gemini response format: {data}") from exc

    async def _openai_answer(self, api_key: str, model: str, prompt: str) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1000,
        }
        response = await self.client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise LLMError(f"OpenAI API error ({response.status_code}): {response.text}")
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected OpenAI response format: {data}") from exc

    async def _anthropic_answer(self, api_key: str, model: str, prompt: str) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1000,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = await self.client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise LLMError(f"Anthropic API error ({response.status_code}): {response.text}")
        data = response.json()
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected Anthropic response format: {data}") from exc
