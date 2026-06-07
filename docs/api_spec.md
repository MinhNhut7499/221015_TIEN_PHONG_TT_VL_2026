# API Specification

Base URL (development): `http://localhost:8000`  
All responses are `application/json` unless noted otherwise.  
Interactive docs: `GET /docs` (Swagger UI) · `GET /redoc` (ReDoc)

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
  "distribution_entropy": 0.94
}
```

Notes:
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
      "analysis_status": "completed",
      "uploaded_at": "2026-06-06T10:00:00+00:00",
      "style": "Gothic",
      "confidence": 0.62
    }
  ],
  "total": 1
}
```

---

## 5. JWT Token Structure

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

## 6. Error Response Format

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
