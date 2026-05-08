"""
API Discovery Engine
Finds and learns API endpoints from URLs, docs, OpenAPI specs, or probing.
"""

import re
import json
import urllib.request
import urllib.error
from typing import Optional
from ..core import APIProfile


# Known API patterns for common services
KNOWN_APIS = {
    "github.com": {
        "name": "GitHub",
        "base_url": "https://api.github.com",
        "description": "GitHub REST API v3",
        "auth_type": "bearer",
        "auth_help": "Needs a Personal Access Token (classic) with appropriate scopes. Create one at https://github.com/settings/tokens",
        "auth_env": "GITHUB_TOKEN",
        "endpoints": [
            {"method": "GET", "path": "/repos/{owner}/{repo}/issues", "desc": "List issues"},
            {"method": "GET", "path": "/repos/{owner}/{repo}/pulls", "desc": "List pull requests"},
            {"method": "GET", "path": "/user/repos", "desc": "List user repos"},
            {"method": "POST", "path": "/repos/{owner}/{repo}/issues", "desc": "Create issue"},
            {"method": "GET", "path": "/search/issues", "desc": "Search issues"},
        ],
    },
    "api.openweathermap.org": {
        "name": "OpenWeatherMap",
        "base_url": "https://api.openweathermap.org/data/2.5",
        "description": "Weather data API",
        "auth_type": "api_key",
        "auth_help": "Needs an API key from https://openweathermap.org/api",
        "auth_env": "OPENWEATHER_API_KEY",
        "endpoints": [
            {"method": "GET", "path": "/weather", "desc": "Current weather"},
            {"method": "GET", "path": "/forecast", "desc": "5-day forecast"},
        ],
    },
    "earthquake.usgs.gov": {
        "name": "USGS Earthquakes",
        "base_url": "https://earthquake.usgs.gov/fdsnws/event/1",
        "description": "USGS Earthquake Hazards Program API",
        "auth_type": "none",
        "auth_help": None,
        "auth_env": None,
        "endpoints": [
            {"method": "GET", "path": "/query", "desc": "Query earthquakes (format=geojson&minmagnitude=X&...)"},
        ],
    },
    "api.coingecko.com": {
        "name": "CoinGecko",
        "base_url": "https://api.coingecko.com/api/v3",
        "description": "Cryptocurrency data API (free, no key)",
        "auth_type": "none",
        "auth_help": None,
        "auth_env": None,
        "endpoints": [
            {"method": "GET", "path": "/ping", "desc": "Check API status"},
            {"method": "GET", "path": "/simple/price", "desc": "Get coin prices"},
            {"method": "GET", "path": "/coins/markets", "desc": "Market data"},
            {"method": "GET", "path": "/coins/{id}", "desc": "Coin details"},
        ],
    },
    "news.ycombinator.com": {
        "name": "HackerNews",
        "base_url": "https://hacker-news.firebaseio.com/v0",
        "description": "HackerNews Firebase API",
        "auth_type": "none",
        "auth_help": None,
        "auth_env": None,
        "endpoints": [
            {"method": "GET", "path": "/topstories.json", "desc": "Top story IDs"},
            {"method": "GET", "path": "/newstories.json", "desc": "New story IDs"},
            {"method": "GET", "path": "/item/{id}.json", "desc": "Get story/comment by ID"},
        ],
    },
    "api.openai.com": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "description": "OpenAI API",
        "auth_type": "bearer",
        "auth_help": "Needs an API key from https://platform.openai.com/api-keys",
        "auth_env": "OPENAI_API_KEY",
        "endpoints": [
            {"method": "GET", "path": "/models", "desc": "List models"},
            {"method": "POST", "path": "/chat/completions", "desc": "Chat completions"},
        ],
    },
    "jsonplaceholder.typicode.com": {
        "name": "JSONPlaceholder",
        "base_url": "https://jsonplaceholder.typicode.com",
        "description": "Free fake REST API for testing",
        "auth_type": "none",
        "auth_help": None,
        "auth_env": None,
        "endpoints": [
            {"method": "GET", "path": "/posts", "desc": "List posts"},
            {"method": "GET", "path": "/users", "desc": "List users"},
            {"method": "GET", "path": "/todos", "desc": "List todos"},
            {"method": "GET", "path": "/comments", "desc": "List comments"},
        ],
    },
}


def discover_from_url(url: str) -> Optional[APIProfile]:
    """Try to discover an API from a URL."""
    # Check known APIs first
    for domain, info in KNOWN_APIS.items():
        if domain in url:
            return APIProfile(
                name=info["name"],
                base_url=info["base_url"],
                description=info["description"],
                auth_type=info["auth_type"],
                endpoints=info["endpoints"],
                auth_config={
                    "help": info.get("auth_help"),
                    "env_var": info.get("auth_env"),
                },
            )

    # Try to probe common API patterns
    base = _extract_base_url(url)
    return _probe_api(base)


def discover_from_name(name: str) -> Optional[APIProfile]:
    """Try to find a known API by name/name."""
    name_lower = name.lower()
    for domain, info in KNOWN_APIS.items():
        if name_lower in info["name"].lower() or name_lower in domain.lower():
            return APIProfile(
                name=info["name"],
                base_url=info["base_url"],
                description=info["description"],
                auth_type=info["auth_type"],
                endpoints=info["endpoints"],
                auth_config={
                    "help": info.get("auth_help"),
                    "env_var": info.get("auth_env"),
                },
            )
    return None


def _extract_base_url(url: str) -> str:
    """Extract base URL (scheme + host) from a full URL."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _probe_api(base_url: str) -> Optional[APIProfile]:
    """Probe a base URL for common API patterns."""
    # Try OpenAPI/Swagger
    for spec_path in ["/openapi.json", "/swagger.json", "/api-docs", "/v3/api-docs"]:
        try:
            req = urllib.request.Request(f"{base_url}{spec_path}", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                spec = json.loads(resp.read())
                return _parse_openapi_spec(spec, base_url)
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            continue

    # Try root path
    try:
        req = urllib.request.Request(base_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()  # Just check it responds
            return APIProfile(
                name=base_url.split("//")[1].split("/")[0],
                base_url=base_url,
                description=f"Discovered API at {base_url}",
                auth_type="unknown",
                endpoints=[],
            )
    except (urllib.error.URLError, OSError):
        pass

    return None


def _parse_openapi_spec(spec: dict, base_url: str) -> APIProfile:
    """Parse an OpenAPI/Swagger spec into an APIProfile."""
    info = spec.get("info", {})
    title = info.get("title", "Unknown API")
    description = info.get("description", "")

    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "desc": details.get("summary", details.get("description", ""))[:100],
                })

    return APIProfile(
        name=title,
        base_url=base_url,
        description=description[:500],
        auth_type="unknown",
        endpoints=endpoints[:50],  # Limit
    )


def list_known_apis() -> list[dict]:
    """List all known/built-in APIs."""
    result = []
    for domain, info in KNOWN_APIS.items():
        result.append({
            "domain": domain,
            "name": info["name"],
            "base_url": info["base_url"],
            "auth_type": info["auth_type"],
            "auth_required": info["auth_type"] != "none",
            "endpoints_count": len(info["endpoints"]),
        })
    return result
