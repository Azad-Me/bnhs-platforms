from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.common.constant import AccessLevel, QCState, FilePathsEnum
from services.common.models import Assignment, Issue, Page, Revision, User, Volume
from ..assignments.service import ACTIVE_ASSIGNMENT_STATUS
from .realignment import (
    RevisionDocumentError,
    normalize_ocr_document,
    realign_revision_document,
)
from .schemas import PageClaimState, PageRevisionRead, QCPageRead


SCAN_URL_TTL_SECONDS = 300
REVISION_CLAIM_TTL = timedelta(minutes=30)


async def get_page_volume_and_issue(
    page: Page,
) -> tuple[Volume, Issue]:
    """
        ocr/tesseract/V1/i1/p0001.json
    """
    ocr_s3_key = page.ocr_s3_key
    if not ocr_s3_key:
        raise PageNotFoundError("OCR s3 Key not found")
    
    page_source = ocr_s3_key.split("tesseract/")[-1]
    source = [part for part in page_source.split("/") if part]
    vol = source[0] if len(source) > 0 else "unknown"
    issue = source[1] if len(source) > 1 else "unknown"
    page_key = source[2] if len(source) > 2 else (source[-1] if source else "unknown")

    return vol, issue, page_key




class PageNotFoundError(LookupError):
    pass


class PageAssetUnavailableError(RuntimeError):
    pass


class PageAssetFormatError(RuntimeError):
    pass


class RevisionConflictError(ValueError):
    pass


class RevisionClaimRequiredError(ValueError):
    pass


class RevisionNotEditableError(ValueError):
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
    page_document = None
    if page.ocr_s3_key:
        try:
            page_document = normalize_ocr_document(
                _read_json_object(
                    s3_client, bucket=bucket, key=page.ocr_s3_key
                )
            )
        except RevisionDocumentError as error:
            raise PageAssetFormatError(str(error)) from error
        ocr_text = _extract_ocr_text(page_document)

    corrected_text = ocr_text or ""
    if revision is not None:
        revision_document = _read_json_object(
            s3_client, bucket=bucket, key=revision.s3_key
        )
        structured_document = _extract_revision_document(revision_document)
        if structured_document is not None:
            try:
                page_document = normalize_ocr_document(structured_document)
            except RevisionDocumentError as error:
                raise PageAssetFormatError(str(error)) from error
            corrected_text = _extract_ocr_text(page_document)
        else:
            corrected_text = _extract_revision_text(revision_document)
            page_document = None

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

    volume, issue, _ = await get_page_volume_and_issue( page)

    return QCPageRead(
        id=page.id,
        issue_id=page.issue_id,
        volume_code=volume,
        issue_code=issue,
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
        document=page_document,
    )


async def save_page_revision(
    session: AsyncSession,
    *,
    page_id: int,
    user: User,
    base_revision_id: int | None,
    submitted_document: dict[str, Any],
    s3_client: Any,
    bucket: str,
) -> PageRevisionRead:
    page = await session.scalar(
        select(Page).where(Page.id == page_id).with_for_update()
    )
    if page is None:
        raise PageNotFoundError("Page not found.")
    # if user.level.strip().casefold() != AccessLevel.QC_USER.value:
    #     raise RevisionNotEditableError("Only QC users can save page revisions.")
    if QCState(page.status) != QCState.IN_PROGRESS:
        raise RevisionNotEditableError(
            "The page must be claimed and in progress before saving a revision."
        )

    now = datetime.now(timezone.utc)
    assignment = await session.scalar(
        select(Assignment)
        .where(
            Assignment.page_id == page_id,
            Assignment.user_id == user.id,
            Assignment.status == ACTIVE_ASSIGNMENT_STATUS,
            Assignment.lock_expires_at > now,
        )
        .order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
        .with_for_update()
    )
    if assignment is None:
        raise RevisionClaimRequiredError(
            "An active page claim is required to save a revision."
        )

    latest_revision = await session.scalar(
        select(Revision)
        .where(
            Revision.page_id == page_id,
            Revision.saved_by == user.id,
        )
        .order_by(Revision.saved_at.desc(), Revision.id.desc())
        .limit(1)
    )
    expected_base_id = latest_revision.id if latest_revision else None
    if base_revision_id != expected_base_id:
        raise RevisionConflictError(
            "The base revision is stale. Reload the page before saving."
        )

    if latest_revision is not None:
        base_revision_document = _read_json_object(
            s3_client,
            bucket=bucket,
            key=latest_revision.s3_key,
        )
        base_document = _extract_revision_document(base_revision_document)
        if base_document is None:
            raise RevisionConflictError(
                "The latest revision has no structured word data and cannot "
                "be used as a realignment base."
            )
    else:
        if not page.ocr_s3_key:
            raise PageAssetFormatError("The page has no OCR document to revise.")
        base_document = _read_json_object(
            s3_client,
            bucket=bucket,
            key=page.ocr_s3_key,
        )

    aligned_document, warnings = realign_revision_document(
        base_document=base_document,
        submitted_document=submitted_document,
        page_width=page.width,
        page_height=page.height,
    )

    volume_key, issue_key, page_key = await get_page_volume_and_issue(page)
    revision_key = FilePathsEnum.get_revision_path(
        volume=volume_key,
        issue=issue_key,
        page_number=page_key,
        user_id=user.id,
    )
    revision = Revision(
        page_id=page_id,
        saved_by=user.id,
        based_on_revision_id=expected_base_id,
        s3_key=revision_key,
        saved_at=now,
    )
    session.add(revision)
    await session.flush()

    revision_document = {
        **aligned_document,
        "revision_id": revision.id,
        "based_on_revision_id": expected_base_id,
        "saved_by": user.id,
        "saved_at": now.isoformat(),
    }
    _write_json_object(
        s3_client,
        bucket=bucket,
        key=revision_key,
        document=revision_document,
    )
    assignment.lock_expires_at = now + REVISION_CLAIM_TTL

    return PageRevisionRead(
        id=revision.id,
        page_id=page_id,
        based_on_revision_id=expected_base_id,
        saved_at=now,
        document=aligned_document,
        realignment_warnings=warnings,
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
        rendered_lines.append(
            " ".join(word["t"] for word in words if word["t"])
        )
    return "\n".join(rendered_lines)


def _extract_revision_text(document: dict[str, Any]) -> str:
    corrected_text = document.get("corrected_text")
    if not isinstance(corrected_text, str):
        raise PageAssetFormatError(
            "The revision asset must contain corrected_text."
        )
    return corrected_text


def _extract_revision_document(
    document: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(document.get("lines"), list):
        return None
    return {
        key: value
        for key, value in document.items()
        if key not in {"revision_id", "based_on_revision_id", "saved_by", "saved_at"}
    }


def _write_json_object(
    s3_client: Any,
    *,
    bucket: str,
    key: str,
    document: dict[str, Any],
) -> None:
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(
                document,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
    except ClientError as error:
        raise PageAssetUnavailableError(
            "Unable to store the page revision."
        ) from error

