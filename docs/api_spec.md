# API Specification

Base URL (development): `http://localhost:8000`  
All responses are `application/json` unless noted otherwise.  
Interactive docs (Swagger UI `/docs`, ReDoc `/redoc`, OpenAPI `/openapi.json`) are **disabled** — the API surface is not exposed publicly. This document is the reference.

---

## Authentication

Protected endpoints require:
```
Authorization: Bearer <access_token>
```

The `access_token` is obtained via the Google OAuth flow described below.

---

## 1. Health Endpoints

### `GET /`
Root health check.

**Response 200**
```json
{
  "status": "ok",
  "app_name": "Architecture AI API",
  "environment": "development",
  "version": "1.0.0"
}
```

---

### `GET /health`
Deep health check (polled by load balancers).

**Response 200** — same schema as `GET /`

---

## 2. Authentication Endpoints

### `GET /auth/google/login`
Redirect the browser to Google's OAuth consent screen.

**Response 302** — Location: Google authorization URL  
No request body needed.

---

### `GET /auth/google/callback`
Exchange the Google authorization code for application JWT tokens.

**Query Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `code` | string | Yes | One-time authorization code from Google |

**Response 200**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Response 400** — Google code exchange failed
```json
{
  "detail": "Failed to exchange authorization code with Google"
}
```

---

### `POST /auth/google`
Exchange a Google ID token (from `@react-oauth/google`) for application JWT tokens.

**Request body (JSON)**
```json
{ "credential": "<google-id-token>" }
```

**Response 200** — same shape as the callback `TokenResponse` above.

**Response 401** — Invalid ID token or audience mismatch.

---

### `GET /auth/me`
Return the authenticated user's profile from the Users table. Requires auth.

**Headers**
```
Authorization: Bearer <access_token>
```

**Response 200**
```json
{
  "name": "Jane Doe",
  "email": "jane@example.com",
  "picture": "https://lh3.googleusercontent.com/a/...",
  "role": "user"
}
```

**Response 404** — No user row matches the token subject.

---

### `DELETE /auth/account`
Delete the authenticated user's own account and data (Google Play / App Store
self-service deletion). Requires auth for an **active** account.

The account row is anonymised (name, email, picture, Google sub and password hash
are scrubbed and `IsActive` set to false) and all the user's projects, uploaded
images, physical files and analysis history are removed. Anonymised financial
records (payment transactions, token ledger) are retained for accounting and
carry no personal data. The operation is irreversible and idempotent: a repeat
call on an already-deleted account returns `deleted: false` (or 403, since the
token is now for an inactive account).

**Headers**
```
Authorization: Bearer <access_token>
```

**Response 200**
```json
{
  "deleted": true
}
```

**Response 403** — Token missing/invalid, or the account is already deactivated/deleted.

---

### Hybrid mobile app login (Cloud-Sync Polling)

Google login for the Flutter WebView app. The web (inside the app) registers a
session, the app opens Google in a Chrome Custom Tab, the flutter callback stores
the JWT pair against the session, and the web polls until it claims the token.
All `session_id` / `state` values must be **UUID v4**; sessions are one-time use
and expire after `LOGIN_SESSION_TTL_MIN` (default 10 minutes). Requires the
`LoginSessions` table.

#### `POST /auth/login-session`
Register (or reset) a pending session.

**Request body**
```json
{ "session_id": "<uuid-v4>" }
```
**Response 200** — `{ "ok": true }`  
**Response 400** — `session_id` is not a UUID v4.

#### `GET /auth/login-session/{session_id}`
Poll a session for its token (consumed on the first `completed` read).

**Response 200**
```json
{ "status": "pending" | "completed" | "expired",
  "access_token": "<jwt|null>", "refresh_token": "<jwt|null>" }
```
**Response 400** — `session_id` is not a UUID v4.

#### `GET /auth/google/login/flutter?session_id=<uuid-v4>`
Opened by the app in a Chrome Custom Tab. **Response 307** — redirect to Google's
consent screen with `state=session_id`. **400** if `session_id` is not a UUID v4.

#### `GET /auth/google/callback/flutter?code=...&state=<uuid-v4>`
Google's redirect target (registered as `GOOGLE_FLUTTER_REDIRECT_URI`). Verifies
the session is still pending, exchanges the code, and stores the JWT pair against
the session. Returns an **HTML** page (`text/html`) telling the user to close the
tab. A forged/unknown/expired `state` is rejected (HTML error, **400**) *before*
any Google exchange or account creation.

---

## 3. File Upload Endpoints

### `POST /upload/image`
Upload a single architectural image. Requires authentication.

**Headers**
```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

**Form Fields**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | File | Yes | Image file (jpg, jpeg, png, webp) |

**Constraints**
- Maximum file size: `MAX_FILE_SIZE_MB` (default 10 MB)
- Allowed extensions: jpg, jpeg, png, webp

**Response 201**
```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "original_filename": "exterior.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 2048000,
  "stored_path": "utils/upload_temp/550e8400-e29b-41d4-a716-446655440000.jpg",
  "uploaded_by": "google-sub-id-12345"
}
```

**Response 400** — Missing filename
```json
{ "detail": "Uploaded file must have a filename" }
```

**Response 401** — Invalid or missing token
```json
{ "detail": "Token validation failed: ..." }
```

**Response 413** — File too large
```json
{ "detail": "File size 12,000,000 bytes exceeds the 10 MB limit" }
```

**Response 422** — Unsupported file type
```json
{ "detail": "File type '.gif' is not supported. Allowed types: ['jpg', 'jpeg', 'png', 'webp']" }
```

---

## 4. Analysis Endpoints

### `POST /analyze`
Run the 7-agent LLM pipeline on a previously uploaded image. Requires auth and
all three LLM API keys configured (otherwise **503**).

**Request body (JSON)**
```json
{ "file_id": "550e8400-e29b-41d4-a716-446655440000" }
```

**Response 200**
```json
{
  "style": "Gothic",
  "confidence": 0.62,
  "explanation": "Predominantly Gothic with Renaissance influence...",
  "key_evidence": ["pointed arch detected", "vertical dominance high"],
  "components": [
    {
      "component_id": "c1",
      "component_type": "arch",
      "detection_confidence": 0.91,
      "bounding_box": { "x_min": 120, "y_min": 40, "x_max": 320, "y_max": 410 },
      "agent1": { "...": "..." },
      "agent2": { "...": "..." },
      "agent3": { "...": "..." },
      "agent4": { "...": "..." }
    }
  ],
  "processing_time_ms": 41230.5,
  "style_distribution": {
    "distribution": { "Gothic": 0.55, "Renaissance": 0.28, "Baroque": 0.17 },
    "primary": "Gothic",
    "secondary": ["Renaissance", "Baroque"]
  },
  "composition_explanation": "Dominant Gothic with Renaissance influence...",
  "evidence_per_style": { "Gothic": ["..."], "Renaissance": ["..."] },
  "gradcam_b64": "<png-base64 or null>",
  "explanation_vi": "Chủ yếu là Gothic với ảnh hưởng Phục Hưng...",
  "key_evidence_vi": ["vòm nhọn", "tỷ lệ theo chiều dọc"],
  "composition_explanation_vi": "...",
  "evidence_per_style_vi": { "Gothic": ["..."] },
  "degraded": false,
  "warnings": [],
  "certainty_margin": 0.27,
  "distribution_entropy": 0.94,
  "image_id": "a1b2c3d4-..."
}
```

Notes:
- `image_id` is the persisted `Images.ImageId` of this analysis (or `null` when
  the result was not persisted, e.g. test/legacy tokens). The frontend uses it to
  open the follow-up Q&A (`POST /analyze/{image_id}/ask`) for the just-analysed image.
- `bounding_box` is the YOLO pixel-space box (in the source image's coordinate
  space) used by the frontend to draw the detection overlay.
- `gradcam_b64` is a PNG heatmap overlay from the ResNet50 style head, populated
  only when a real `STYLE_HEAD_MODEL_PATH` is set and `ENABLE_GRADCAM=True`;
  otherwise `null` (e.g. with the mock feature service).
- `*_vi` fields hold Vietnamese translations of the narrative, populated when
  `ENABLE_BILINGUAL=True`; `null` when disabled or translation failed.

**Response 503** — LLM pipeline not configured (missing API keys).

---

### `GET /analyze/history`
Retrieve the authenticated user's past analyses (newest first).

**Response 200**
```json
{
  "items": [
    {
      "image_id": "...",
      "image_path": "utils/upload_temp/...jpg",
      "file_id": "550e8400-e29b-41d4-a716-446655440000",
      "analysis_status": "completed",
      "uploaded_at": "2026-06-06T10:00:00+00:00",
      "style": "Gothic",
      "confidence": 0.62,
      "has_detail": true
    }
  ],
  "total": 1
}
```

`has_detail` is true when the full result (DetailJson) was persisted and the
analysis can be re-opened with full fidelity.

---

### `GET /analyze/history/{image_id}`
Re-open a past analysis. Returns the full stored `AnalyzeResponse` JSON
(`DetailJson`) when available, or a summary built from the persisted
style/confidence/explanation/evidence for analyses created before full-result
persistence existed. Requires auth; only the owner can read it.

**Response 200** — same shape as `POST /analyze` (full), or a summary subset
(`style`, `confidence`, `explanation`, `key_evidence`, empty `components`).
Both include `image_id` and `file_id`.

**Response 404** — Image does not exist or is not owned by the caller.

---

### `GET /analyze/image/{image_id}`
Stream the original uploaded image for one of the caller's analyses (used to
re-display the image when re-opening a past analysis). Requires auth.

**Response 200** — the image file (`image/*`).

**Response 404** — Not owned, or the file is no longer on disk.

---

### `POST /analyze/{image_id}/ask`
Ask a grounded follow-up question about one of the caller's stored analyses. The
answer is grounded in that analysis's evidence + KB candidate styles (gated mode:
image-specific questions answered strictly from the analysis; general architecture
knowledge is allowed but flagged; off-topic questions are declined). Requires auth.
Stateless — the client sends prior turns in `history`.

**Request body (JSON)**
```json
{
  "question": "Why not Romanesque?",
  "history": [
    { "role": "user", "content": "What is the primary style?" },
    { "role": "assistant", "content": "Gothic, at 55%." }
  ],
  "lang": "vi"
}
```

**Response 200**
```json
{ "answer": "Vì phiếu bằng chứng ghi vòm nhọn và nhấn mạnh chiều đứng..." }
```

**Response 404** — Image not owned by the caller.

**Response 503** — Q&A not configured (`DEEPSEEK_API_KEY` missing).

---

## 5. Knowledge Endpoints

Read-only access to the architectural-style knowledge base (no DB, no LLM).
Both endpoints require auth.

### `GET /knowledge/style?name=<free-text>`
Resolve a free-text style name (exact → alias → fuzzy) to its knowledge card.

**Response 200**
```json
{
  "id": "gothic",
  "name": "Gothic",
  "aliases": ["Gothic Revival", "..."],
  "family_id": "medieval-european",
  "family_name": "Medieval European",
  "region": ["Western Europe"],
  "period": "1140-1500",
  "defining_features": ["pointed arches", "flying buttresses", "..."],
  "expected_profile": { "arch": "pointed", "...": "..." },
  "description": "...",
  "references": ["AAT", "Wikidata P149"],
  "aat_id": "TBD",
  "wikidata_id": "TBD",
  "siblings": [{ "id": "romanesque", "name": "Romanesque" }]
}
```

**Response 404** — No KB entry matches the name.

### `GET /knowledge/style/{style_id}`
Same card, looked up by exact KB id (used when navigating between sibling styles).
**Response 404** if the id is unknown.

---

## 6. JWT Token Structure

### Access Token Payload
```json
{
  "sub":        "google-sub-id-12345",
  "email":      "user@example.com",
  "name":       "Nguyen Van A",
  "token_type": "access",
  "exp":        1748000000
}
```

### Refresh Token Payload
```json
{
  "sub":        "google-sub-id-12345",
  "email":      "user@example.com",
  "name":       "Nguyen Van A",
  "token_type": "refresh",
  "exp":        1749000000
}
```

---

## 7. Error Response Format

All error responses follow FastAPI's default structure:
```json
{
  "detail": "Human-readable error message"
}
```

Validation errors (422) include a `loc` array identifying the failing field:
```json
{
  "detail": [
    {
      "loc": ["body", "file"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```
