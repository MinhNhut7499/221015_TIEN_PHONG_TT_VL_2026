# Development Roadmap

Step-by-step plan for building the Architecture AI backend from the current
skeleton to a fully functional production system.

Each phase must be completed and tested before the next one begins.

---

## Phase 0 — Foundation (DONE)

The skeleton built in this step:

- [x] Full project folder structure
- [x] `app/config.py` — pydantic-settings, `.env` loading
- [x] `app/security/security.py` — JWT create/verify, bcrypt
- [x] `app/routers/base.py` — health check endpoints
- [x] `app/routers/auth.py` — Google OAuth flow, JWT issuance
- [x] `app/routers/file_upload.py` — authenticated image upload
- [x] `app/models/base_db.py` — data shapes (read-only DB contract)
- [x] `chatbot/services/llm_service.py` — pluggable LLM service layer
- [x] `test/test_base.py` — smoke tests
- [x] `requirements.txt`, `.env.example`, `run_api.py`, `start.sh`
- [x] Architecture, API spec, and roadmap documentation

**Verify phase 0 is working before continuing:**
```bash
cp .env.example .env
# Fill in SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
python run_api.py
# Visit http://localhost:8000/health → should return {"status": "ok", ...}
pytest test/ -v
```

---

## Phase 1 — Database Integration

**Goal:** Connect the application to a real database and persist users + history.

Steps:
1. Choose ORM: SQLAlchemy 2.x (async) recommended for FastAPI.
2. Add `sqlalchemy[asyncio]`, `asyncpg` (PostgreSQL) or `aiosqlite` (SQLite dev) to `requirements.txt`.
3. Create `app/database.py`:
   - `AsyncEngine` and `AsyncSession` factory from `DB_CONNECTION`.
   - `get_db()` FastAPI dependency that yields a session.
4. Create `app/models/user.py` — SQLAlchemy ORM model for the `users` table.
5. Create `app/models/analysis_history.py` — ORM model for `analysis_history`.
6. Create `app/repositories/` package:
   - `user_repository.py` — `upsert_google_user()`, `get_user_by_sub()`
   - `history_repository.py` — `create_history()`, `list_history_for_user()`
7. Update `app/routers/auth.py` to upsert the user on every login.
8. Run first migration (Alembic): `alembic init alembic && alembic revision --autogenerate`.

**New files:**
```
app/database.py
app/models/user.py
app/models/analysis_history.py
app/repositories/
    user_repository.py
    history_repository.py
alembic/
    alembic.ini
    env.py
    versions/
```

---

## Phase 2 — LLM Integration

**Goal:** Replace `StubLLMService` with a real Gemini or OpenAI Vision call.

Steps:
1. Obtain an API key and add `LLM_API_KEY` and `LLM_MODEL` to `.env`.
2. Add the provider SDK to `requirements.txt`:
   - Gemini: `google-generativeai`
   - OpenAI: `openai`
3. Create `chatbot/services/gemini_service.py` (or `openai_service.py`):
   - Inherit `BaseLLMService`.
   - Implement `analyze_image()`: read file bytes → send to vision API → parse response.
   - Implement `is_available()`: test API connectivity.
4. Update `get_llm_service()` factory in `chatbot/services/llm_service.py` to return the new implementation.
5. Create `app/routers/analyze.py`:
   - `POST /analyze` — accepts `file_id`, calls `get_llm_service().analyze_image()`, saves result to DB.
6. Register the new router in `app/main.py`.
7. Write tests in `test/test_analyze.py`.

**New files:**
```
chatbot/services/gemini_service.py
app/routers/analyze.py
test/test_analyze.py
```

---

## Phase 3 — User History

**Goal:** Let authenticated users retrieve their past analyses.

Steps:
1. Create `app/routers/history.py`:
   - `GET /history` — paginated list of the current user's analyses.
   - `GET /history/{analysis_id}` — single analysis detail.
2. Register the router in `app/main.py`.
3. Write tests in `test/test_history.py`.

---

## Phase 4 — Hardening and Production Readiness

**Goal:** Make the system safe, observable, and deployable.

Steps:
1. **Rate limiting** — add `slowapi` middleware to throttle `/upload/image` and `/analyze`.
2. **Structured logging** — replace `print` / uvicorn default with `structlog` JSON output.
3. **Sentry integration** — add `sentry-sdk[fastapi]`; call `sentry_sdk.init()` in `main.py`.
4. **Request ID middleware** — inject `X-Request-ID` header for tracing.
5. **Input sanitisation** — strip EXIF metadata from uploaded images with `Pillow`.
6. **File storage** — swap `utils/upload_temp/` for object storage (S3 / GCS) via a storage abstraction layer.
7. **Dockerfile** — multi-stage build targeting Python 3.10-slim.
8. **CI pipeline** — GitHub Actions: lint (ruff), type-check (mypy), test (pytest), build Docker image.
9. **Production env check** — refuse to start if `APP_ENV=production` and `DEBUG=true`.

---

## Phase 5 — Vector Search / RAG (optional, thesis extension)

**Goal:** Enable semantic image retrieval using pre-computed embeddings.

Steps:
1. Populate `utils/data_vector/` via the `ingestion/` pipeline.
2. Integrate a vector store (FAISS local or Qdrant hosted).
3. Add `POST /search/similar` endpoint: embed query image → nearest-neighbour lookup → return similar examples.
4. Feed retrieved examples as few-shot context to the LLM analysis prompt.

---

## Dependency Summary by Phase

| Phase | New Packages |
|---|---|
| 1 | sqlalchemy[asyncio], asyncpg, aiosqlite, alembic |
| 2 | google-generativeai OR openai, Pillow |
| 3 | (no new packages) |
| 4 | slowapi, structlog, sentry-sdk[fastapi] |
| 5 | faiss-cpu OR qdrant-client, sentence-transformers |
