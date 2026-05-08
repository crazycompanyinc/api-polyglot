"""
Auth Negotiator
Handles authentication discovery, prompting, and credential management.
"""

import os
import base64
from typing import Optional
from ..core import APIProfile, get_credential, has_credential, store_credential


class AuthResult:
    def __init__(self, success: bool, headers: dict = None, params: dict = None, error: str = None):
        self.success = success
        self.headers = headers or {}
        self.params = params or {}
        self.error = error

    def __repr__(self):
        if self.success:
            return f"AuthResult(success=True, keys={list(self.headers.keys()) + list(self.params.keys())})"
        return f"AuthResult(success=False, error={self.error})"


def negotiate_auth(profile: APIProfile, service_name: str = None) -> AuthResult:
    """
    Negotiate authentication for an API profile.
    Checks existing credentials, env vars, and prompts if needed.
    """
    svc = service_name or profile.name.lower().replace(" ", "_")

    if profile.auth_type == "none":
        return AuthResult(success=True)

    if profile.auth_type == "bearer":
        return _negotiate_bearer(svc, profile)

    if profile.auth_type == "api_key":
        return _negotiate_api_key(svc, profile)

    if profile.auth_type == "basic":
        return _negotiate_basic(svc, profile)

    if profile.auth_type == "oauth2":
        return _negotiate_oauth2(svc, profile)

    return AuthResult(success=True)  # Unknown auth, try without


def _negotiate_bearer(service_name: str, profile: APIProfile) -> AuthResult:
    """Negotiate Bearer token auth (JWT, PAT, etc.)."""
    # 1. Check stored credentials
    cred = get_credential(service_name)
    if cred and cred.get("type") == "bearer":
        return AuthResult(success=True, headers={"Authorization": f"Bearer {cred['value']}"})

    # 2. Check environment variable
    env_var = profile.auth_config.get("env_var", f"{service_name.upper()}_TOKEN")
    token = os.environ.get(env_var)
    if token:
        return AuthResult(success=True, headers={"Authorization": f"Bearer {token}"})

    # 3. Check common env var patterns
    common_vars = ["API_TOKEN", "BEARER_TOKEN", "AUTH_TOKEN", "TOKEN"]
    for var in common_vars:
        token = os.environ.get(var)
        if token:
            return AuthResult(success=True, headers={"Authorization": f"Bearer {token}"})

    # 4. Can't auto-resolve
    help_msg = profile.auth_config.get("help", "Bearer token required")
    return AuthResult(
        success=False,
        error=f"AUTH_REQUIRED: Bearer token needed. {help_msg}. "
              f"Set env var {env_var}, or run: polyglot auth set {service_name} --token <value>"
    )


def _negotiate_api_key(service_name: str, profile: APIProfile) -> AuthResult:
    """Negotiate API key auth."""
    # 1. Check stored credentials
    cred = get_credential(service_name)
    if cred:
        key_location = cred.get("meta", {}).get("location", "query")
        key_name = cred.get("meta", {}).get("key_name", "api_key")
        if key_location == "header":
            return AuthResult(success=True, headers={key_name: cred["value"]})
        else:
            return AuthResult(success=True, params={key_name: cred["value"]})

    # 2. Check environment variable
    env_var = profile.auth_config.get("env_var", f"{service_name.upper()}_API_KEY")
    key = os.environ.get(env_var)
    if key:
        return AuthResult(success=True, params={"api_key": key})

    # 3. Common patterns
    for var in ["API_KEY", f"{service_name.upper()}_KEY"]:
        key = os.environ.get(var)
        if key:
            return AuthResult(success=True, params={"api_key": key})

    help_msg = profile.auth_config.get("help", "API key required")
    return AuthResult(
        success=False,
        error=f"AUTH_REQUIRED: API key needed. {help_msg}. "
              f"Set env var {env_var}, or run: polyglot auth set {service_name} --key <value>"
    )


def _negotiate_basic(service_name: str, profile: APIProfile) -> AuthResult:
    """Negotiate HTTP Basic auth."""
    cred = get_credential(service_name)
    if cred and cred.get("type") == "basic":
        token = base64.b64encode(f"{cred['meta']['username']}:{cred['value']}".encode()).decode()
        return AuthResult(success=True, headers={"Authorization": f"Basic {token}"})

    # Check env
    user = os.environ.get(f"{service_name.upper()}_USER") or os.environ.get("API_USER")
    pwd = os.environ.get(f"{service_name.upper()}_PASS") or os.environ.get("API_PASS")
    if user and pwd:
        token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        return AuthResult(success=True, headers={"Authorization": f"Basic {token}"})

    return AuthResult(
        success=False,
        error=f"AUTH_REQUIRED: Basic auth (username:password) needed. "
              f"Run: polyglot auth set {service_name} --user <user> --pass <pass>"
    )


def _negotiate_oauth2(service_name: str, profile: APIProfile) -> AuthResult:
    """Negotiate OAuth2 auth."""
    cred = get_credential(service_name)
    if cred and cred.get("type") == "oauth2":
        return AuthResult(success=True, headers={"Authorization": f"Bearer {cred['value']}"})

    # Check env
    token = os.environ.get(f"{service_name.upper()}_OAUTH_TOKEN")
    if token:
        return AuthResult(success=True, headers={"Authorization": f"Bearer {token}"})

    return AuthResult(
        success=False,
        error=f"AUTH_REQUIRED: OAuth2 access token needed. "
              f"Run: polyglot auth set {service_name} --token <value>"
    )


def apply_auth(request_headers: dict, request_params: dict, auth_result: AuthResult) -> tuple[dict, dict]:
    """Apply auth result to request headers and params."""
    if auth_result.success:
        request_headers.update(auth_result.headers)
        request_params.update(auth_result.params)
    return request_headers, request_params
