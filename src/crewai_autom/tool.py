"""CrewAI tools for Autom, a SERP API for live search engine results (https://www.autom.dev)."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

import httpx
from crewai.tools import BaseTool, EnvVar
from pydantic import BaseModel, Field

__all__ = ["AutomSearchTool", "AutomSearchToolSchema"]

BRAND = "Autom"
ENV = "AUTOM_API_KEY"
APP_URL = "https://app.autom.dev"
BASE_URL = "https://api.autom.dev"
USER_AGENT = "crewai-autom"


def _redact(text: str, api_key: str) -> str:
    return text.replace(api_key, "***") if api_key else text


def _error_message(response: httpx.Response, api_key: str) -> str:
    detail = ""
    try:
        body = response.json()
    except ValueError:
        detail = response.text.strip()
    else:
        if isinstance(body, dict):
            error = body.get("error") or body.get("message") or ""
            if isinstance(error, dict):
                error = error.get("message") or ""
            detail = str(error)
    detail = _redact(detail, api_key)[:300]
    status = response.status_code
    if status == 401 and "rate limit" in detail.lower():
        label = f"{BRAND} rate limit exceeded"
    elif status == 401:
        label = f"{BRAND} rejected the API key"
    elif status == 402:
        label = f"{BRAND} account is out of credits"
    elif status == 429:
        label = f"{BRAND} rate limit exceeded"
    else:
        label = f"{BRAND} API error"
    return f"{label} (HTTP {status})" + (f": {detail}" if detail else "")


def _get(path: str, params: dict[str, Any], api_key: str, timeout: float) -> httpx.Response | str:
    """GET ``path`` and return the response, or an error message for the agent."""
    if not api_key:
        return f"{ENV} is not set. Get a key at {APP_URL}"
    headers = {"x-api-key": api_key, "Accept": "application/json", "User-Agent": USER_AGENT}
    try:
        response = httpx.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        return f"{BRAND} did not answer within {timeout:g} seconds."
    except httpx.HTTPError as exc:
        return f"Could not reach {BRAND}: {_redact(str(exc), api_key)}"
    if not response.is_success:
        return _error_message(response, api_key)
    return response


def _organic(response: httpx.Response, limit: int) -> list[dict[str, Any]] | str:
    try:
        body = response.json()
    except ValueError:
        return f"{BRAND} returned a response that is not JSON."
    rows = body.get("organic_results") if isinstance(body, dict) else None
    if isinstance(body, dict) and rows is None:
        rows = []
    if not isinstance(rows, list):
        return f"{BRAND} returned an unexpected response shape."
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result = {"title": row.get("title") or "", "link": row.get("link") or "", "snippet": row.get("snippet") or ""}
        for key in ("position", "date", "source"):
            if row.get(key) not in (None, ""):
                result[key] = row[key]
        results.append(result)
        if len(results) >= limit:
            break
    return results


class AutomSearchToolSchema(BaseModel):
    """Input for AutomSearchTool."""

    search_query: str = Field(..., description="The search query. Search operators such as site: are supported.")


class AutomSearchTool(BaseTool):
    """Search the web with Autom: Google (web or news), Bing, Brave, DuckDuckGo or Yahoo.

    Returns a JSON list of results with ``title``, ``link``, ``snippet`` and ``position``
    (news results also carry ``date`` and ``source``).
    """

    name: str = "Search the internet with Autom"
    description: str = (
        "Search the internet with a search_query and get the top results with title, link and snippet. "
        "Use it for current events and facts you do not know."
    )
    args_schema: type[BaseModel] = AutomSearchToolSchema
    engine: Literal["google", "bing", "brave", "duckduckgo", "yahoo"] = "google"
    search_type: Literal["search", "news"] = "search"
    """``news`` searches Google News (Google only)."""
    n_results: int = Field(default=5, ge=1, le=10)
    country: str | None = None
    """Two-letter country code, such as us (Google only)."""
    language: str | None = None
    """Language code of the results, such as en (Google only)."""
    location: str | None = None
    """City or region to search from (Google web search only)."""
    timeout: float = 60.0
    api_key: str | None = Field(default=None, description="Autom API key. Defaults to AUTOM_API_KEY.")
    env_vars: list[EnvVar] = Field(
        default_factory=lambda: [EnvVar(name="AUTOM_API_KEY", description="API key for Autom", required=True)]
    )

    def _run(self, search_query: str, **kwargs: Any) -> str:
        query = (search_query or "").strip()
        if not query:
            return "The search query is empty."
        engine = self.engine if self.search_type == "search" else "google"
        path = f"/v1/{engine}/{'news' if self.search_type == 'news' else 'search'}"
        params: dict[str, Any] = {"query": query}
        if engine == "google":
            if self.country:
                params["gl"] = self.country.strip().lower()
            if self.language:
                params["hl"] = self.language.strip()
            if self.location and self.search_type == "search":
                params["location"] = self.location.strip()
        api_key = (self.api_key or os.environ.get(ENV) or "").strip()
        response = _get(path, params, api_key, self.timeout)
        if isinstance(response, str):
            return response
        results = _organic(response, self.n_results)
        if isinstance(results, str):
            return results
        return json.dumps(results, ensure_ascii=False)
