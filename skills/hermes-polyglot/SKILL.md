---
name: hermes-polyglot
description: "API Polyglot Agent - Call any API from natural language without manual integration. Use when you need to call an external API, fetch data from a web service, or integrate with a service that doesn't have a dedicated tool. Handles discovery, auth negotiation, request building, and execution automatically. Zero configuration required."
---

# Hermes Polyglot Skill

Call any API from natural language. Polyglot auto-discovers the service, negotiates auth, builds and executes the request.

## Quick Reference

```bash
# Check if polyglot server is running
curl -s http://localhost:7878/health

# Call from natural language (most common)
curl -s -X POST http://localhost:7878/ask \
  -H "Content-Type: application/json" \
  -d '{"intent": "your request in plain language"}'

# Direct API call
curl -s -X POST http://localhost:7878/call \
  -H "Content-Type: application/json" \
  -d '{"method": "GET", "url": "https://api.example.com/endpoint", "params": {"key": "val"}}'

# List known APIs
curl -s http://localhost:7878/apis | python3 -m json.tool

# Store a credential
curl -s -X POST http://localhost:7878/auth/set \
  -H "Content-Type: application/json" \
  -d '{"service": "github", "token": "ghp_xxx", "type": "bearer"}'
```

## When To Use This Skill

**USE polyglot when:**
- You need to call an external API that doesn't have a dedicated Hermes tool
- The user asks you to fetch data from a web service
- You need to check if a URL/API endpoint is reachable
- You need data from GitHub, USGS, CoinGecko, HackerNews, or similar services

**DO NOT use polyglot when:**
- A dedicated tool exists (e.g., use `gh` for GitHub, `web_search` for searching)
- The request needs browser interaction (use browser tools)
- You need to extract data from HTML pages (use web_extract)

## Workflow

### 1. Check Server

```bash
curl -s http://localhost:7878/health 2>/dev/null || echo "NOT_RUNNING"
```

If NOT_RUNNING, start it:
```bash
cd ~/.hermes/api-polyglot && python3 polyglot serve --port 7878 &
sleep 1
```

### 2. Make the Call

**Natural language (recommended):**
```bash
curl -s -X POST http://localhost:7878/ask \
  -H "Content-Type: application/json" \
  -d '{"intent": "list issues from github repo crazycompanyinc/api-polyglot"}'
```

**Direct call (when you know the exact URL):**
```bash
curl -s -X POST http://localhost:7878/call \
  -H "Content-Type: application/json" \
  -d '{"method": "GET", "url": "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"}'
```

### 3. Handle Auth If Needed

If response contains `AUTH_REQUIRED`:
1. Read the error message — it tells you exactly what credential is needed
2. Check if it's already available (env var, stored credential)
3. If not, ask the user clearly: "This API needs an X. Here's how to get one: [link]"
4. Once you have the credential, store it:
```bash
curl -s -X POST http://localhost:7878/auth/set \
  -H "Content-Type: application/json" \
  -d '{"service": "github", "token": "TOKEN", "type": "bearer"}'
```
5. Retry the original call

## Python Usage (In-Process)

When writing Python code that uses polyglot directly:

```python
import sys
sys.path.insert(0, "/path/to/api-polyglot")
from src import Polyglot, ask

# Quick ask
resp = ask("mostrame precios de bitcoin desde coingecko")
if resp.error:
    print(f"Error: {resp.error}")
else:
    print(resp.data)

# Direct call
poly = Polyglot()
resp = poly.get("https://api.coigecko.com/api/v3/ping")
if resp.status_code == 200:
    print("API is up")
```

## Known Built-In APIs

| Service | Auth Needed | Example Intent |
|---------|------------|----------------|
| USGS Earthquakes | None | "earthquakes magnitude 5+ japan last day" |
| CoinGecko | None | "bitcoin price in usd" |
| HackerNews | None | "top 10 hacker news stories" |
| GitHub | Token | "issues from repo owner/name" |
| OpenWeatherMap | API Key | "weather in Buenos Aires" |
| JSONPlaceholder | None | "fake posts for testing" |

## Troubleshooting

**"Could not discover API"**: Be more specific. Include the service name or a URL.

**"AUTH_REQUIRED"**: Polyglot tells you exactly what's needed. Get the credential and store it.

**Server not responding**: Start it with `python3 polyglot serve --port 7878 &`
