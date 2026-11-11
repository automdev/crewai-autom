"""Offline tests for crewai-autom (httpx.MockTransport)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from crewai_autom import AutomSearchTool
from crewai_autom import tool as tool_module

API_KEY = "test-autom-key-placeholder"  # pragma: allowlist secret
ENV = "AUTOM_API_KEY"
ROWS = [
    {"position": 1, "title": "CrewAI", "link": "https://www.crewai.com/", "snippet": "Multi-agent framework."},
    "not an object",
    {
        "position": 2,
        "title": "News",
        "link": "https://news.example.com/",
        "snippet": "s",
        "date": "1 day ago",
        "source": "Example",
    },
]

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], list[httpx.Request]]:
    def install(handler: Handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        transport = httpx.MockTransport(record)

        def fake_get(url, **kwargs):
            kwargs.pop("timeout", None)
            with httpx.Client(transport=transport) as client:
                return client.get(url, **kwargs)

        monkeypatch.setattr(tool_module.httpx, "get", fake_get)
        return seen

    return install


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, f"{API_KEY}\n")


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"organic_results": ROWS})


def test_search(mock_http) -> None:
    seen = mock_http(ok)
    out = json.loads(AutomSearchTool(country="US", language="en", location="Paris").run(search_query=" crewai "))

    assert seen[0].url.path == "/v1/google/search"
    assert dict(seen[0].url.params) == {"query": "crewai", "gl": "us", "hl": "en", "location": "Paris"}
    assert seen[0].headers["x-api-key"] == API_KEY
    assert out[0] == {
        "title": "CrewAI",
        "link": "https://www.crewai.com/",
        "snippet": "Multi-agent framework.",
        "position": 1,
    }
    assert out[1]["date"] == "1 day ago" and out[1]["source"] == "Example"


def test_news_uses_google_news(mock_http) -> None:
    seen = mock_http(ok)
    AutomSearchTool(search_type="news", engine="bing", location="Paris").run(search_query="q")
    assert seen[0].url.path == "/v1/google/news"
    assert "location" not in seen[0].url.params


@pytest.mark.parametrize("engine", ["bing", "brave", "duckduckgo", "yahoo"])
def test_other_engines(mock_http, engine: str) -> None:
    seen = mock_http(ok)
    AutomSearchTool(engine=engine, country="us").run(search_query="q")
    assert seen[0].url.path == f"/v1/{engine}/search"
    assert dict(seen[0].url.params) == {"query": "q"}


def test_n_results(mock_http) -> None:
    mock_http(ok)
    assert len(json.loads(AutomSearchTool(n_results=1).run(search_query="q"))) == 1


def test_api_key_argument_wins(mock_http) -> None:
    seen = mock_http(ok)
    AutomSearchTool(api_key="other-key").run(search_query="q")
    assert seen[0].headers["x-api-key"] == "other-key"


def test_missing_key(mock_http, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV)
    seen = mock_http(ok)
    assert "AUTOM_API_KEY is not set" in AutomSearchTool().run(search_query="q")
    assert seen == []


def test_empty_query(mock_http) -> None:
    assert AutomSearchTool().run(search_query="  ") == "The search query is empty."


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            httpx.Response(401, json={"error": "Invalid API key"}),
            "Autom rejected the API key (HTTP 401): Invalid API key",
        ),
        (httpx.Response(401, json={"error": "Rate limit exceeded"}), "Autom rate limit exceeded (HTTP 401)"),
        (httpx.Response(500, json={"message": f"boom {API_KEY}"}), "Autom API error (HTTP 500): boom ***"),
        (httpx.Response(200, text="<html>"), "not JSON"),
        (httpx.Response(200, json=["x"]), "unexpected response shape"),
    ],
)
def test_errors_are_returned_as_text(mock_http, response, expected) -> None:
    mock_http(lambda request: response)
    assert expected in AutomSearchTool().run(search_query="q")


def test_env_vars_declared() -> None:
    assert [var.name for var in AutomSearchTool().env_vars] == ["AUTOM_API_KEY"]
