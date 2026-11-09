from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....common.cloud import S3Resource
from ....common.constant import QCState, StitchTextMode
from ....common.db.config import DatabaseSettings
from ....common.db.pool import DataBaseConnectionPool
from ....common.models import ApprovedPage, Page, Revision
from .stitch import render_approved_page_to_path


@dataclass(frozen=True)
class ApprovedPageSource:
    page_number: int
    revision_id: int
    image_key: str
    revision_key: str


async def _load_approved_page(
    session: AsyncSession,
    page_id: int,
) -> ApprovedPageSource:
    page = await session.get(Page, page_id)
    if page is None:
        raise ValueError(f"Page {page_id} was not found.")

    approved = await session.scalar(
        select(ApprovedPage).where(
            ApprovedPage.page_id == page_id
        )
    )
    if approved is None:
        raise ValueError(f"Page {page_id} has no approved revision.")
    if (
        page.status != QCState.COMPLETED.value
        or page.current_approved_revision_id != approved.revision_id
    ):
        raise ValueError(
            f"Page {page_id} is not in its current approved state."
        )

    revision = await session.get(Revision, approved.revision_id)
    if revision is None or revision.page_id != page_id:
        raise ValueError(f"Page {page_id} has an invalid approved revision link.")
    if not page.page_source_file:
        raise ValueError(f"Page {page_id} has no source scan key.")

    return ApprovedPageSource(
        page_number=page.page_number,
        revision_id=revision.id,
        image_key=page.page_source_file,
        revision_key=revision.s3_key,
    )


async def _run(
    page_id: int,
    output_path: Path,
    text_mode: StitchTextMode,
) -> None:
    pool = DataBaseConnectionPool(DatabaseSettings())
    try:
        async with pool.session() as session:
            source = await _load_approved_page(session, page_id)
    finally:
        await pool.close()

    s3_resource = S3Resource()
    try:
        bucket = os.environ.get("S3_BUCKET", "bnhs-jbnhs-archive")
        output = await asyncio.to_thread(
            render_approved_page_to_path,
            s3_client=s3_resource.client,
            bucket=bucket,
            page_number=source.page_number,
            image_key=source.image_key,
            revision_key=source.revision_key,
            output_path=output_path,
            text_mode=text_mode,
        )
    finally:
        s3_resource.close()

    print(f"Created {output.resolve()}")
    print(
        f"Page: {page_id}; approved revision: {source.revision_id}; "
        f"text mode: {text_mode.value}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create a one-page searchable PDF from the approved revision "
            "and original page scan."
        )
    )
    parser.add_argument("page_id", type=int, help="Database page ID")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output PDF path (default: approved-page-<page_id>.pdf)",
    )
    parser.add_argument(
        "--text-mode",
        choices=[mode.value for mode in StitchTextMode],
        default=StitchTextMode.INVISIBLE.value,
        help="Render text as invisible (searchable) or visible with red boxes.",
    )
    args = parser.parse_args()
    if args.page_id < 1:
        parser.error("page_id must be a positive integer")

    output_path = args.output or Path(f"approved-page-{args.page_id}.pdf")
    asyncio.run(
        _run(
            args.page_id,
            output_path,
            StitchTextMode(args.text_mode),
        )
    )


if __name__ == "__main__":
    main()
