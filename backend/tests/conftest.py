from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.clients.claude import ClaudeClient
from app.clients.jobdiva.client import JobDivaClient
from app.clients.jobdiva.mock import MockJobDivaTransport
from app.core.config import Settings
from app.models.pipeline import Deps
from app.services.jobs import JobsService


def make_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        _env_file=None,
        anthropic_api_key=None,
        jobdiva_mock=True,
        llm_mode="stub",
        jobdiva_min_interval_s=0.0,
        jobdiva_backoff_base_s=0.0,
        snapshot_path=tmp_path / "search_snapshot.json",
        search_deadline_s=60.0,
    )
    base.update(overrides)
    return Settings(**base)


async def no_sleep(_: float) -> None:
    return None


def make_client(settings: Settings, transport: MockJobDivaTransport | None = None) -> JobDivaClient:
    client = JobDivaClient(settings, transport=transport or MockJobDivaTransport())
    client.sleep = no_sleep
    return client


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
async def jobdiva(settings: Settings):
    client = make_client(settings)
    yield client
    await client.aclose()


@pytest.fixture(autouse=True)
def offline_geo(monkeypatch):
    """Tests never download GeoNames data: distances are unknown unless a test sets them."""

    async def unknown(origin, zips):
        return {k: None for k in zips}

    monkeypatch.setattr("app.services.prescore.distances_miles", unknown)


def make_deps(settings: Settings, jobdiva: JobDivaClient, claude: ClaudeClient | None = None) -> Deps:
    return Deps(
        settings=settings, jobdiva=jobdiva, claude=claude or ClaudeClient(settings), jobs=JobsService(jobdiva, settings)
    )


class FakeMessages:
    """Stands in for `client.beta.messages`; `responder(kwargs) -> (stop_reason, text)`."""

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        stop, text = self.responder(kwargs)
        return SimpleNamespace(
            model=kwargs["model"],
            stop_reason=stop,
            content=[SimpleNamespace(type="text", text=text)] if text is not None else [],
            usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 1, "output_tokens": 1}),
        )


def fake_claude(settings: Settings, responder) -> tuple[ClaudeClient, FakeMessages]:
    messages = FakeMessages(responder)
    sdk = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeClient(settings, client=sdk), messages


def handles_in(kwargs: dict) -> dict[str, list[tuple[str, str]]]:
    """Parse candidate handles and their (evidence id, text) pairs from a request's content."""
    text = "\n".join(block["text"] for block in kwargs["messages"][0]["content"])
    out: dict[str, list[tuple[str, str]]] = {}
    for handle, body in re.findall(r'<candidate handle="(c\d+)">(.*?)</candidate>', text, re.S):
        out[handle] = re.findall(r'<evidence id="([^"]+)" source="[^"]+"[^>]*>(.*?)</evidence>', body, re.S)
    return out


def requirement_ids(kwargs: dict) -> list[str]:
    text = "\n".join(block["text"] for block in kwargs["messages"][0]["content"])
    return re.findall(r'<requirement id="([^"]+)"', text)


def dumps(obj) -> str:
    return json.dumps(obj)
