from __future__ import annotations

from dataclasses import dataclass, field

import requests


@dataclass
class PublishResult:
    platform: str
    ok: bool
    id: str = ""
    url: str = ""
    error: str = ""
    extra: dict = field(default_factory=dict)


class PublishError(RuntimeError):
    pass


def check(resp: requests.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise PublishError(f"{what} failed ({resp.status_code}): {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        return {}
