from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...common.constant.qc_state_enum import QCState
from ...common.db.pool import DataBaseConnectionPool
from ...common.models import Issue, Page, Volume


_MASTER_PDF_KEY = re.compile(
    r"^derived/pdf/(?P<volume>V[^/]+)/(?P<issue>i[^/]+)/(?P<filename>[^/]+\.pdf)$"
)
MASTER_PDF_PREFIX = "derived/pdf/"


@dataclass(frozen=True)
class IngestionResult:
    volume_code: str
    issue_code: str
    page_count: int
    manifest_s3_key: str
    ocr_s3_prefix: str


class BatchIngestionError(RuntimeError):
    def __init__(
        self,
        failures: list[tuple[str, Exception]],
        completed: list[IngestionResult],
    ) -> None:
        self.failures = failures
        self.completed = completed
        details = "; ".join(f"{key}: {error}" for key, error in failures)
        super().__init__(
            f"{len(failures)} of {len(failures) + len(completed)} "
            f"master PDFs failed ingestion: {details}"
        )


def list_master_pdf_keys(
    *,
    s3_client: Any,
    bucket: str,
    prefix: str = MASTER_PDF_PREFIX,
) -> list[str]:
    """List every PDF below the canonical master-PDF prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = {
        item["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for item in page.get("Contents", [])
        if item.get("Key", "").lower().endswith(".pdf")
    }
    return sorted(keys)


def parse_master_pdf_key(s3_key: str) -> tuple[str, str]:
    """Return volume and issue codes from the guide's canonical master-PDF key."""
    match = _MASTER_PDF_KEY.fullmatch(s3_key)
    if match is None:
        raise ValueError(
            "Expected an S3 key like derived/pdf/V1/i1/i1.pdf; "
            f"received {s3_key!r}."
        )

    volume_code = match.group("volume")
    issue_code = match.group("issue")
    if match.group("filename") != f"{issue_code}.pdf":
        raise ValueError(
            f"The PDF filename must match its issue folder ({issue_code}.pdf)."
        )

    return volume_code, issue_code


def page_ocr_s3_key(volume_code: str, issue_code: str, page_number: int) -> str:
    if page_number < 1:
        raise ValueError("Page numbers must start at 1.")
    return f"ocr/tesseract/{volume_code}/{issue_code}/p{page_number:04d}.json"


def issue_manifest_s3_key(volume_code: str, issue_code: str) -> str:
    return f"ocr/tesseract/{volume_code}/{issue_code}/manifest.json"


def page_image_s3_key(volume_code: str, issue_code: str, page_number: int) -> str:
    if page_number < 1:
        raise ValueError("Page numbers must start at 1.")
    return (
        f"issues/{volume_code.lower()}/{issue_code.lower()}/"
        f"p{page_number}.jpeg"
    )


def build_page_ocr_document(
    *,
    page_number: int,
    source_file: str,
    width: int,
    height: int,
    dpi: int,
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert OCR line geometry to the page JSON format in the volunteer guide."""
    output_lines = []
    for line_number, line in enumerate(lines, start=1):
        bbox = line["bbox"]
        output_lines.append(
            {
                "id": f"l{line_number}",
                "b": [bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]],
                "words": [
                    {
                        "id": f"w{word_number}",
                        "t": word["text"],
                        "b": [
                            word["bbox"]["x1"],
                            word["bbox"]["y1"],
                            word["bbox"]["x2"],
                            word["bbox"]["y2"],
                        ],
                        "c": word["confidence"],
                    }
                    for word_number, word in enumerate(
                        line["words"],
                        start=1,
                    )
                ],
            }
        )

    return {
        "page": page_number,
        "source_file": source_file,
        "source_page": page_number,
        "width": width,
        "height": height,
        "dpi": dpi,
        "engine": "tesseract",
        "lines": output_lines,
    }


def classify_page_image(image: Any) -> str:
    """Classify a rendered page as bitonal, gray, or color for the manifest."""
    import cv2
    import numpy as np

    sample = image[::8, ::8]
    channel_range = sample.max(axis=2).astype(np.int16) - sample.min(axis=2)
    if np.mean(channel_range > 8) > 0.01:
        return "color"

    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    if np.unique(gray).size <= 2:
        return "bitonal"
    return "gray"


def _extract_ocr_lines(
    image: Any,
    *,
    language: str,
    psm: int,
    confidence_threshold: float,
) -> list[dict[str, Any]]:
    from .process_extraction import extract_ocr_data, group_words_into_lines

    words, _ = extract_ocr_data(image, language=language, psm=psm)
    return group_words_into_lines(
        words,
        confidence_threshold=confidence_threshold,
    )


def _page_manifest_entry(
    *,
    page_number: int,
    source_file: str,
    image_storage: str,
    document: dict[str, Any],
    confidence_threshold: float,
) -> dict[str, Any]:
    words = [
        word for line in document["lines"] for word in line["words"]
    ]
    return {
        "page": page_number,
        "source_file": source_file,
        "image_storage": image_storage,
        "line_count": len(document["lines"]),
        "word_count": len(words),
        "low_confidence_words": sum(
            word["c"] < confidence_threshold for word in words
        ),
    }


async def _save_issue_metadata(
    session: AsyncSession,
    *,
    toned_pdf_s3_key: str | None,
    volume_code: str,
    issue_code: str,
    manifest_s3_key: str,
    page_entries: list[dict[str, Any]],
) -> None:
    volume = await session.scalar(
        select(Volume).where(Volume.volume_code == volume_code)
    )
    if volume is None:
        volume = Volume(volume_code=volume_code)
        session.add(volume)
        await session.flush()

    issue_matches = (
        await session.scalars(
            select(Issue).where(
                Issue.volume_id == volume.id,
                Issue.issue_code == issue_code,
            )
        )
    ).all()
    if len(issue_matches) > 1:
        raise RuntimeError(
            f"Multiple issue records exist for {volume_code}/{issue_code}."
        )

    issue = issue_matches[0] if issue_matches else Issue(
        volume_id=volume.id,
        issue_code=issue_code,
    )
    if not issue_matches:
        session.add(issue)
        await session.flush()

    if toned_pdf_s3_key is not None:
        issue.toned_pdf_s3_key = toned_pdf_s3_key
    issue.manifest_s3_key = manifest_s3_key
    existing_pages = (
        await session.scalars(select(Page).where(Page.issue_id == issue.id))
    ).all()
    pages_by_number = {page.page_number: page for page in existing_pages}

    for entry in page_entries:
        page_number = entry["page"]
        page = pages_by_number.get(page_number)
        if page is None:
            page = Page(
                issue_id=issue.id,
                page_number=page_number,
                page_source_file=entry["image_s3_key"],
                status=QCState.UNVERIFIED.value,
            )
            session.add(page)

        page.width = entry["width"]
        page.height = entry["height"]
        page.dpi = entry["dpi"]
        page.ocr_s3_key = entry["ocr_s3_key"]


async def ingest_local_pdf(
    *,
    pdf_path: Path,
    s3_client: Any,
    db_pool: DataBaseConnectionPool,
    bucket: str,
    master_pdf_s3_key: str,
    toned_pdf_s3_key: str | None = None,
    dpi: int = 300,
    language: str = "eng",
    psm: int = 3,
    confidence_threshold: float = 0.6,
) -> IngestionResult:
    """Render, OCR, upload, and register a downloaded master issue PDF."""
    import cv2
    import pymupdf
    import numpy as np

    if dpi <= 0:
        raise ValueError("DPI must be greater than zero.")
    if psm <= 0:
        raise ValueError("Tesseract PSM must be greater than zero.")
    if not 0 <= confidence_threshold <= 1:
        raise ValueError("Confidence threshold must be between 0 and 1.")

    volume_code, issue_code = parse_master_pdf_key(master_pdf_s3_key)
    manifest_key = issue_manifest_s3_key(volume_code, issue_code)

    source_file = PurePosixPath(master_pdf_s3_key).name
    page_entries: list[dict[str, Any]] = []

    with pymupdf.open(pdf_path) as document:
        if document.is_encrypted:
            raise ValueError(f"Encrypted PDFs are not supported: {master_pdf_s3_key}")
        if document.page_count == 0:
            raise ValueError(f"The PDF contains no pages: {master_pdf_s3_key}")

        total_pages = document.page_count
        print(
            f"Processing {master_pdf_s3_key}: {total_pages} pages.",
            flush=True,
        )
        scale = dpi / 72
        matrix = pymupdf.Matrix(scale, scale)

        for page_number, pdf_page in enumerate(document, start=1):
            print(
                f"  [{volume_code}/{issue_code}] "
                f"Page {page_number}/{total_pages}: rendering and OCR...",
                flush=True,
            )
            pixmap = pdf_page.get_pixmap(
                matrix=matrix,
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
            image_bytes = pixmap.tobytes("png")
            image = cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if image is None:
                raise RuntimeError(
                    f"Unable to decode rendered page {page_number} "
                    f"from {master_pdf_s3_key}."
                )

            height, width = image.shape[:2]
            image_key = page_image_s3_key(
                volume_code,
                issue_code,
                page_number,
            )
            encoded_successfully, jpeg_bytes = cv2.imencode(
                ".jpeg",
                image,
                [cv2.IMWRITE_JPEG_QUALITY, 90],
            )
            if not encoded_successfully:
                raise RuntimeError(
                    f"Unable to encode page {page_number} as JPEG "
                    f"from {master_pdf_s3_key}."
                )
            s3_client.put_object(
                Bucket=bucket,
                Key=image_key,
                Body=jpeg_bytes.tobytes(),
                ContentType="image/jpeg",
            )

            lines = _extract_ocr_lines(
                image,
                language=language,
                psm=psm,
                confidence_threshold=confidence_threshold,
            )
            page_document = build_page_ocr_document(
                page_number=page_number,
                source_file=source_file,
                width=width,
                height=height,
                dpi=dpi,
                lines=lines,
            )
            page_key = page_ocr_s3_key(volume_code, issue_code, page_number)
            s3_client.put_object(
                Bucket=bucket,
                Key=page_key,
                Body=json.dumps(
                    page_document, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
            page_entries.append(
                {
                    **_page_manifest_entry(
                        page_number=page_number,
                        source_file=source_file,
                        image_storage=classify_page_image(image),
                        document=page_document,
                        confidence_threshold=confidence_threshold,
                    ),
                    "width": width,
                    "height": height,
                    "dpi": dpi,
                    "image_s3_key": image_key,
                    "ocr_s3_key": page_key,
                }
            )
            print(
                f"  [{volume_code}/{issue_code}] "
                f"Page {page_number}/{total_pages} complete "
                f"({len(lines)} lines).",
                flush=True,
            )

    manifest = {
        "volume": volume_code,
        "issue": issue_code,
        "source_pdf": master_pdf_s3_key,
        "engine": "tesseract",
        "page_count": len(page_entries),
        "pages": [
            {
                key: value
                for key, value in entry.items()
                if key not in {"width", "height", "dpi", "ocr_s3_key"}
            }
            for entry in page_entries
        ],
    }
    s3_client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json; charset=utf-8",
    )

    async with db_pool.session() as session:
        async with session.begin():
            await _save_issue_metadata(
                session,
                toned_pdf_s3_key=toned_pdf_s3_key,
                volume_code=volume_code,
                issue_code=issue_code,
                manifest_s3_key=manifest_key,
                page_entries=page_entries,
            )

    return IngestionResult(
        volume_code=volume_code,
        issue_code=issue_code,
        page_count=len(page_entries),
        manifest_s3_key=manifest_key,
        ocr_s3_prefix=f"ocr/tesseract/{volume_code}/{issue_code}/",
    )


async def ingest_s3_pdf(
    *,
    s3_client: Any,
    db_pool: DataBaseConnectionPool,
    bucket: str,
    master_pdf_s3_key: str,
    toned_pdf_s3_key: str | None = None,
    dpi: int = 300,
    language: str = "eng",
    psm: int = 3,
    confidence_threshold: float = 0.6,
) -> IngestionResult:
    """Download a canonical master PDF from S3 and run the ingestion pipeline."""
    parse_master_pdf_key(master_pdf_s3_key)
    with tempfile.TemporaryDirectory(prefix="jbnhs-ingest-") as temp_dir:
        pdf_path = Path(temp_dir) / PurePosixPath(master_pdf_s3_key).name
        s3_client.download_file(bucket, master_pdf_s3_key, str(pdf_path))
        return await ingest_local_pdf(
            pdf_path=pdf_path,
            s3_client=s3_client,
            db_pool=db_pool,
            bucket=bucket,
            master_pdf_s3_key=master_pdf_s3_key,
            toned_pdf_s3_key=toned_pdf_s3_key,
            dpi=dpi,
            language=language,
            psm=psm,
            confidence_threshold=confidence_threshold,
        )


async def ingest_all_s3_pdfs(
    *,
    s3_client: Any,
    db_pool: DataBaseConnectionPool,
    bucket: str,
    prefix: str = MASTER_PDF_PREFIX,
    toned_pdf_s3_keys: dict[str, str] | None = None,
    dpi: int = 300,
    language: str = "eng",
    psm: int = 3,
    confidence_threshold: float = 0.6,
) -> list[IngestionResult]:
    """Ingest every master PDF under the configured S3 prefix."""
    keys = list_master_pdf_keys(
        s3_client=s3_client,
        bucket=bucket,
        prefix=prefix,
    )
    print(
        f"Found {len(keys)} master PDF(s) under s3://{bucket}/{prefix}.",
        flush=True,
    )
    completed: list[IngestionResult] = []
    failures: list[tuple[str, Exception]] = []

    for index, key in enumerate(keys, start=1):
        print(
            f"[{index}/{len(keys)}] Downloading {key}...",
            flush=True,
        )
        try:
            result = await ingest_s3_pdf(
                s3_client=s3_client,
                db_pool=db_pool,
                bucket=bucket,
                master_pdf_s3_key=key,
                toned_pdf_s3_key=(toned_pdf_s3_keys or {}).get(key),
                dpi=dpi,
                language=language,
                psm=psm,
                confidence_threshold=confidence_threshold,
            )
        except Exception as error:
            print(f"Failed {key}: {error!r}", flush=True)
            failures.append((key, error))
        else:
            completed.append(result)

    if failures:
        raise BatchIngestionError(failures, completed)

    return completed
