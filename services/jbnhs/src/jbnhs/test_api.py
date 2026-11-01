from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException

from .api import (
    list_issue_pages,
    list_volume_issue_pages,
    list_volume_issues,
    list_volumes_with_issues,
)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class CatalogApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_volumes_groups_issues_and_page_counts(self):
        created_at = datetime.now(timezone.utc)
        rows = [
            SimpleNamespace(
                volume_id=1000,
                volume_code="V1",
                volume_created_at=created_at,
                issue_id=1001,
                issue_code="i1",
                manifest_s3_key="ocr/V1/i1/manifest.json",
                page_count=3,
            ),
            SimpleNamespace(
                volume_id=1000,
                volume_code="V1",
                volume_created_at=created_at,
                issue_id=1002,
                issue_code="i2",
                manifest_s3_key=None,
                page_count=0,
            ),
            SimpleNamespace(
                volume_id=1003,
                volume_code="V2",
                volume_created_at=created_at,
                issue_id=None,
                issue_code=None,
                manifest_s3_key=None,
                page_count=0,
            ),
        ]

        class FakeSession:
            async def execute(self, statement):
                return FakeResult(rows)

        volumes = await list_volumes_with_issues(FakeSession(), None)
        self.assertEqual([volume.volume_code for volume in volumes], ["V1", "V2"])
        self.assertEqual(
            [(issue.issue_code, issue.page_count) for issue in volumes[0].issues],
            [("i1", 3), ("i2", 0)],
        )
        self.assertEqual(volumes[1].issues, [])

    async def test_list_issue_pages_returns_pages_in_page_number_order(self):
        timestamp = datetime.now(timezone.utc)
        pages = [
            SimpleNamespace(
                id=10002,
                issue_id=1001,
                page_number=2,
                source_file="s3://bucket/issue.pdf",
                width=2400,
                height=3400,
                dpi=300,
                master_pdf_s3_key="derived/pdf/V1/i1/i1.pdf",
                toned_pdf_s3_key=None,
                ocr_s3_key="ocr/V1/i1/p0002.json",
                status="queued",
                is_check_page=False,
                current_approved_revision_id=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
            SimpleNamespace(
                id=10001,
                issue_id=1001,
                page_number=1,
                source_file="s3://bucket/issue.pdf",
                width=2400,
                height=3400,
                dpi=300,
                master_pdf_s3_key="derived/pdf/V1/i1/i1.pdf",
                toned_pdf_s3_key=None,
                ocr_s3_key="ocr/V1/i1/p0001.json",
                status="queued",
                is_check_page=False,
                current_approved_revision_id=None,
                created_at=timestamp,
                updated_at=timestamp,
            ),
        ]

        class FakeSession:
            async def scalar(self, statement):
                return 1001

            async def scalars(self, statement):
                return sorted(pages, key=lambda page: page.page_number)

        result = await list_issue_pages(1001, FakeSession(), None)
        self.assertEqual([page.page_number for page in result], [1, 2])
        self.assertEqual(result[0].ocr_s3_key, "ocr/V1/i1/p0001.json")

    async def test_list_issue_pages_returns_404_for_missing_issue(self):
        class FakeSession:
            async def scalar(self, statement):
                return None

        with self.assertRaises(HTTPException) as error:
            await list_issue_pages(404, FakeSession(), None)
        self.assertEqual(error.exception.status_code, 404)

    async def test_list_volume_issues_returns_issue_summaries(self):
        rows = [
            SimpleNamespace(
                issue_id=1001,
                issue_code="i1",
                manifest_s3_key="ocr/V1/i1/manifest.json",
                page_count=24,
            ),
        ]

        class FakeSession:
            async def scalar(self, statement):
                return 1000

            async def execute(self, statement):
                return FakeResult(rows)

        issues = await list_volume_issues(1000, FakeSession(), None)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_code, "i1")
        self.assertEqual(issues[0].page_count, 24)

    async def test_list_volume_issues_returns_404_for_missing_volume(self):
        class FakeSession:
            async def scalar(self, statement):
                return None

        with self.assertRaises(HTTPException) as error:
            await list_volume_issues(404, FakeSession(), None)
        self.assertEqual(error.exception.status_code, 404)

    async def test_nested_pages_require_issue_belongs_to_volume(self):
        class FakeSession:
            async def scalar(self, statement):
                return None

        with self.assertRaises(HTTPException) as error:
            await list_volume_issue_pages(1000, 1001, FakeSession(), None)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "Issue not found in this volume.")

    async def test_nested_pages_return_pages_for_matching_issue(self):
        timestamp = datetime.now(timezone.utc)
        page = SimpleNamespace(
            id=10001,
            issue_id=1001,
            page_number=1,
            source_file="s3://bucket/issue.pdf",
            width=2400,
            height=3400,
            dpi=300,
            master_pdf_s3_key="derived/pdf/V1/i1/i1.pdf",
            toned_pdf_s3_key=None,
            ocr_s3_key="ocr/V1/i1/p0001.json",
            status="queued",
            is_check_page=False,
            current_approved_revision_id=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

        class FakeSession:
            async def scalar(self, statement):
                return 1001

            async def scalars(self, statement):
                return [page]

        pages = await list_volume_issue_pages(1000, 1001, FakeSession(), None)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].issue_id, 1001)
        self.assertEqual(pages[0].page_number, 1)


if __name__ == "__main__":
    unittest.main()
