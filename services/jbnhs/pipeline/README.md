# JBNHS master-PDF ingestion

This pipeline lists every canonical master PDF under `derived/pdf/` in S3,
downloads each issue PDF in turn, renders its pages, runs Tesseract, writes
guide-format OCR JSON to S3, and upserts the page and issue manifest paths in
PostgreSQL. S3 listing uses pagination so the pipeline can process buckets with
more than one page of results.

The master PDF key must follow the volunteer guide layout:

```text
derived/pdf/V1/i1/i1.pdf
```

For that example the pipeline writes:

```text
ocr/tesseract/V1/i1/p0001.json
ocr/tesseract/V1/i1/p0002.json
ocr/tesseract/V1/i1/manifest.json
```

The `pages` rows store the original master-PDF key, per-page dimensions and DPI,
the exact OCR JSON key, and the S3 URI of the source PDF; `page_number` selects
the individual page. The `issues` row stores the manifest key. PDF page images
are rendered locally for OCR; the original S3 PDF is not changed. New pages
enter the `queued` status. Reprocessing an issue updates its source metadata and
OCR keys without resetting existing QC statuses.

Install dependencies and the Tesseract executable:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r services/jbnhs/pipeline/requirements.txt
```

The pipeline Dockerfile installs Tesseract and the Python dependencies. Configure
AWS credentials using the standard AWS credential chain (prefer an IAM role),
and set `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, and `DB_NAME`.
`S3_BUCKET` defaults to `bnhs-jbnhs-archive`; the region defaults to
`ap-south-1`.

Run from the repository root; no per-issue command-line arguments are needed:

```powershell
python -m services.jbnhs.pipeline.run
```

The batch scans `S3_MASTER_PDF_PREFIX` (default `derived/pdf/`) in
`S3_BUCKET` (default `bnhs-jbnhs-archive`). It uses standard AWS credentials
and requires `s3:ListBucket` for that prefix, read access to master PDFs, and
write access to OCR output keys. OCR settings can be adjusted with `OCR_DPI`,
`TESSERACT_LANGUAGE`, `TESSERACT_PSM`, and `OCR_CONFIDENCE_THRESHOLD`.

Run the pipeline tests with:

```powershell
python -m unittest services.jbnhs.pipeline.test_ingest
```

Issues are processed sequentially. A failure for one PDF is reported, and the
batch continues with the remaining PDFs; after processing, the run exits with an
error summary if any issues failed. The output writes are idempotent by S3 key
and `(issue_id, page_number)`. S3 writes happen before each database transaction;
on failure, rerunning the command safely replaces the same versioned output
keys. The pipeline does not delete source or output objects.
