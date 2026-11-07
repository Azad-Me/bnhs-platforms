from __future__ import annotations

import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from ....common.constant.qc_state_enum import QCState
from .realignment import (
    RevisionDocumentError,
    normalize_ocr_document,
    realign_revision_document,
)
from .service import (
    RevisionClaimRequiredError,
    RevisionConflictError,
    save_page_revision,
)


def _sample_document():
    return {
        "page": 1,
        "width": 500,
        "height": 200,
        "lines": [
            {
                "id": "l1",
                "b": [10, 20, 200, 40],
                "words": [
                    {"id": "w1", "t": "The", "b": [10, 20, 35, 40], "c": 0.9},
                    {"id": "w2", "t": "bird", "b": [55, 20, 90, 40], "c": 0.8},
                ],
            },
            {
                "id": "l2",
                "b": [10, 60, 200, 80],
                "words": [
                    {"id": "w1", "t": "flies", "b": [10, 60, 60, 80], "c": 0.95},
                    {"id": "w2", "t": "away", "b": [70, 60, 120, 80], "c": 0.92},
                ],
            },
        ],
    }


class RevisionRealignmentTests(unittest.TestCase):
    def test_normalize_adds_ids_without_mutating_source(self):
        source = {
            "lines": [
                {
                    "words": [
                        {"t": "one", "b": [0, 0, 10, 10]},
                        {"t": "two", "b": [11, 0, 20, 10]},
                    ]
                }
            ]
        }

        normalized = normalize_ocr_document(source)

        self.assertEqual(normalized["lines"][0]["id"], "l1")
        self.assertEqual(
            [word["id"] for word in normalized["lines"][0]["words"]],
            ["w1", "w2"],
        )
        self.assertNotIn("id", source["lines"][0]["words"][0])

    def test_replacement_preserves_geometry_and_drops_old_confidence(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"][0]["words"][1].update(
            {"t": "birds", "b": [0, 0, 1, 1]}
        )

        result, warnings = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        word = result["lines"][0]["words"][1]
        self.assertEqual(word["b"], [55, 20, 90, 40])
        self.assertNotIn("c", word)
        self.assertEqual(warnings, [])

    def test_inserted_word_gets_estimated_box_and_reports_tight_gap(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"][0]["words"].insert(
            1, {"id": "w3", "t": "small", "b": []}
        )

        result, warnings = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        box = result["lines"][0]["words"][1]["b"]
        self.assertEqual((box[1], box[3]), (20, 40))
        self.assertGreater(box[2], box[0])
        self.assertTrue(any("limited to the gap" in warning for warning in warnings))

    def test_deleted_word_is_kept_as_id_tombstone(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"][0]["words"][0].update({"t": "", "b": []})

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual(
            result["lines"][0]["words"][0],
            {"id": "w1", "t": "", "b": []},
        )

    def test_deleted_word_by_omission_is_converted_to_tombstone(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"][0]["words"] = [submitted["lines"][0]["words"][1]]

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        words = result["lines"][0]["words"]
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]["id"], "w1")
        self.assertEqual(words[0]["t"], "")
        self.assertEqual(words[0]["b"], [])
        self.assertEqual(words[1]["id"], "w2")
        self.assertEqual(words[1]["t"], "bird")

    def test_deleted_line_by_omission_is_removed(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"] = [submitted["lines"][0]]

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual(len(result["lines"]), 1)
        self.assertEqual(result["lines"][0]["id"], "l1")

    def test_deleted_line_by_empty_words_and_box_is_removed(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"][1] = {"id": "l2", "b": [], "words": []}

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual(len(result["lines"]), 1)
        self.assertEqual(result["lines"][0]["id"], "l1")

    def test_added_line_between_lines_estimates_box_and_places_words(self):
        base = _sample_document()
        submitted = _sample_document()
        new_line = {
            "id": "l3",
            "b": [],
            "words": [
                {"id": "w1", "t": "softly", "b": []},
            ],
        }
        submitted["lines"].insert(1, new_line)

        result, warnings = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual(len(result["lines"]), 3)
        self.assertEqual(result["lines"][0]["id"], "l1")
        self.assertEqual(result["lines"][1]["id"], "l3")
        self.assertEqual(result["lines"][2]["id"], "l2")

        line_box = result["lines"][1]["b"]
        self.assertGreaterEqual(line_box[1], 40)
        self.assertLessEqual(line_box[3], 60)

        word = result["lines"][1]["words"][0]
        self.assertEqual(word["id"], "w1")
        self.assertEqual(word["t"], "softly")
        self.assertGreater(word["b"][2], word["b"][0])
        self.assertEqual(word["b"][1], line_box[1])
        self.assertEqual(word["b"][3], line_box[3])

    def test_added_line_with_explicit_box(self):
        base = _sample_document()
        submitted = _sample_document()
        new_line = {
            "id": "l3",
            "b": [15, 100, 300, 130],
            "words": [
                {"id": "w1", "t": "high", "b": []},
                {"id": "w2", "t": "above", "b": []},
            ],
        }
        submitted["lines"].append(new_line)

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual(len(result["lines"]), 3)
        self.assertEqual(result["lines"][2]["b"], [15, 100, 300, 130])
        words = result["lines"][2]["words"]
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0]["b"][0], 15)
        self.assertGreaterEqual(words[1]["b"][0], words[0]["b"][2])

    def test_auto_generates_word_and_line_ids_if_omitted(self):
        base = _sample_document()
        submitted = {
            "lines": [
                {
                    "words": [{"t": "only"}]
                }
            ]
        }

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual(len(result["lines"]), 1)
        self.assertEqual(result["lines"][0]["id"], "l3")
        self.assertEqual(result["lines"][0]["words"][0]["id"], "w1")
        self.assertEqual(result["lines"][0]["words"][0]["t"], "only")
        self.assertEqual(len(result["lines"][0]["words"][0]["b"]), 4)

    def test_reordered_lines_preserves_submitted_order(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"] = [submitted["lines"][1], submitted["lines"][0]]

        result, _ = realign_revision_document(
            base_document=base,
            submitted_document=submitted,
            page_width=500,
            page_height=200,
        )

        self.assertEqual([line["id"] for line in result["lines"]], ["l2", "l1"])

    def test_new_words_must_start_without_a_box(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"][0]["words"].append(
            {"id": "w3", "t": "new", "b": [91, 20, 120, 40]}
        )

        with self.assertRaisesRegex(RevisionDocumentError, "empty box"):
            realign_revision_document(
                base_document=base,
                submitted_document=submitted,
                page_width=500,
                page_height=200,
            )

    def test_rejects_nonmonotonic_new_word_id(self):
        base = _sample_document()
        base["lines"][0]["words"][1]["id"] = "w3"
        submitted = _sample_document()
        submitted["lines"][0]["words"][1]["id"] = "w3"
        submitted["lines"][0]["words"].append(
            {"id": "w2", "t": "new", "b": []}
        )
        with self.assertRaisesRegex(RevisionDocumentError, "greater than"):
            realign_revision_document(
                base_document=base,
                submitted_document=submitted,
                page_width=500,
                page_height=200,
            )

    def test_rejects_nonmonotonic_new_line_id(self):
        base = _sample_document()
        submitted = _sample_document()
        submitted["lines"].append(
            {
                "id": "l2",
                "words": [{"id": "w1", "t": "repeat", "b": []}],
            }
        )
        with self.assertRaisesRegex(RevisionDocumentError, "Duplicate submitted line ID"):
            realign_revision_document(
                base_document=base,
                submitted_document=submitted,
                page_width=500,
                page_height=200,
            )

        base3 = {
            "page": 1,
            "lines": [
                {
                    "id": "l3",
                    "b": [10, 10, 100, 30],
                    "words": [{"id": "w1", "t": "top", "b": [10, 10, 50, 30]}],
                }
            ],
        }
        submitted3 = {
            "lines": [
                base3["lines"][0],
                {
                    "id": "l2",
                    "b": [],
                    "words": [{"id": "w1", "t": "new", "b": []}],
                },
            ]
        }
        with self.assertRaisesRegex(RevisionDocumentError, "greater than"):
            realign_revision_document(
                base_document=base3,
                submitted_document=submitted3,
                page_width=500,
                page_height=200,
            )


class RevisionSaveServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_persists_revision_and_extends_claim(self):
        page = SimpleNamespace(
            id=12,
            status=QCState.IN_PROGRESS.value,
            ocr_s3_key="ocr/tesseract/V1/i1/p0001.json",
            width=500,
            height=200,
        )
        assignment = SimpleNamespace(
            lock_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
        )

        class FakeSession:
            def __init__(self):
                self.calls = 0
                self.added = []

            async def scalar(self, statement):
                self.calls += 1
                return {1: page, 2: assignment, 3: None}[self.calls]

            def add(self, value):
                self.added.append(value)

            async def flush(self):
                self.added[-1].id = 101

        session = FakeSession()
        s3 = Mock()
        s3.get_object.return_value = {
            "Body": io.BytesIO(json.dumps(_sample_document()).encode())
        }
        submitted = _sample_document()
        submitted["lines"][0]["words"].insert(
            1, {"id": "w3", "t": "small", "b": []}
        )

        result = await save_page_revision(
            session,
            page_id=12,
            user=SimpleNamespace(id=7, level="qc_user"),
            base_revision_id=None,
            submitted_document=submitted,
            s3_client=s3,
            bucket="archive",
        )

        self.assertEqual(result.id, 101)
        self.assertIsNone(session.added[0].based_on_revision_id)
        self.assertEqual(result.document["lines"][0]["words"][1]["id"], "w3")
        self.assertTrue(result.document["lines"][0]["words"][1]["b"])
        self.assertGreater(
            assignment.lock_expires_at,
            datetime.now(timezone.utc) + timedelta(minutes=29),
        )
        s3.put_object.assert_called_once()

    async def test_save_rejects_stale_base_revision(self):
        page = SimpleNamespace(id=12, status=QCState.IN_PROGRESS.value)
        assignment = SimpleNamespace(
            lock_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        revision = SimpleNamespace(id=42, saved_by=7, s3_key="revision.json")

        class FakeSession:
            def __init__(self):
                self.calls = 0

            async def scalar(self, statement):
                self.calls += 1
                return {1: page, 2: assignment, 3: revision}[self.calls]

        with self.assertRaises(RevisionConflictError):
            await save_page_revision(
                FakeSession(),
                page_id=12,
                user=SimpleNamespace(id=7, level="qc_user"),
                base_revision_id=None,
                submitted_document=_sample_document(),
                s3_client=Mock(),
                bucket="archive",
            )

    async def test_save_requires_active_claim(self):
        page = SimpleNamespace(id=12, status=QCState.IN_PROGRESS.value)

        class FakeSession:
            def __init__(self):
                self.calls = 0

            async def scalar(self, statement):
                self.calls += 1
                return page if self.calls == 1 else None

        with self.assertRaises(RevisionClaimRequiredError):
            await save_page_revision(
                FakeSession(),
                page_id=12,
                user=SimpleNamespace(id=7, level="qc_user"),
                base_revision_id=None,
                submitted_document=_sample_document(),
                s3_client=Mock(),
                bucket="archive",
            )


if __name__ == "__main__":
    unittest.main()
