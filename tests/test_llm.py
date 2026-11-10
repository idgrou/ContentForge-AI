import json

import pytest
from pydantic import BaseModel, ConfigDict

from contentforge.llm import LLMError, LocalLLM, parse_json_loose


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str


class FakeResp:
    def __init__(self, content, status=200):
        self.status_code, self._content, self.text = status, content, str(content)

    def json(self):
        return {"message": {"content": self._content}}


class FakeSession:
    def __init__(self, replies):
        self.replies, self.bodies = list(replies), []

    def post(self, url, json=None, timeout=None):
        self.bodies.append(json)
        return self.replies.pop(0)


def test_parse_json_loose_handles_fences_and_chatter():
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Sure! {"a": 2} hope it helps') == {"a": 2}


def test_generate_sends_schema_and_retries_on_bad_json():
    s = FakeSession([FakeResp("oops"), FakeResp(json.dumps({"title": "כותרת"}))])
    llm = LocalLLM(model="m", session=s)
    assert llm.generate("sys", "p", Out).title == "כותרת"
    assert s.bodies[0]["format"]["properties"]["title"]["type"] == "string"
    assert s.bodies[0]["stream"] is False and s.bodies[0]["model"] == "m"
    assert len(s.bodies[1]["messages"]) == 4


def test_missing_model_gives_clear_error():
    with pytest.raises(LLMError, match="ollama pull"):
        LocalLLM(model="nope", session=FakeSession([FakeResp("", 404)])).complete("x")
