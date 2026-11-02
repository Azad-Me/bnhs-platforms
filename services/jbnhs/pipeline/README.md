# JBNHS master-PDF ingestion

This pipeline lists every canonical master PDF under `derived/pdf/` in S3,
downloads each issue PDF in turn, renders its pages, uploads page JPEGs and
guide-format OCR JSON, and upserts their S3 paths and issue manifest in
PostgreSQL. S3 listing uses pagination so the pipeline can process buckets with
more than one page of results.

The master PDF key must follow the volunteer guide layout:

```text
derived/pdf/V1/i1/i1.pdf
```

For that example the pipeline writes:

```text
issues/v1/i1/p1.jpeg
issues/v1/i1/p2.jpeg
ocr/tesseract/V1/i1/p0001.json
ocr/tesseract/V1/i1/p0002.json
ocr/tesseract/V1/i1/manifest.json
```

The `issues` row stores the original master-PDF key and manifest key. Each
`pages` row stores the rendered JPEG key, OCR JSON key, and page dimensions;
`page_number` selects the individual page. Images are JPEG-encoded at quality
90 and uploaded as `image/jpeg`. The original S3 PDF is not changed. New pages
enter the `queued` status. Reprocessing an issue overwrites the same JPEG/OCR
keys without resetting existing QC statuses.

Install dependencies and the Tesseract executable:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r services/jbnhs/pipeline/requirements.txt
```

On Windows, if Tesseract is installed outside `PATH`, set `TESSERACT_CMD` to
the full path to `tesseract.exe` (for example,
`C:\Program Files\Tesseract-OCR\tesseract.exe`). The Python pipeline uses this
setting when invoking Tesseract.

The pipeline Dockerfile installs Tesseract and the Python dependencies. Configure
AWS credentials using the standard AWS credential chain (prefer an IAM role),
and set `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, and `DB_NAME`.
`S3_BUCKET` defaults to `bnhs-jbnhs-archive`; the region defaults to
`ap-south-1`.

Build the dedicated pipeline image from the repository root (the build context
must be the repository root so both dependency files and the `services` package
are available):

```powershell
docker build -f services/jbnhs/pipeline/Dockerfile -t bnhs-jbnhs-pipeline .
docker run --rm --env-file .env bnhs-jbnhs-pipeline
```

The `.env` file is not copied into the image. Provide AWS credentials to the
container through an IAM role or another secure AWS credential-chain method.

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
