# JBNHS catalog API

These read-only endpoints require a valid bearer token from Google Sign-In.
Their router and response schemas live in the service-specific
`src/jbnhs/` package.

- `GET /api/volumes` returns volumes with their issues and each issue's page
  count. Volumes are included even when they have no issues.
- `GET /api/volumes/{volume_id}/issues` returns issues for one volume, with
  their page counts.
- `GET /api/volumes/{volume_id}/issues/{issue_id}/pages` returns pages for an
  issue only when it belongs to the requested volume.
- `GET /api/issues/{issue_id}/pages` returns the issue's pages ordered by page
  number. A nonexistent issue returns `404`.

The page response includes page dimensions, QC status, and the source/OCR S3
keys for use by the QC client.
