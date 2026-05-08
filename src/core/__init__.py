"""
API Polyglot Agent - Core Orchestrator
Discovers, negotiates auth, and calls any API from natural language intent.
"""

import json
import hashlib
import time
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Data Models ───────────────────────────────────────────────────────────────

@dataclass
class APIProfile:
    """Learned profile of an API endpoint."""
    name: str
    base_url: str
    description: str
    auth_type: str = "none"          # none, api_key, bearer, basic, oauth2, cookie
    auth_config: dict = field(default_factory=dict)
    endpoints: list = field(default_factory=list)
    rate_limit: Optional[dict] = None
    discovered_at: float = field(default_factory=time.time)
    last_used: float = 0
    use_count: int = 0
    success_rate: float = 1.0

    @property
    def id(self) -> str:
        return hashlib.sha256(f"{self.base_url}:{self.name}".encode()).hexdigest()[:12]


@dataclass
class APIRequest:
    """A resolved API request ready to execute."""
    method: str
    url: str
    headers: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    body: Optional[dict] = None
    auth_type: str = "none"
    auth_config: dict = field(default_factory=dict)


@dataclass
class APIResponse:
    """Normalized API response."""
    status_code: int
    data: any
    headers: dict = field(default_factory=dict)
    raw_text: str = ""
    error: Optional[str] = None
    duration_ms: float = 0
    cached: bool = False


# ─── Profile Store ─────────────────────────────────────────────────────────────

PROFILE_DIR = Path.home() / ".api-polyglot" / "profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def save_profile(profile: APIProfile):
    path = PROFILE_DIR / f"{profile.id}.json"
    path.write_text(json.dumps(asdict(profile), indent=2, default=str))


def load_profile(profile_id: str) -> Optional[APIProfile]:
    path = PROFILE_DIR / f"{profile_id}.json"
    if path.exists():
        data = json.loads(path.read_text())
        return APIProfile(**data)
    return None


def find_profile_by_url(base_url: str) -> Optional[APIProfile]:
    for f in PROFILE_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        if data.get("base_url") == base_url:
            return APIProfile(**data)
    return None


def list_profiles() -> list[APIProfile]:
    profiles = []
    for f in PROFILE_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        profiles.append(APIProfile(**data))
    return profiles


def find_profile_by_name(name: str) -> Optional[APIProfile]:
    for f in PROFILE_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        if data.get("name", "").lower() == name.lower():
            return APIProfile(**data)
    return None


# ─── Credential Store ──────────────────────────────────────────────────────────

CREDS_DIR = Path.home() / ".api-polyglot" / "credentials"
CREDS_DIR.mkdir(parents=True, exist_ok=True)


def store_credential(service_name: str, cred_type: str, value: str, meta: dict = None):
    """Store a credential securely. In production, use keyring or vault."""
    data = {"type": cred_type, "value": value, "meta": meta or {}}
    path = CREDS_DIR / f"{service_name}.json"
    path.write_text(json.dumps(data))
    os.chmod(path, 0o600)


def get_credential(service_name: str) -> Optional[dict]:
    path = CREDS_DIR / f"{service_name}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def has_credential(service_name: str) -> bool:
    return (CREDS_DIR / f"{service_name}.json").exists()


# ─── Intent Parser ─────────────────────────────────────────────────────────────

class Intent:
    """Parsed user intent."""
    def __init__(self, raw: str):
        self.raw = raw
        self.action = None          # get, post, list, search, monitor, compose
        self.resource = None        # what resource to access
        self.filters = dict()       # query filters
        self.output_format = "json" # json, text, table
        self.target_service = None  # optional known service name
        self._parse()

    def _parse(self):
        raw_lower = self.raw.lower()

        # Detect action
        if any(w in raw_lower for w in ["busc", "search", "find", "look"]):
            self.action = "search"
        elif any(w in raw_lower for w in ["list", "listá", "mostrá", "show", "get", "trae"]):
            self.action = "list"
        elif any(w in raw_lower for w in ["post", "creá", "create", "mandá", "send", "enviá"]):
            self.action = "post"
        elif any(w in raw_lower for w in ["monitor", "watch", "alert", "avis"]):
            self.action = "monitor"
        elif any(w in raw_lower for w in ["compon", "combin", "cross", "mix", "cruz"]):
            self.action = "compose"
        else:
            self.action = "get"

        # Detect output format
        if any(w in raw_lower for w in ["email", "telegram", "slack", "mensaj"]):
            self.output_format = "notify"
        elif any(w in raw_lower for w in ["csv", "spreadsheet", "excel"]):
            self.output_format = "csv"
        elif any(w in raw_lower for w in ["report", "resumen", "summary"]):
            self.output_format = "report"

    def __repr__(self):
        return f"Intent(action={self.action}, resource={self.resource}, filters={self.filters})"
