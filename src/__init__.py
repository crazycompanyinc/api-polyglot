"""
Polyglot - Main Agent Orchestrator
Takes natural language intent, discovers the API, negotiates auth,
builds the request, executes it, and returns structured results.
"""

import os
import json
import re
from typing import Optional
from .core import (
    Intent, APIProfile, APIResponse,
    save_profile, find_profile_by_url, find_profile_by_name, list_profiles,
    store_credential, get_credential,
)
from .discovery import discover_from_url, discover_from_name, list_known_apis, KNOWN_APIS
from .auth import negotiate_auth, apply_auth
from .execute import execute, get_json, paginate


class Polyglot:
    """Main agent: discover -> auth -> execute -> return."""

    def __init__(self, service_hint: str = None):
        self.service_hint = service_hint
        self._last_profile = None
        self._last_response = None

    # ── High-level API ──────────────────────────────────────────────────────

    def ask(self, intent_text: str, **kwargs) -> APIResponse:
        """
        Primary entry point. Parse intent, discover API, negotiate auth, execute.
        """
        intent = Intent(intent_text)

        # 1. Discover the API
        profile = self._discover(intent_text, intent)
        if profile is None:
            return APIResponse(
                status_code=0, data=None,
                error=f"Could not discover API from: '{intent_text}'. "
                      f"Try being more specific or provide a URL."
            )
        self._last_profile = profile

        # 2. Build request from intent + profile
        request = self._build_request(intent, profile, **kwargs)
        if request is None:
            return APIResponse(
                status_code=0, data=None,
                error=f"Could not build request for intent: '{intent_text}'. "
                      f"Available endpoints: {[e['path'] for e in profile.endpoints[:5]]}"
            )

        # 3. Negotiate auth
        svc_name = profile.name.lower().replace(" ", "_")
        auth_result = negotiate_auth(profile, svc_name)

        if not auth_result.success:
            return APIResponse(
                status_code=401, data=None,
                error=auth_result.error,
            )

        request.headers, request.params = apply_auth(
            request.headers, request.params, auth_result
        )

        # 4. Execute
        resp = execute(
            method=request.method,
            url=request.url,
            headers=request.headers,
            params=request.params,
            body=request.body,
            cache_ttl=kwargs.get("cache_ttl", 0),
        )

        # Save/update profile usage
        profile.last_used = __import__("time").time()
        profile.use_count += 1
        if resp.error:
            profile.success_rate = max(0, profile.success_rate - 0.05)
        else:
            profile.success_rate = min(1.0, profile.success_rate + 0.01)
        save_profile(profile)

        self._last_response = resp
        return resp

    def call(self, method: str, url: str, **kwargs) -> APIResponse:
        """Direct API call (bypass intent parsing)."""
        headers = kwargs.get("headers", {})
        params = kwargs.get("params", {})
        body = kwargs.get("body")

        # Try to find existing auth for this URL
        profile = find_profile_by_url(url.split("?")[0])
        if profile:
            svc_name = profile.name.lower().replace(" ", "_")
            auth_result = negotiate_auth(profile, svc_name)
            if auth_result.success:
                headers, params = apply_auth(headers, params, auth_result)

        return execute(method, url, headers=headers, params=params, body=body,
                        timeout=kwargs.get("timeout", 30),
                        cache_ttl=kwargs.get("cache_ttl", 0))

    def get(self, url: str, **kwargs) -> APIResponse:
        return self.call("GET", url, **kwargs)

    def post(self, url: str, body: dict, **kwargs) -> APIResponse:
        return self.call("POST", url, body=body, **kwargs)

    # ── Discovery methods ────────────────────────────────────────────────────

    def discover(self, text: str) -> Optional[APIProfile]:
        """Discover an API from text/URL."""
        profile = self._discover(text, Intent(text))
        if profile:
            self._last_profile = profile
        return profile

    def list_apis(self) -> list:
        """List all known APIs."""
        known = list_known_apis()
        learned = list_profiles()
        return {
            "known": known,
            "learned": [{"name": p.name, "base_url": p.base_url, "auth_type": p.auth_type,
                         "endpoints": len(p.endpoints), "uses": p.use_count} for p in learned],
        }

    # ── Credential management ────────────────────────────────────────────────

    def set_credential(self, service: str, value: str, cred_type: str = "bearer", **meta):
        """Store a credential for a service."""
        store_credential(service, cred_type, value, meta)

    def get_credential_info(self, service: str) -> Optional[dict]:
        """Get stored credential (value masked)."""
        cred = get_credential(service)
        if cred:
            val = cred.get("value", "")
            cred["value"] = val[:4] + "..." + val[-4:] if len(val) > 8 else "****"
        return cred

    # ── Internal ─────────────────────────────────────────────────────────────

    def _discover(self, text: str, intent: Intent) -> Optional[APIProfile]:
        """Discover an API from free text."""
        # Check if URL is in the text
        url_match = re.search(r'https?://[^\s]+', text)
        if url_match:
            url = url_match.group(0)
            # Check if already learned
            profile = find_profile_by_url(url.split("?")[0])
            if profile:
                return profile
            profile = discover_from_url(url)
            if profile:
                save_profile(profile)
                return profile

        # Try by service name
        if self.service_hint:
            profile = discover_from_name(self.service_hint)
            if profile:
                save_profile(profile)
                return profile

        # Try to match text against known APIs
        text_lower = text.lower()
        for domain, info in KNOWN_APIS.items():
            name_words = info["name"].lower().split()
            if any(w in text_lower for w in name_words if len(w) > 2):
                profile = discover_from_name(info["name"])
                if profile:
                    save_profile(profile)
                    return profile

        # Try all known APIs by keyword matching
        return None

    def _build_request(self, intent: Intent, profile: APIProfile, **kwargs) -> Optional:
        """Build an APIRequest from intent and profile."""
        from .core import APIRequest

        # Override from kwargs
        if "url" in kwargs and "method" in kwargs:
            return APIRequest(
                method=kwargs["method"],
                url=kwargs["url"],
                headers=kwargs.get("headers", {}),
                params=kwargs.get("params", {}),
                body=kwargs.get("body"),
            )

        # Match intent to endpoint
        if not profile.endpoints:
            # No known endpoints, try base URL
            return APIRequest(method="GET", url=profile.base_url)

        # Simple matching based on intent action
        best_endpoint = None
        text_lower = intent.raw.lower()

        for ep in profile.endpoints:
            ep_desc = ep.get("desc", "").lower()
            ep_path = ep.get("path", "").lower()
            method = ep.get("method", "GET")

            # Match GET/list/search with list endpoints
            if intent.action in ("list", "get", "search"):
                if method == "GET" and any(w in ep_desc + ep_path for w in ["list", "search", "get", "query"]):
                    if best_endpoint is None or ep_desc > (best_endpoint.get("desc", "") or ""):
                        best_endpoint = ep

        # Fallback: first GET endpoint
        if best_endpoint is None:
            for ep in profile.endpoints:
                if ep.get("method") == "GET":
                    best_endpoint = ep
                    break

        # Fallback: any endpoint
        if best_endpoint is None:
            best_endpoint = profile.endpoints[0]

        # Build URL
        path = best_endpoint["path"]

        # Replace path params from kwargs or intent
        for key, value in kwargs.items():
            if key.startswith("{") or key.startswith("_"):
                continue
            placeholder = "{" + key + "}"
            if placeholder in path:
                path = path.replace(placeholder, str(value))

        # Common replacements for known APIs
        path = self._resolve_path_params(path, profile, **kwargs)

        url = profile.base_url.rstrip("/") + "/" + path.lstrip("/")

        # Collect query params
        params = {}
        if "query" in kwargs:
            if isinstance(kwargs["query"], dict):
                params.update(kwargs["query"])
            elif isinstance(kwargs["query"], str):
                # Parse "key=val&key2=val2"
                from urllib.parse import parse_qs
                for k, v in parse_qs(kwargs["query"]).items():
                    params[k] = v[0]

        # Add filters from intent
        params.update(kwargs.get("params", {}))

        return APIRequest(
            method=best_endpoint.get("method", "GET"),
            url=url,
            headers=kwargs.get("headers", {}),
            params=params,
            body=kwargs.get("body"),
        )

    def _resolve_path_params(self, path: str, profile: APIProfile, **kwargs) -> str:
        """Resolve path parameters with common defaults."""
        import re
        params_in_path = re.findall(r'\{(\w+)\}', path)

        if not params_in_path:
            return path

        replacements = {}

        # Known defaults per service
        defaults = {
            "github.com": {
                "owner": os.environ.get("GITHUB_OWNER", ""),
                "repo": os.environ.get("GITHUB_REPO", ""),
            },
        }

        service_defaults = {}
        for domain, defs in defaults.items():
            if domain in profile.base_url:
                service_defaults = defs
                break

        for p in params_in_path:
            if p in kwargs:
                replacements[p] = kwargs[p]
            elif p in service_defaults and service_defaults[p]:
                replacements[p] = service_defaults[p]

        for key, value in replacements.items():
            path = path.replace("{" + key + "}", str(value))

        # If still has unresolved params, return as-is (caller handles)
        return path

    # ── Convenience ──────────────────────────────────────────────────────────

    def last_profile(self) -> Optional[APIProfile]:
        return self._last_profile

    def last_response(self) -> Optional[APIResponse]:
        return self._last_response


# ── Module-level shortcut ──────────────────────────────────────────────────────

_default = None

def ask(text: str, **kwargs) -> APIResponse:
    """Global shortcut: polyglot.ask('...')"""
    global _default
    if _default is None:
        _default = Polyglot()
    return _default.ask(text, **kwargs)

def call(method: str, url: str, **kwargs) -> APIResponse:
    """Global shortcut: polyglot.call('GET', url)"""
    global _default
    if _default is None:
        _default = Polyglot()
    return _default.call(method, url, **kwargs)

def get(url: str, **kwargs) -> APIResponse:
    """Global shortcut: polyglot.get(url)"""
    global _default
    if _default is None:
        _default = Polyglot()
    return _default.get(url, **kwargs)

def post(url: str, body: dict, **kwargs) -> APIResponse:
    """Global shortcut: polyglot.post(url, {...})"""
    global _default
    if _default is None:
        _default = Polyglot()
    return _default.post(url, body, **kwargs)
