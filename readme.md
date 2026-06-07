# Architecture AI — Backend API

FastAPI backend for an AI system that recognises architectural styles from photographs.

## Quick Start

```bash
cd api_base
python3.10 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then edit .env with your credentials
python run_api.py
```

API docs: http://localhost:8000/docs  
Health check: http://localhost:8000/health

## Features

- Google OAuth 2.0 login → JWT access + refresh tokens
- Authenticated image upload (jpg/jpeg/png/webp, max 10 MB)
- Pluggable LLM service layer (stub returns placeholder until API key is set)
- Structured JSON responses throughout
- Full OpenAPI schema at `/docs` and `/redoc`

## Project Structure

See [CLAUDE.md](CLAUDE.md) for the full structure and all development rules.

## Documentation

| File | Purpose |
|---|---|
| [docs/backend_architecture.md](docs/backend_architecture.md) | System architecture and request flow |
| [docs/api_spec.md](docs/api_spec.md) | All API endpoints, request/response formats |
| [docs/development_roadmap.md](docs/development_roadmap.md) | Step-by-step build plan |
| [CLAUDE.md](CLAUDE.md) | Rules for Claude Code and developers |

## Running Tests

```bash
pytest test/ -v
```

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Random hex string for JWT signing |
| `GOOGLE_CLIENT_ID` | Yes | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Yes | From Google Cloud Console |
| `LLM_API_KEY` | No | Gemini / OpenAI key (stub used if empty) |
| `DB_CONNECTION` | No | Database URL (managed externally) |
