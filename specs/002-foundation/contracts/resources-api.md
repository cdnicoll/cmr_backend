# Resources API Contract

**Base path**: `/api/v1/resources`  
**Auth**: JWT required (`Authorization: Bearer <token>`)

---

## POST /api/v1/resources

Batch create resources from URLs. Each URL is validated (SSRF, format, type). Duplicates are skipped; new resources are inserted with `pipeline_stage = discovered`.

**Request**:

```json
{
  "urls": [
    "https://example.com/article-1",
    "https://www.youtube.com/watch?v=abc123",
    "https://example.com/article-1"
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| urls | array of string | Yes | 1..N URLs to process |

**Response**: `201 Created` (if any created) or `200 OK` (if all skipped)

```json
{
  "created": 2,
  "skipped": 1,
  "errors": 0,
  "results": [
    {
      "url": "https://example.com/article-1",
      "status": "created",
      "resource_id": "uuid",
      "error": null
    },
    {
      "url": "https://www.youtube.com/watch?v=abc123",
      "status": "created",
      "resource_id": "uuid",
      "error": null
    },
    {
      "url": "https://example.com/article-1",
      "status": "skipped",
      "resource_id": "uuid",
      "error": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| created | int | Count of new resources inserted |
| skipped | int | Count of duplicates skipped |
| errors | int | Count of validation failures |
| results | array | Per-URL result objects |

**ResourceResult**:
| Field | Type | Description |
|-------|------|-------------|
| url | string | The URL that was processed |
| status | string | `created` \| `skipped` \| `error` |
| resource_id | UUID \| null | Present when created or skipped |
| error | string \| null | Error message when status=error |

**Errors**:
- `400 Bad Request` — Empty `urls` array or invalid JSON
- `401 Unauthorized` — Missing or invalid JWT
- `422 Unprocessable Entity` — Individual URL validation failures (e.g. SSRF, malformed). When all URLs fail validation, response may still be 200/201 with `errors` count and per-result `error` messages.

**Validation failures** (per-URL, do not fail batch):
- SSRF: internal IP, localhost, private range
- Malformed URL
- Invalid YouTube format (when detected as YouTube)
- Unsupported scheme (e.g. `file://`)

---

## Auth

All Resources endpoints require a valid Supabase JWT. Use `get_validated_jwt_user` or `get_current_user` per starter-kit. Unauthenticated requests receive `401` with `WWW-Authenticate: Bearer`.

---

## Phase 1 Scope

- **In scope**: `POST /api/v1/resources` (batch create only)
- **Out of scope**: `GET /api/v1/resources`, `GET /api/v1/resources/{id}`, `PATCH`, `DELETE` — future phases or separate spec
