# JBNHS catalog API

These read-only endpoints require a valid bearer token from Google Sign-In.
The catalog uses three layers under `src/catalog/`: `api.py` handles HTTP,
authentication, and response envelopes; `schemas.py` defines API data models;
and `service.py` owns database queries and result assembly. ORM entities remain
in `services/common/models/`.

- `GET /api/volumes` returns volumes with their issues and each issue's page
  count. Volumes are included even when they have no issues.
- `GET /api/volumes/{volume_id}/issues` returns issues for one volume, with
  their page counts.
- `GET /api/volumes/{volume_id}/issues/{issue_id}/pages` returns pages for an
  issue only when it belongs to the requested volume.
- `GET /api/issues/{issue_id}/pages` returns the issue's pages ordered by page
  number. A nonexistent issue returns `404`.

The page response includes page dimensions, QC status, and the source/OCR S3
keys for use by the QC client. Each issue summary includes its source PDF S3 key.

## API container

Build the API image from the repository root and pass environment settings at
runtime; `.env` is intentionally excluded from the image:

```powershell
docker build -t bnhs-api .
docker run --rm --env-file .env -p 8000:8000 bnhs-api
```

Set `CORS_ALLOWED_ORIGINS` to a comma-separated list of exact frontend origins
(for example, `http://localhost:3000,http://localhost:5173`). Wildcard origins
are rejected; bearer-token requests do not use cookie credentials.
