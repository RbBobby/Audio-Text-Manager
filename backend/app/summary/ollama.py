from __future__ import annotations

from typing import Any

import httpx


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    """Minimal synchronous client for Ollama's /api/chat."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:14b-instruct-q4_K_M",
        timeout_sec: float = 900.0,
        default_options: dict[str, Any] | None = None,
        trust_env: bool = True,
    ) -> None:
        self._model = model
        self._default_options: dict[str, Any] = {"temperature": 0.2}
        if default_options:
            self._default_options.update(default_options)
        timeout = httpx.Timeout(timeout_sec, connect=15.0)
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            trust_env=trust_env,
        )

    @property
    def model(self) -> str:
        return self._model

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def health(self) -> bool:
        try:
            r = self._client.get("/api/tags")
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        last: Exception | None = None
        for attempt in range(2):
            try:
                return self._chat_once(messages, options=options)
            except (httpx.HTTPError, OllamaError) as e:
                if attempt == 0:
                    continue
                raise e

    def _chat_once(
        self,
        messages: list[dict[str, str]],
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        opts = dict(self._default_options)
        if options:
            opts.update(options)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": opts,
        }
        try:
            r = self._client.post("/api/chat", json=payload)
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama request failed: {e}") from e
        if r.status_code >= 400:
            raise OllamaError(f"Ollama HTTP {r.status_code}: {r.text[:2000]}")
        data = r.json()
        msg = data.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str):
            raise OllamaError(f"Unexpected Ollama response: {str(data)[:2000]}")
        return content
