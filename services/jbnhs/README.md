# JBNHS APIs

These catalog read endpoints require a valid bearer token from Google Sign-In.
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
- `GET /api/pages/{page_id}/revisions` returns the role-scoped page history,
  including the OCR import baseline when available. QC users see their own
  revisions; Admins and Publishers see the common history.
- `GET /api/pages/{page_id}/revisions/{revision_id}` returns revision content.
  The `/compare` subroute returns a unified text diff against another revision
  or, when `against_revision_id` is omitted, the OCR baseline.
- `POST /api/pages/{page_id}/submit-review` lets the active QC claimant submit
  a saved revision for review and releases the claim.
- `POST /api/pages/{page_id}/review` lets Admins and Publishers send a page
  back with `{"decision":"send_back","note":"..."}` or approve/publish it with
  `{"decision":"approve"}`. Send-back notes are required.

The page response includes page dimensions, QC status, and the source/OCR S3
keys for use by the QC client. Each issue summary includes its source PDF S3 key.

## Check one approved page as a searchable PDF

From the repository root, run the standalone utility with the database page ID.
It reads the page's current approved revision and source scan from S3, then
writes a one-page PDF locally without changing either source asset:

```powershell
python -m services.jbnhs.src.stitching.stitch_page 10042 --output .\approved-page-10042.pdf
```

Pass `--text-mode visible` to draw the text and red word boxes over the scan for
alignment checking. The default `--text-mode invisible` creates the searchable
invisible text layer.

The database, AWS/S3, bucket, and font settings use the same environment
configuration as the API. If `--output` is omitted, the PDF is written to
`approved-page-<page_id>.pdf` in the current directory.

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
