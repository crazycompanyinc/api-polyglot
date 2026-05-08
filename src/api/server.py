"""
Polyglot HTTP Server
REST API so other agents can use polyglot without importing.
"""

import json
import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import Polyglot
from src.core import list_profiles
from src.discovery import list_known_apis
from src.execute import clear_cache as _clear_cache

_polyglot = Polyglot()


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)
        flat = {k: v[0] if len(v) == 1 else v for k, v in params.items()}

        if path == "/health":
            return self._json(200, {"status": "ok", "service": "api-polyglot", "version": "1.0.0"})

        if path == "/apis":
            return self._json(200, _polyglot.list_apis())

        if path == "/profiles":
            profiles = list_profiles()
            return self._json(200, {
                "profiles": [
                    {"name": p.name, "base_url": p.base_url, "auth": p.auth_type,
                     "endpoints": len(p.endpoints), "uses": p.use_count,
                     "success_rate": round(p.success_rate, 2)}
                    for p in profiles
                ]
            })

        if path == "/call":
            url = flat.get("url")
            if not url:
                return self._json(400, {"error": "Missing 'url' parameter"})
            resp = _polyglot.get(url)
            return self._json(200, _response_dict(resp))

        if path == "/cache/clear":
            _clear_cache()
            return self._json(200, {"cleared": True})

        self._json(404, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        content_length = int(self.headers.get("Content-Length", 0))
        body_text = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            body = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError:
            return self._json(400, {"error": "Invalid JSON body"})

        if path == "/ask":
            intent = body.get("intent") or body.get("query") or body.get("q")
            if not intent:
                return self._json(400, {"error": "Missing 'intent' field"})
            kwargs = {k: v for k, v in body.items() if k not in ("intent", "query", "q")}
            resp = _polyglot.ask(intent, **kwargs)
            return self._json(200, _response_dict(resp))

        if path == "/call":
            url = body.get("url")
            method = body.get("method", "GET").upper()
            if not url:
                return self._json(400, {"error": "Missing 'url' field"})
            resp = _polyglot.call(
                method, url,
                headers=body.get("headers"),
                params=body.get("params"),
                body=body.get("body"),
                timeout=body.get("timeout", 30),
                cache_ttl=body.get("cache_ttl", 0),
            )
            return self._json(200, _response_dict(resp))

        if path == "/auth/set":
            service = body.get("service")
            value = body.get("value") or body.get("token") or body.get("key")
            cred_type = body.get("type", "bearer")
            if not service or not value:
                return self._json(400, {"error": "Missing 'service' and 'value'"})
            meta = {k: v for k, v in body.items() if k not in ("service", "value", "token", "key", "type")}
            _polyglot.set_credential(service, value, cred_type, **meta)
            return self._json(200, {"stored": True, "service": service, "type": cred_type})

        if path == "/discover":
            text = body.get("text") or body.get("url") or body.get("name")
            if not text:
                return self._json(400, {"error": "Missing 'text' field"})
            profile = _polyglot.discover(text)
            if profile:
                return self._json(200, {
                    "discovered": True,
                    "profile": {
                        "id": profile.id,
                        "name": profile.name,
                        "base_url": profile.base_url,
                        "auth_type": profile.auth_type,
                        "endpoints": profile.endpoints,
                    },
                })
            return self._json(404, {"discovered": False, "error": "Could not discover API"})

        self._json(404, {"error": f"Unknown endpoint: {path}"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, status, data):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def _response_dict(resp):
    return {
        "status": resp.status_code,
        "data": resp.data,
        "error": resp.error,
        "duration_ms": round(resp.duration_ms, 1),
        "cached": resp.cached,
    }


def serve(host="127.0.0.1", port=7878):
    server = HTTPServer((host, port), Handler)
    print(f"Polyglot server running at http://{host}:{port}")
    print(f"  GET  /health          - Health check")
    print(f"  GET  /apis            - List known APIs")
    print(f"  GET  /profiles        - List learned profiles")
    print(f"  POST /ask             - Natural language API call")
    print(f"  POST /call            - Direct API call")
    print(f"  POST /discover        - Discover an API")
    print(f"  POST /auth/set        - Store credentials")
    server.serve_forever()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7878
    serve(port=port)
