from __future__ import annotations

import math
import re
from typing import Any


_WORD_ID = re.compile(r"^w([1-9]\d*)$")


class RevisionDocumentError(ValueError):
    pass


def normalize_ocr_document(document: dict[str, Any]) -> dict[str, Any]:
    lines = document.get("lines")
    if not isinstance(lines, list):
        raise RevisionDocumentError("The page document must contain a lines list.")

    normalized = dict(document)
    normalized_lines: list[dict[str, Any]] = []
    seen_lines: set[str] = set()
    for line_index, line in enumerate(lines, start=1):
        if not isinstance(line, dict) or not isinstance(line.get("words"), list):
            raise RevisionDocumentError(
                f"Line {line_index} must contain a words list."
            )
        line_id = line.get("id")
        if not isinstance(line_id, str) or not line_id:
            line_id = f"l{line_index}"
        if line_id in seen_lines:
            raise RevisionDocumentError(f"Duplicate line ID: {line_id}.")
        seen_lines.add(line_id)

        normalized_words: list[dict[str, Any]] = []
        for word_index, source_word in enumerate(line["words"], start=1):
            if not isinstance(source_word, dict):
                raise RevisionDocumentError(
                    f"Word {word_index} in line {line_id} must be an object."
                )
            word = dict(source_word)
            if not isinstance(word, dict) or not isinstance(word.get("t"), str):
                raise RevisionDocumentError(
                    f"Word {word_index} in line {line_id} must have text."
                )
            normalized_words.append(word)

        used_ids: set[str] = set()
        for word in normalized_words:
            word_id = word.get("id")
            if not isinstance(word_id, str) or not word_id:
                continue
            if word_id in used_ids:
                raise RevisionDocumentError(
                    f"Duplicate word ID {word_id} in line {line_id}."
                )
            used_ids.add(word_id)
        next_generated_id = 1
        for word in normalized_words:
            word_id = word.get("id")
            if not isinstance(word_id, str) or not word_id:
                while f"w{next_generated_id}" in used_ids:
                    next_generated_id += 1
                word_id = f"w{next_generated_id}"
                word["id"] = word_id
                used_ids.add(word_id)
                next_generated_id += 1
            if _word_number(word_id) is None:
                raise RevisionDocumentError(
                    f"Word IDs in line {line_id} must use the w-number format."
                )
            word.setdefault("b", [])
            _validate_box(word["b"], f"Word {word_id} in line {line_id}")

        line_copy = dict(line)
        line_copy["id"] = line_id
        line_copy["words"] = normalized_words
        line_copy.setdefault("b", [])
        _validate_box(line_copy.get("b"), f"Line {line_id}")
        normalized_lines.append(line_copy)

    normalized["lines"] = normalized_lines
    return normalized


def realign_revision_document(
    *,
    base_document: dict[str, Any],
    submitted_document: dict[str, Any],
    page_width: int | None,
    page_height: int | None,
) -> tuple[dict[str, Any], list[str]]:
    base = normalize_ocr_document(base_document)
    for line in base["lines"]:
        line_box = _valid_box(line["b"])
        if line_box is not None:
            _validate_page_bounds(
                line_box,
                width=page_width,
                height=page_height,
                label=f"Line {line['id']}",
            )
        for word in line["words"]:
            word_box = _valid_box(word["b"])
            if word_box is not None:
                _validate_page_bounds(
                    word_box,
                    width=page_width,
                    height=page_height,
                    label=f"Word {word['id']} in line {line['id']}",
                )
    if not isinstance(submitted_document, dict):
        raise RevisionDocumentError("The submitted page document must be an object.")
    submitted_lines = submitted_document.get("lines")
    if not isinstance(submitted_lines, list):
        raise RevisionDocumentError("The submitted page must contain a lines list.")

    base_lines = {line["id"]: line for line in base["lines"]}
    submitted_by_id: dict[str, dict[str, Any]] = {}
    for index, line in enumerate(submitted_lines, start=1):
        if not isinstance(line, dict) or not isinstance(line.get("id"), str):
            raise RevisionDocumentError(f"Submitted line {index} needs a line ID.")
        line_id = line["id"]
        if line_id in submitted_by_id:
            raise RevisionDocumentError(f"Duplicate submitted line ID: {line_id}.")
        if line_id not in base_lines:
            raise RevisionDocumentError(f"Unknown line ID: {line_id}.")
        if not isinstance(line.get("words"), list):
            raise RevisionDocumentError(f"Line {line_id} must contain a words list.")
        submitted_by_id[line_id] = line

    missing_lines = set(base_lines) - set(submitted_by_id)
    if missing_lines:
        raise RevisionDocumentError(
            "Lines cannot be removed by this operation; use an explicit line "
            f"deletion operation. Missing: {', '.join(sorted(missing_lines))}."
        )

    output = dict(base)
    warnings: list[str] = []
    output_lines: list[dict[str, Any]] = []
    for base_line in base["lines"]:
        line_id = base_line["id"]
        submitted_line = submitted_by_id[line_id]
        base_words = {word["id"]: word for word in base_line["words"]}
        submitted_words = submitted_line["words"]
        seen_word_ids: set[str] = set()
        additions: list[dict[str, Any]] = []
        output_words: list[dict[str, Any]] = []
        max_base_id = max(
            (
                number
                for word_id in base_words
                if (number := _word_number(word_id)) is not None
            ),
            default=0,
        )

        for index, word in enumerate(submitted_words, start=1):
            if not isinstance(word, dict):
                raise RevisionDocumentError(
                    f"Word {index} in line {line_id} must be an object."
                )
            word_id = word.get("id")
            text = word.get("t")
            if not isinstance(word_id, str) or not word_id:
                raise RevisionDocumentError(
                    f"Word {index} in line {line_id} needs a word ID."
                )
            if not isinstance(text, str):
                raise RevisionDocumentError(
                    f"Word {word_id} in line {line_id} must have text."
                )
            if word_id in seen_word_ids:
                raise RevisionDocumentError(
                    f"Duplicate word ID {word_id} in line {line_id}."
                )
            seen_word_ids.add(word_id)

            if word_id in base_words:
                original = base_words[word_id]
                word_copy = dict(original)
                if text == "" and word.get("b") != []:
                    raise RevisionDocumentError(
                        f"Deleted word {word_id} must have an empty box."
                    )
                word_copy["t"] = text
                if text == "":
                    word_copy["b"] = []
                    word_copy.pop("c", None)
                elif text != original["t"]:
                    word_copy.pop("c", None)
                output_words.append(word_copy)
                continue

            _validate_box(word.get("b"), f"New word {word_id} in line {line_id}")
            if word.get("b") != []:
                raise RevisionDocumentError(
                    f"New word {word_id} must have an empty box for realignment."
                )
            number = _word_number(word_id)
            if number is None or number <= max_base_id:
                raise RevisionDocumentError(
                    f"New word {word_id} must use a w-number greater than "
                    f"the existing IDs in line {line_id}."
                )
            if not text.strip():
                raise RevisionDocumentError(
                    f"New word {word_id} cannot be blank; remove the empty "
                    "placeholder before saving."
                )
            new_word = {key: value for key, value in word.items() if key != "c"}
            new_word["b"] = []
            additions.append(new_word)
            output_words.append(new_word)

        for word_id, original in base_words.items():
            if word_id not in seen_word_ids:
                raise RevisionDocumentError(
                    f"Word {word_id} is missing from line {line_id}; represent "
                    "a deletion with empty text and an empty box."
                )

        _assign_added_word_boxes(
            line=base_line,
            words=output_words,
            additions=additions,
            page_width=page_width,
            page_height=page_height,
            warnings=warnings,
        )
        line_copy = dict(base_line)
        line_copy["words"] = output_words
        output_lines.append(line_copy)

    output["lines"] = output_lines
    return output, warnings


def _assign_added_word_boxes(
    *,
    line: dict[str, Any],
    words: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    page_width: int | None,
    page_height: int | None,
    warnings: list[str],
) -> None:
    if not additions:
        return
    line_box = line.get("b")
    line_bounds = _valid_box(line_box)
    if line_bounds is None:
        raise RevisionDocumentError(
            f"Cannot place added words because line {line['id']} has no valid box."
        )
    x0, y0, x1, y1 = line_bounds
    if page_width is not None:
        x1 = min(x1, page_width)
    if page_height is not None:
        y1 = min(y1, page_height)

    for index, word in enumerate(words):
        if not any(word is added for added in additions):
            continue
        previous = next(
            (
                candidate
                for candidate in reversed(words[:index])
                if candidate.get("t") and _valid_box(candidate.get("b"))
            ),
            None,
        )
        following = next(
            (
                candidate
                for candidate in words[index + 1 :]
                if candidate.get("t") and _valid_box(candidate.get("b"))
            ),
            None,
        )
        previous_box = _valid_box(previous.get("b")) if previous else None
        following_box = _valid_box(following.get("b")) if following else None
        anchors = [anchor for anchor in (previous, following) if anchor is not None]
        if not anchors:
            warnings.append(
                f"{line['id']}/{word['id']}: no neighboring word box; "
                "using the full line height and an estimated horizontal position."
            )

        anchor_boxes = [
            box
            for box in (previous_box, following_box)
            if box is not None
        ]
        heights = [box[3] - box[1] for box in anchor_boxes if box[3] > box[1]]
        height = max(1, round(sum(heights) / len(heights))) if heights else max(1, y1 - y0)
        center_y = (
            sum((box[1] + box[3]) / 2 for box in anchor_boxes) / len(anchor_boxes)
            if anchor_boxes
            else (y0 + y1) / 2
        )
        char_widths = [
            (box[2] - box[0]) / max(len(anchor["t"]), 1)
            for anchor, box in (
                (previous, previous_box),
                (following, following_box),
            )
            if anchor is not None and box is not None and box[2] > box[0]
        ]
        average_char_width = (
            sum(char_widths) / len(char_widths)
            if char_widths
            else max(1.0, (x1 - x0) / max(len(word["t"]) * 8, 1))
        )
        estimated_width = max(1, math.ceil(len(word["t"]) * average_char_width))
        left = previous_box[2] if previous_box else x0
        right = following_box[0] if following_box else x1
        available_width = right - left
        if available_width <= 0:
            warnings.append(
                f"{line['id']}/{word['id']}: no horizontal gap; the estimated "
                "box may overlap a neighboring word."
            )
            box_x0 = max(x0, min(left, x1 - 1))
            box_width = min(estimated_width, max(1, x1 - box_x0))
        elif estimated_width > available_width:
            warnings.append(
                f"{line['id']}/{word['id']}: the estimated text width exceeds "
                "the available gap; box width was limited to the gap."
            )
            box_x0 = left
            box_width = available_width
        else:
            box_x0 = left
            box_width = estimated_width

        box_y0 = max(y0, min(round(center_y - height / 2), y1 - 1))
        box_y1 = min(y1, box_y0 + height)
        word["b"] = [
            round(box_x0),
            round(box_y0),
            round(box_x0 + box_width),
            round(box_y1),
        ]


def _word_number(word_id: str) -> int | None:
    match = _WORD_ID.fullmatch(word_id)
    return int(match.group(1)) if match else None


def _validate_box(value: Any, label: str) -> None:
    if _valid_box(value) is None and value != []:
        raise RevisionDocumentError(
            f"{label} must have an empty box or four finite coordinates."
        )


def _valid_box(value: Any) -> tuple[float, float, float, float] | None:
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
        return None
    x0, y0, x1, y1 = value
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _validate_page_bounds(
    box: tuple[float, float, float, float],
    *,
    width: int | None,
    height: int | None,
    label: str,
) -> None:
    _, _, x1, y1 = box
    if (width is not None and x1 > width) or (
        height is not None and y1 > height
    ):
        raise RevisionDocumentError(
            f"{label} box exceeds the page dimensions."
        )
