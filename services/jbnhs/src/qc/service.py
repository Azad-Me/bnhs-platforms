from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.constant.qc_state_enum import QCState
from ....common.models import Assignment, Page, Revision
from ..assignments.service import ACTIVE_ASSIGNMENT_STATUS
from .schemas import PageClaimState, QCPageRead


SCAN_URL_TTL_SECONDS = 300


class PageNotFoundError(LookupError):
    pass


class PageAssetUnavailableError(RuntimeError):
    pass


class PageAssetFormatError(RuntimeError):
    pass


async def get_qc_page(
    session: AsyncSession,
    *,
    page_id: int,
    user_id: int,
    revision_owner_id: int | None,
    s3_client: Any,
    bucket: str,
) -> QCPageRead:
    page = await session.scalar(select(Page).where(Page.id == page_id))
    if page is None:
        raise PageNotFoundError("Page not found.")

    claim_state = await _get_claim_state(session, page.id, user_id)

    revision_query = select(Revision).where(Revision.page_id == page.id)
    if revision_owner_id is not None:
        revision_query = revision_query.where(
            Revision.saved_by == revision_owner_id
        )
    revision = await session.scalar(
        revision_query.order_by(Revision.saved_at.desc(), Revision.id.desc())
    )

    ocr_text = None
    if page.ocr_s3_key:
        ocr_document = _read_json_object(
            s3_client, bucket=bucket, key=page.ocr_s3_key
        )
        ocr_text = _extract_ocr_text(ocr_document)

    corrected_text = ocr_text or ""
    if revision is not None:
        revision_document = _read_json_object(
            s3_client, bucket=bucket, key=revision.s3_key
        )
        corrected_text = _extract_revision_text(revision_document)

    try:
        scan_url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": page.page_source_file},
            ExpiresIn=SCAN_URL_TTL_SECONDS,
        )
    except ClientError as error:
        raise PageAssetUnavailableError(
            "Unable to create an authorized page-scan URL."
        ) from error

    return QCPageRead(
        id=page.id,
        issue_id=page.issue_id,
        page_number=page.page_number,
        status=QCState(page.status),
        is_check_page=page.is_check_page,
        ocr_text=ocr_text,
        corrected_text=corrected_text,
        current_revision_id=revision.id if revision else None,
        revision_saved_at=revision.saved_at if revision else None,
        scan_url=scan_url,
        scan_url_expires_in=SCAN_URL_TTL_SECONDS,
        claim=claim_state,
    )


async def _get_claim_state(
    session: AsyncSession,
    page_id: int,
    user_id: int,
) -> PageClaimState:
    now = datetime.now(timezone.utc)
    result = await session.scalars(
        select(Assignment)
        .where(
            Assignment.page_id == page_id,
            Assignment.status == ACTIVE_ASSIGNMENT_STATUS,
            Assignment.lock_expires_at > now,
        )
        .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
    )
    active = next(iter(result), None)
    return PageClaimState(
        is_claimed=active is not None,
        claimed_by_me=active is not None and active.user_id == user_id,
        lock_expires_at=active.lock_expires_at if active is not None else None,
    )


def _read_json_object(s3_client: Any, *, bucket: str, key: str) -> dict[str, Any]:
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
    except (ClientError, KeyError) as error:
        raise PageAssetUnavailableError(
            "Unable to read a required page asset."
        ) from error
    try:
        raw_body = body.read()
    finally:
        body.close()

    try:
        document = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PageAssetFormatError(
            f"Page asset {key} is not valid UTF-8 JSON."
        ) from error
    if not isinstance(document, dict):
        raise PageAssetFormatError(f"Page asset {key} must contain a JSON object.")
    return document


def _extract_ocr_text(document: dict[str, Any]) -> str:
    lines = document.get("lines")
    if not isinstance(lines, list):
        raise PageAssetFormatError("The OCR asset does not contain a lines list.")

    rendered_lines: list[str] = []
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get("words"), list):
            raise PageAssetFormatError("The OCR asset contains an invalid line.")
        words = line["words"]
        if any(
            not isinstance(word, dict)
            or not isinstance(word.get("t"), str)
            for word in words
        ):
            raise PageAssetFormatError("The OCR asset contains an invalid word.")
        rendered_lines.append(" ".join(word["t"] for word in words))
    return "\n".join(rendered_lines)


def _extract_revision_text(document: dict[str, Any]) -> str:
    corrected_text = document.get("corrected_text")
    if not isinstance(corrected_text, str):
        raise PageAssetFormatError(
            "The revision asset must contain corrected_text."
        )
    return corrected_text
