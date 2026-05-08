# API Polyglot Agent

> Call any API from natural language. No manual integration. No YAML connectors. No configuration files.

Polyglot discovers APIs automatically, negotiates authentication, builds the right request, and returns structured data — all from a simple sentence.

## Quick Start

```bash
pip install -r requirements.txt

# Call an API in natural language
python polyglot ask "mostrame los últimos terremotos de USGS"

# Direct API call
python polyglot call GET https://api.coingecko.com/api/v3/simple/price -p "ids=bitcoin" -p "vs_currencies=usd"

# Start the HTTP server (for other agents)
python polyglot serve --port 7878

# List known/built-in APIs
python polyglot apis
```

## HTTP Server API

When running as a server, other agents can use Polyglot programmatically:

```bash
# Health check
curl http://localhost:7878/health

# List available APIs
curl http://localhost:7878/ask

# Call from natural language
curl -X POST http://localhost:7878/ask \
  -H "Content-Type: application/json" \
  -d '{"intent": "listar los últimos issues del repo crazycompanyinc/api-polyglot"}'

# Direct API call
curl -X POST http://localhost:7878/call \
  -H "Content-Type: application/json" \
  -d '{"method": "GET", "url": "https://api.coingecko.com/api/v3/ping"}'

# Store credentials
curl -X POST http://localhost:7878/auth/set \
  -H "Content-Type: application/json" \
  -d '{"service": "github", "token": "ghp_xxx", "type": "bearer"}'
```

## Built-in APIs (zero config)

| Service | Auth | What it does |
|---------|------|-------------|
| GitHub | Token | Repos, issues, PRs, search |
| USGS Earthquakes | None | Real-time earthquake data |
| CoinGecko | None | Crypto prices & market data |
| HackerNews | None | Top/new stories |
| OpenWeatherMap | API Key | Weather & forecasts |
| JSONPlaceholder | None | Fake data for testing |

## How It Works

1. **Discovery** — Match text to known APIs or probe URLs for OpenAPI specs
2. **Auth Negotiation** — Check stored credentials, env vars, or tell you exactly what's needed
3. **Request Building** — Map intent to the right endpoint + parameters
4. **Execution** — Call with retries, rate-limit handling, pagination, caching
5. **Learning** — Save API profiles so subsequent calls are faster

## For Hermes Agents

When the `hermes-polyglot` skill is loaded, agents can call any API without
asking the user for configuration. The agent handles discovery, auth, and
execution automatically.

Skill path: `skills/hermes-polyglot/SKILL.md`
