"""
API Executor
Handles calling APIs with retries, rate limiting, pagination, and caching.
"""

import json
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Optional
from ..core import APIResponse


# Simple in-memory cache
_cache = {}
_cache_dir = Path.home() / ".api-polyglot" / "cache"
_cache_dir.mkdir(parents=True, exist_ok=True)


def execute(
    method: str,
    url: str,
    headers: dict = None,
    params: dict = None,
    body: any = None,
    timeout: int = 30,
    retries: int = 3,
    cache_ttl: int = 0,
) -> APIResponse:
    """
    Execute an HTTP request with retries, caching, and error handling.
    """
    headers = headers or {}
    params = params or {}

    # Add params to URL
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    # Check cache for GET requests
    if method.upper() == "GET" and cache_ttl > 0:
        cached = _get_cache(url, cache_ttl)
        if cached:
            return APIResponse(**cached, cached=True)

    # Set default headers
    if "Accept" not in headers:
        headers["Accept"] = "application/json"
    if "User-Agent" not in headers:
        headers["User-Agent"] = "API-Polyglot/1.0"

    last_error = None
    for attempt in range(retries):
        try:
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"

            req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
            start = time.time()

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                duration = (time.time() - start) * 1000

                content_type = resp.headers.get("Content-Type", "")
                result_data = raw
                if "json" in content_type:
                    try:
                        result_data = json.loads(raw)
                    except json.JSONDecodeError:
                        result_data = raw

                response = APIResponse(
                    status_code=resp.status,
                    data=result_data,
                    headers=dict(resp.headers),
                    raw_text=raw,
                    duration_ms=duration,
                )

                # Cache successful GET
                if method.upper() == "GET" and cache_ttl > 0:
                    _set_cache(url, response)

                return response

        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.reason}"
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass

            # Don't retry 4xx (client errors)
            if 400 <= e.code < 500 and e.code not in (429,):
                return APIResponse(
                    status_code=e.code,
                    data=None,
                    error=f"{last_error} - {body_text}",
                    duration_ms=0,
                )

            # 429 rate limit - back off
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 2 ** attempt))
                time.sleep(retry_after)
                continue

            if attempt < retries - 1:
                time.sleep(2 ** attempt)

        except Exception as e:
            last_error = str(e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return APIResponse(
        status_code=0,
        data=None,
        error=f"All {retries} attempts failed. Last: {last_error}",
        duration_ms=0,
    )


def get_json(url: str, headers: dict = None, params: dict = None, **kwargs) -> APIResponse:
    """Shortcut for GET JSON requests."""
    return execute("GET", url, headers=headers, params=params, **kwargs)


def post_json(url: str, body: dict, headers: dict = None, params: dict = None, **kwargs) -> APIResponse:
    """Shortcut for POST JSON requests."""
    return execute("POST", url, headers=headers, params=params, body=body, **kwargs)


def paginate(
    url: str,
    headers: dict = None,
    params: dict = None,
    page_param: str = "page",
    per_page_param: str = "per_page",
    per_page: int = 30,
    max_pages: int = 10,
) -> list:
    """Auto-paginate through GET results that return arrays."""
    all_results = []
    params = params or {}

    for page in range(1, max_pages + 1):
        params[page_param] = page
        params[per_page_param] = per_page

        resp = get_json(url, headers=headers, params=params.copy())
        if resp.error:
            break

        if isinstance(resp.data, list):
            if not resp.data:
                break
            all_results.extend(resp.data)
        else:
            all_results.append(resp.data)
            break

    return all_results


# --- Cache helpers ---

def _cache_key(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()


def _get_cache(url: str, ttl: int) -> Optional[dict]:
    key = _cache_key(url)
    path = _cache_dir / f"{key}.json"
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < ttl:
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
    return None


def _set_cache(url: str, response: APIResponse):
    key = _cache_key(url)
    path = _cache_dir / f"{key}.json"
    path.write_text(json.dumps({
        "status_code": response.status_code,
        "data": response.data,
        "headers": response.headers,
        "raw_text": response.raw_text,
        "error": response.error,
        "duration_ms": response.duration_ms,
    }, default=str))


def clear_cache():
    for f in _cache_dir.glob("*.json"):
        f.unlink()
