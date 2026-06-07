# Backend Architecture

## 1. Overview

The Architecture AI backend is a stateless FastAPI service that acts as the
integration layer between three external systems:

```
React Frontend
      │  HTTPS / JSON
      ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend                        │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  /auth   │  │   /upload    │  │  /analyze (TBD)  │  │
│  │  router  │  │   router     │  │     router       │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  │
│       │               │                   │             │
│  ┌────▼───────────────▼───────────────────▼──────────┐  │
│  │              app/security/security.py              │  │
│  │          (JWT create / verify / bcrypt)            │  │
│  └───────────────────────┬────────────────────────────┘  │
│                          │                              │
│  ┌───────────────────────▼────────────────────────────┐  │
│  │          chatbot/services/llm_service.py            │  │
│  │    BaseLLMService ABC  →  StubLLMService (now)      │  │
│  │                        →  GeminiService (later)     │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
      │                    │                    │
  Google OAuth          File System          Database
  (userinfo API)      (upload_temp/)     (managed externally)
```

---

## 2. Module Responsibilities

### `app/main.py`
- Constructs the FastAPI application via factory function `create_application()`.
- Registers CORS middleware with origins from config.
- Mounts all routers with their prefixes.

### `app/config.py`
- Single `Settings` class (pydantic-settings v2) reads `.env` once at startup.
- Cached via `lru_cache`; all modules import the singleton `settings`.
- Provides derived helpers `allowed_origins_list` and `allowed_extensions_list`.

### `app/security/security.py`
- `hash_password` / `verify_password` — bcrypt wrappers.
- `create_access_token` / `create_refresh_token` — signed JWT creation.
- `decode_token` / `get_token_subject` — JWT verification with typed errors.

### `app/routers/auth.py`
- Google OAuth 2.0 authorization-code flow.
- Issues application-owned JWT pairs (frontend never receives Google tokens directly).

### `app/routers/file_upload.py`
- Validates extension and size before writing.
- Assigns a UUID filename to prevent collisions and path traversal.
- Stores files in `utils/upload_temp/`.

### `app/routers/base.py`
- Health check endpoints for load balancers and monitoring.

### `app/models/base_db.py`
- Pydantic data shapes for DB entities.
- **Read-only contract** — schema is managed externally.

### `app/utils/helpers.py`
- Stateless utility functions: extension extraction, sanitisation, directory creation.

### `chatbot/services/llm_service.py`
- `BaseLLMService` defines the contract every LLM provider must fulfil.
- `StubLLMService` runs during development without an API key.
- `get_llm_service()` factory selects the concrete implementation at runtime.

---

## 3. Request Flow — Image Upload

```
Client  →  POST /upload/image  (multipart, Authorization: Bearer <jwt>)
              │
              ▼
       file_upload.get_current_user()
              │  decode JWT → extract user_id
              │
              ▼
       _assert_filename_present()
       _assert_extension_allowed()   ← checks config.allowed_extensions_list
              │
              ▼
       await file.read()
       _assert_size_within_limit()   ← checks config.MAX_FILE_SIZE_MB
              │
              ▼
       uuid4() → stored_filename
       _persist_file()               ← writes to utils/upload_temp/<uuid>.ext
              │
              ▼
       return UploadResponse(file_id, original_filename, stored_path, …)
```

---

## 4. Authentication Flow — Google OAuth

```
1. Client  →  GET /auth/google/login
2. Backend → 302 Redirect → Google Consent Screen
3. Google  → 302 Redirect → GET /auth/google/callback?code=XXX
4. Backend → POST google/token (exchange code → google_access_token)
5. Backend → GET google/userinfo (fetch email, name, sub, picture)
6. Backend → create_access_token({sub, email, name})
             create_refresh_token({sub, email, name})
7. Backend → return TokenResponse(access_token, refresh_token)
8. Client  stores tokens; uses access_token in Authorization: Bearer header
```

---

## 5. Future Modules (not yet implemented)

| Module | Purpose |
|---|---|
| `app/routers/analyze.py` | POST /analyze — trigger LLM analysis on an uploaded image |
| `app/routers/history.py` | GET /history — return a user's past analysis results |
| `chatbot/services/gemini_service.py` | Concrete Gemini Vision LLM service |
| `ingestion/` | Dataset loading and vector store population pipeline |

---

## 6. Security Notes

- JWT secret is loaded from env; app refuses to start if it is empty or `"changeme"`.
- Uploaded files are stored by UUID, never by user-supplied name.
- Google client secret never appears in logs or responses.
- CORS origins are explicitly allowlisted via config.
