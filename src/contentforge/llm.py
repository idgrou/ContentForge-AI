"""Local LLM client (Ollama). No paid API and no API key: the model runs on your machine.

Install Ollama from https://ollama.com, then pull a model, for example:

    ollama pull gemma3:12b      # good multilingual quality, Hebrew included
    ollama pull qwen3:8b        # lighter alternative

Structured answers use Ollama's JSON-schema ``format`` so they parse into Pydantic models.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def parse_json_loose(raw: str) -> Any:
    """Parse JSON even when a model wraps it in ``` fences or adds text around it."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise


class LocalLLM:
    def __init__(
        self,
        model: str = "gemma3:12b",
        host: str = "http://localhost:11434",
        num_ctx: int = 16384,
        temperature: float = 0.4,
        timeout: float = 900,
        session: requests.Session | None = None,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.timeout = timeout
        self.session = session or requests.Session()

    def _chat(self, messages: list[dict], fmt: Any = None) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"num_ctx": self.num_ctx, "temperature": self.temperature},
        }
        if fmt is not None:
            body["format"] = fmt
        try:
            resp = self.session.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
        except requests.ConnectionError as exc:
            raise LLMError(f"Ollama is not reachable at {self.host}. Start it with `ollama serve`.") from exc
        if resp.status_code == 404:
            raise LLMError(f"Model {self.model!r} not found. Run `ollama pull {self.model}`.")
        if resp.status_code != 200:
            raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:500]}")
        return resp.json()["message"]["content"]

    def complete(self, prompt: str, json_mode: bool = True) -> str:
        """Plain prompt -> text. Used by the highlight finder (``llm_fn`` signature)."""
        return self._chat([{"role": "user", "content": prompt}], fmt="json" if json_mode else None)

    def generate(self, system: str, prompt: str, output: type[T], attempts: int = 3) -> T:
        """Prompt -> validated Pydantic object. Retries when the model returns invalid JSON."""
        schema = output.model_json_schema()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt + "\n\nAnswer with JSON that matches the schema."},
        ]
        last = ""
        for _ in range(attempts):
            raw = self._chat(messages, fmt=schema)
            try:
                return output.model_validate(parse_json_loose(raw))
            except (json.JSONDecodeError, ValidationError) as exc:
                last = str(exc)
                messages = messages[:2] + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That JSON was invalid ({last[:300]}). Return only corrected JSON."},
                ]
        raise LLMError(f"Model did not return valid JSON after {attempts} attempts: {last[:300]}")
