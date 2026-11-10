"""Thin wrapper over the Anthropic SDK that returns validated Pydantic objects."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


class ClaudeWriter:
    """Calls Claude with a JSON schema so every answer parses into a Pydantic model.

    Server-side refusal fallbacks are on (``fallbacks="default"``): if the model declines,
    the API retries on a fallback model inside the same call.
    """

    def __init__(self, model: str = "claude-opus-5-5", client: Any | None = None, effort: str = "medium"):
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()

    def generate(self, system: str, prompt: str, output: type[T], max_tokens: int = 16000) -> T:
        schema = output.model_json_schema()
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=system,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMError(f"Claude declined the request: {getattr(details, 'explanation', '')}")
        if response.stop_reason == "max_tokens":
            raise LLMError("Answer was cut off at max_tokens; raise max_tokens or shorten the input")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Claude returned no text block")
        try:
            return output.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError(f"Could not parse Claude's JSON answer: {exc}") from exc
