from __future__ import annotations

import asyncio
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.constant import QCState, StitchTextMode
from ....common.models import ApprovedPage, Issue, Page, Revision, Volume


DEFAULT_PAGE_WIDTH_PT = 595.28
DOWNLOAD_URL_TTL_SECONDS = 900
FONT_NAME = "JBNHSUnicode"
FONT_PATHS = (
    os.environ.get("STITCH_FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


class StitchIssueNotFoundError(LookupError):
    pass


class StitchIssueNotReadyError(ValueError):
    pass


class StitchingError(RuntimeError):
    pass


@dataclass(frozen=True)
class StitchResult:
    issue_id: int
    page_count: int
    filename: str
    download_url: str
    download_url_expires_in: int
    text_mode: StitchTextMode


@dataclass(frozen=True)
class _PageAsset:
    page_number: int
    image_key: str
    revision_key: str


async def stitch_issue(
    session: AsyncSession,
    *,
    issue_id: int,
    s3_client: Any,
    bucket: str,
    text_mode: StitchTextMode = StitchTextMode.INVISIBLE,
) -> StitchResult:
    issue_row = (
        await session.execute(
            select(Issue, Volume.volume_code)
            .join(Volume, Volume.id == Issue.volume_id)
            .where(Issue.id == issue_id)
        )
    ).first()
    if issue_row is None:
        raise StitchIssueNotFoundError("Issue not found.")
    issue, volume_code = issue_row

    page_count = await session.scalar(
        select(func.count(Page.id)).where(Page.issue_id == issue_id)
    )
    if not page_count:
        raise StitchIssueNotReadyError("The issue has no pages to stitch.")

    approved_rows = (
        await session.execute(
            select(Page, ApprovedPage, Revision)
            .join(ApprovedPage, ApprovedPage.page_id == Page.id)
            .join(
                Revision,
                (Revision.id == ApprovedPage.revision_id)
                & (Revision.page_id == Page.id),
            )
            .where(Page.issue_id == issue_id)
            .order_by(Page.page_number, Page.id)
        )
    ).all()
    if len(approved_rows) != page_count:
        raise StitchIssueNotReadyError(
            "Every page in the issue must have an approved revision before stitching."
        )

    assets: list[_PageAsset] = []
    for page, approved_page, revision in approved_rows:
        if (
            page.status != QCState.COMPLETED.value
            or page.current_approved_revision_id != approved_page.revision_id
        ):
            raise StitchIssueNotReadyError(
                f"Page {page.page_number} is not in its approved state."
            )
        if not page.page_source_file:
            raise StitchingError(
                f"Page {page.page_number} has no source scan key."
            )
        assets.append(
            _PageAsset(
                page_number=page.page_number,
                image_key=page.page_source_file,
                revision_key=revision.s3_key,
            )
        )

    output_prefix = (
        os.environ.get("S3_STITCHED_PDF_PREFIX", "derived/searchable-pdf")
        .strip("/")
        or "derived/searchable-pdf"
    )
    object_key = (
        f"{output_prefix}/{_safe_key_part(volume_code)}/"
        f"{_safe_key_part(issue.issue_code)}/{text_mode.value}/"
        f"issue-{issue_id}-{uuid4().hex}.pdf"
    )
    filename = (
        f"volume-{_safe_key_part(volume_code)}-"
        f"issue-{_safe_key_part(issue.issue_code)}-{text_mode.value}.pdf"
    )

    try:
        download_url = await asyncio.to_thread(
            _render_upload_and_sign,
            s3_client=s3_client,
            bucket=bucket,
            assets=assets,
            object_key=object_key,
            volume_code=volume_code,
            issue_code=issue.issue_code,
            text_mode=text_mode,
        )
    except (BotoCoreError, ClientError) as error:
        raise StitchingError(
            "Unable to read the approved page assets or store the stitched PDF."
        ) from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise StitchingError(str(error)) from error

    return StitchResult(
        issue_id=issue_id,
        page_count=len(assets),
        filename=filename,
        download_url=download_url,
        download_url_expires_in=DOWNLOAD_URL_TTL_SECONDS,
        text_mode=text_mode,
    )


def _render_upload_and_sign(
    *,
    s3_client: Any,
    bucket: str,
    assets: list[_PageAsset],
    object_key: str,
    volume_code: str,
    issue_code: str,
    text_mode: StitchTextMode,
) -> str:
    with tempfile.TemporaryDirectory(prefix="bnhs-stitch-") as temp_dir:
        pdf_path = Path(temp_dir) / "stitched.pdf"
        _render_pdf_to_path(
            s3_client=s3_client,
            bucket=bucket,
            assets=assets,
            pdf_path=pdf_path,
            title=f"JBNHS volume {volume_code}, issue {issue_code}",
            text_mode=text_mode,
        )
        with pdf_path.open("rb") as pdf_file:
            s3_client.upload_fileobj(
                pdf_file,
                bucket,
                object_key,
                ExtraArgs={
                    "ContentType": "application/pdf",
                    "ContentDisposition": (
                        f'attachment; filename="volume-{_safe_key_part(volume_code)}-'
                        f'issue-{_safe_key_part(issue_code)}-{text_mode.value}.pdf"'
                    ),
                },
            )

    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=DOWNLOAD_URL_TTL_SECONDS,
    )


def render_approved_page_to_path(
    *,
    s3_client: Any,
    bucket: str,
    page_number: int,
    image_key: str,
    revision_key: str,
    output_path: str | Path,
    text_mode: StitchTextMode = StitchTextMode.INVISIBLE,
) -> Path:
    """Create a local, searchable PDF containing one approved page."""
    pdf_path = Path(output_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    _render_pdf_to_path(
        s3_client=s3_client,
        bucket=bucket,
        assets=[
            _PageAsset(
                page_number=page_number,
                image_key=image_key,
                revision_key=revision_key,
            )
        ],
        pdf_path=pdf_path,
        title=f"JBNHS approved page {page_number}",
        text_mode=text_mode,
    )
    return pdf_path


def _render_pdf_to_path(
    *,
    s3_client: Any,
    bucket: str,
    assets: list[_PageAsset],
    pdf_path: Path,
    title: str,
    text_mode: StitchTextMode,
) -> None:
    font_name = _register_font()
    pdf = Canvas(str(pdf_path), pageCompression=1)
    pdf.setTitle(title)
    pdf.setAuthor("BNHS Journal QC")

    for asset in assets:
        image_bytes = _read_s3_object(
            s3_client, bucket=bucket, key=asset.image_key
        )
        revision_bytes = _read_s3_object(
            s3_client, bucket=bucket, key=asset.revision_key
        )
        try:
            document = json.loads(revision_bytes.decode("utf-8"))
            with open("./revision.json","wb") as f:
                f.write(revision_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Approved revision for page {asset.page_number} is not valid UTF-8 JSON."
            ) from error
        if not isinstance(document, dict) or not isinstance(
            document.get("lines"), list
        ):
            raise ValueError(
                f"Approved revision for page {asset.page_number} has no lines list."
            )

        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            image_width, image_height = image.size
            if image_width <= 0 or image_height <= 0:
                raise ValueError(
                    f"Source scan for page {asset.page_number} has invalid dimensions."
                )
            scale = DEFAULT_PAGE_WIDTH_PT / image_width
            page_width_pt = image_width * scale
            page_height_pt = image_height * scale
            pdf.setPageSize((page_width_pt, page_height_pt))
            pdf.drawImage(
                ImageReader(image),
                0,
                0,
                width=page_width_pt,
                height=page_height_pt,
                preserveAspectRatio=False,
                mask="auto",
            )
            _draw_searchable_text(
                pdf,
                document["lines"],
                image_width=image_width,
                image_height=image_height,
                scale=scale,
                font_name=font_name,
                page_number=asset.page_number,
                text_mode=text_mode,
            )
            pdf.showPage()

    pdf.save()


def _draw_searchable_text(
    pdf: Canvas,
    lines: list[Any],
    *,
    image_width: int,
    image_height: int,
    scale: float,
    font_name: str,
    page_number: int,
    text_mode: StitchTextMode,
) -> None:
    for line_index, line in enumerate(lines, start=1):
        if not isinstance(line, dict) or not isinstance(line.get("words"), list):
            raise ValueError(
                f"Line {line_index} on page {page_number} has no words list."
            )
        for word_index, word in enumerate(line["words"], start=1):
            if not isinstance(word, dict) or not isinstance(word.get("t"), str):
                raise ValueError(
                    f"Word {word_index} in line {line_index} on page {page_number} is invalid."
                )
            text = word["t"]
            if not text:
                continue
            box = _validated_box(
                word.get("b"),
                image_width=image_width,
                image_height=image_height,
                label=f"Word {word_index} in line {line_index} on page {page_number}",
            )
            x0, y0, x1, y1 = box
            box_width = (x1 - x0) * scale
            box_height = (y1 - y0) * scale
            font_size = max(1.0, box_height * 0.8)
            ascent = pdfmetrics.getAscent(font_name) * font_size / 1000
            descent = pdfmetrics.getDescent(font_name) * font_size / 1000
            text_height = ascent - descent
            pdf_x = x0 * scale
            pdf_bottom = (image_height - y1) * scale
            baseline = pdf_bottom + (box_height - text_height) / 2 - descent
            natural_width = pdfmetrics.stringWidth(text, font_name, font_size)
            if natural_width <= 0:
                continue

            text_object = pdf.beginText()
            text_object.setTextOrigin(pdf_x, baseline)
            text_object.setFont(font_name, font_size)
            text_object.setHorizScale((box_width / natural_width) * 100)
            text_object.setTextRenderMode(
                0 if text_mode == StitchTextMode.VISIBLE else 3
            )
            text_object.textOut(text)
            if text_mode == StitchTextMode.VISIBLE:
                pdf.saveState()
                pdf.setStrokeColorRGB(0.9, 0.1, 0.1)
                pdf.setLineWidth(0.5)
                pdf.rect(
                    x0 * scale,
                    pdf_bottom,
                    box_width,
                    box_height,
                    stroke=1,
                    fill=0,
                )
                pdf.setFillColorRGB(0, 0.55, 0)
                pdf.drawText(text_object)
                confidence = word.get("c")
                if isinstance(confidence, (int, float)) and not isinstance(
                    confidence, bool
                ):
                    pdf.setFillColorRGB(0, 0.1, 0.9)
                    pdf.setFont(font_name, max(1, min(8, box_height * 0.25)))
                    pdf.drawString(
                        x0 * scale,
                        max(0, pdf_bottom - 7),
                        str(confidence),
                    )
                pdf.restoreState()
            else:
                pdf.drawText(text_object)


def _validated_box(
    value: Any,
    *,
    image_width: int,
    image_height: int,
    label: str,
) -> tuple[float, float, float, float]:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(
            not isinstance(coordinate, (int, float))
            or isinstance(coordinate, bool)
            or not math.isfinite(coordinate)
            for coordinate in value
        )
    ):
        raise ValueError(f"{label} has no valid bounding box.")
    x0, y0, x1, y1 = (float(coordinate) for coordinate in value)
    if (
        x0 < 0
        or y0 < 0
        or x1 <= x0
        or y1 <= y0
        or x1 > image_width
        or y1 > image_height
    ):
        raise ValueError(f"{label} bounding box is outside the source scan.")
    return x0, y0, x1, y1


def _read_s3_object(s3_client: Any, *, bucket: str, key: str) -> bytes:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    try:
        return body.read()
    finally:
        body.close()


def _register_font() -> str:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return FONT_NAME
    for font_path in FONT_PATHS:
        if font_path and Path(font_path).is_file():
            pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))
            return FONT_NAME
    raise FileNotFoundError(
        "No Unicode font was found. Set STITCH_FONT_PATH or install DejaVu Sans."
    )


def _safe_key_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return safe or "unknown"
