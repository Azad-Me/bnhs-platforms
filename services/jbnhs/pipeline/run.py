from __future__ import annotations

import asyncio
import os

from ...common.cloud import S3Resource
from ...common.db import DataBaseConnectionPool
from .ingest import BatchIngestionError, IngestionResult, ingest_all_s3_pdfs


async def run_pipeline() -> None:
    bucket = os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive")
    prefix = os.environ.get("S3_MASTER_PDF_PREFIX", "derived/pdf/")
    region = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "ap-south-1"
    )
    dpi = int(os.environ.get("OCR_DPI", "300"))
    language = os.environ.get("TESSERACT_LANGUAGE", "eng")
    psm = int(os.environ.get("TESSERACT_PSM", "3"))
    confidence_threshold = float(
        os.environ.get("OCR_CONFIDENCE_THRESHOLD", "0.6")
    )
    if dpi <= 0:
        raise ValueError("OCR_DPI must be greater than zero.")
    if psm <= 0:
        raise ValueError("TESSERACT_PSM must be greater than zero.")
    if not 0 <= confidence_threshold <= 1:
        raise ValueError("OCR_CONFIDENCE_THRESHOLD must be between 0 and 1.")

    s3_resource = S3Resource(region_name=region)
    pool = DataBaseConnectionPool()
    try:
        await pool.ping()
        try:
            results = await ingest_all_s3_pdfs(
                s3_client=s3_resource.client,
                db_pool=pool,
                bucket=bucket,
                prefix=prefix,
                dpi=dpi,
                language=language,
                psm=psm,
                confidence_threshold=confidence_threshold,
            )
        except BatchIngestionError as error:
            for result in error.completed:
                _print_result(bucket, result)
            for key, failure in error.failures:
                print(f"Failed {key}: {failure}")
            raise

        if not results:
            print(f"No master PDFs found in s3://{bucket}/{prefix}")
            return

        for result in results:
            _print_result(bucket, result)
        print(f"Completed ingestion for {len(results)} master PDFs.")
    finally:
        try:
            await pool.close()
        finally:
            s3_resource.close()


def _print_result(bucket: str, result: IngestionResult) -> None:
    print(
        f"Ingested {result.volume_code}/{result.issue_code}: "
        f"{result.page_count} pages; manifest "
        f"s3://{bucket}/{result.manifest_s3_key}"
    )


def main() -> None:
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()