from __future__ import annotations

import math
import re
from typing import Any


_WORD_ID = re.compile(r"^w([1-9]\d*)$")
_LINE_ID = re.compile(r"^l([1-9]\d*)$")


class RevisionDocumentError(ValueError):
    pass


def normalize_ocr_document(document: dict[str, Any]) -> dict[str, Any]:
    lines = document.get("lines")
    if not isinstance(lines, list):
        raise RevisionDocumentError("The page document must contain a lines list.")

    normalized = dict(document)
    normalized_lines: list[dict[str, Any]] = []

    used_line_ids: set[str] = set()
    for line_index, line in enumerate(lines, start=1):
        if not isinstance(line, dict) or not isinstance(line.get("words"), list):
            raise RevisionDocumentError(
                f"Line {line_index} must contain a words list."
            )
        line_id = line.get("id")
        if isinstance(line_id, str) and line_id:
            if line_id in used_line_ids:
                raise RevisionDocumentError(f"Duplicate line ID: {line_id}.")
            used_line_ids.add(line_id)

    next_generated_line_id = 1
    for line_index, line in enumerate(lines, start=1):
        line_id = line.get("id")
        if not isinstance(line_id, str) or not line_id:
            while f"l{next_generated_line_id}" in used_line_ids:
                next_generated_line_id += 1
            line_id = f"l{next_generated_line_id}"
            used_line_ids.add(line_id)
            next_generated_line_id += 1

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

        used_word_ids: set[str] = set()
        for word in normalized_words:
            word_id = word.get("id")
            if not isinstance(word_id, str) or not word_id:
                continue
            if word_id in used_word_ids:
                raise RevisionDocumentError(
                    f"Duplicate word ID {word_id} in line {line_id}."
                )
            used_word_ids.add(word_id)
        next_generated_word_id = 1
        for word in normalized_words:
            word_id = word.get("id")
            if not isinstance(word_id, str) or not word_id:
                while f"w{next_generated_word_id}" in used_word_ids:
                    next_generated_word_id += 1
                word_id = f"w{next_generated_word_id}"
                word["id"] = word_id
                used_word_ids.add(word_id)
                next_generated_word_id += 1
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
    max_base_line_id = max(
        (
            number
            for line_id in base_lines
            if (number := _line_number(line_id)) is not None
        ),
        default=0,
    )

    warnings: list[str] = []
    output = dict(base)
    output_lines: list[dict[str, Any]] = []

    seen_line_ids: set[str] = set()
    next_generated_line_id = max_base_line_id + 1

    normalized_submitted_lines: list[dict[str, Any]] = []
    for index, line in enumerate(submitted_lines, start=1):
        if not isinstance(line, dict):
            raise RevisionDocumentError(f"Submitted line {index} must be an object.")
        if not isinstance(line.get("words"), list):
            raise RevisionDocumentError(
                f"Submitted line {index} must contain a words list."
            )

        line_id = line.get("id")
        if line_id is not None and not isinstance(line_id, str):
            raise RevisionDocumentError(f"Submitted line {index} needs a string line ID.")

        if line_id:
            if line_id in seen_line_ids:
                raise RevisionDocumentError(f"Duplicate submitted line ID: {line_id}.")
            if line_id not in base_lines:
                number = _line_number(line_id)
                if number is None:
                    raise RevisionDocumentError(
                        f"Line ID {line_id} must use the l-number format."
                    )
                if number <= max_base_line_id:
                    raise RevisionDocumentError(
                        f"New line {line_id} must use an l-number greater than "
                        "the existing line IDs."
                    )
            seen_line_ids.add(line_id)
        else:
            while (
                f"l{next_generated_line_id}" in seen_line_ids
                or f"l{next_generated_line_id}" in base_lines
            ):
                next_generated_line_id += 1
            line_id = f"l{next_generated_line_id}"
            seen_line_ids.add(line_id)
            next_generated_line_id += 1

        line_copy = dict(line)
        line_copy["id"] = line_id
        normalized_submitted_lines.append(line_copy)

    for line_index, submitted_line in enumerate(normalized_submitted_lines):
        line_id = submitted_line["id"]
        submitted_words = submitted_line["words"]

        is_tombstone = (
            submitted_line.get("b") == []
            and (
                len(submitted_words) == 0
                or all(
                    isinstance(w, dict) and w.get("t") == "" and w.get("b") == []
                    for w in submitted_words
                )
            )
        )
        if is_tombstone:
            continue

        if line_id in base_lines:
            base_line = base_lines[line_id]
            base_words = {word["id"]: word for word in base_line["words"]}
            base_words_order = [word["id"] for word in base_line["words"]]
            max_base_id = max(
                (
                    number
                    for word_id in base_words
                    if (number := _word_number(word_id)) is not None
                ),
                default=0,
            )

            seen_word_ids: set[str] = set()
            additions: list[dict[str, Any]] = []
            output_words: list[dict[str, Any]] = []
            next_generated_word_id = max_base_id + 1
            base_order_idx = 0

            for index, word in enumerate(submitted_words, start=1):
                if not isinstance(word, dict):
                    raise RevisionDocumentError(
                        f"Word {index} in line {line_id} must be an object."
                    )
                word_id = word.get("id")
                text = word.get("t")
                if not isinstance(text, str):
                    raise RevisionDocumentError(
                        f"Word {word_id or index} in line {line_id} must have text."
                    )

                if isinstance(word_id, str) and word_id:
                    if word_id in seen_word_ids:
                        raise RevisionDocumentError(
                            f"Duplicate word ID {word_id} in line {line_id}."
                        )
                else:
                    while (
                        f"w{next_generated_word_id}" in seen_word_ids
                        or f"w{next_generated_word_id}" in base_words
                    ):
                        next_generated_word_id += 1
                    word_id = f"w{next_generated_word_id}"
                    next_generated_word_id += 1

                seen_word_ids.add(word_id)

                if word_id in base_words:
                    target_idx = (
                        base_words_order.index(word_id)
                        if word_id in base_words_order
                        else base_order_idx
                    )
                    while base_order_idx < target_idx:
                        skipped_id = base_words_order[base_order_idx]
                        base_order_idx += 1
                        if skipped_id not in seen_word_ids:
                            seen_word_ids.add(skipped_id)
                            skipped_orig = base_words[skipped_id]
                            skipped_copy = dict(skipped_orig)
                            skipped_copy["t"] = ""
                            skipped_copy["b"] = []
                            skipped_copy.pop("c", None)
                            output_words.append(skipped_copy)

                    base_order_idx = max(base_order_idx, target_idx + 1)

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

                word_box = word.get("b", [])
                _validate_box(word_box, f"New word {word_id} in line {line_id}")
                if word_box != []:
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
                new_word["id"] = word_id
                new_word["b"] = []
                additions.append(new_word)
                output_words.append(new_word)

            while base_order_idx < len(base_words_order):
                skipped_id = base_words_order[base_order_idx]
                base_order_idx += 1
                if skipped_id not in seen_word_ids:
                    seen_word_ids.add(skipped_id)
                    skipped_orig = base_words[skipped_id]
                    skipped_copy = dict(skipped_orig)
                    skipped_copy["t"] = ""
                    skipped_copy["b"] = []
                    skipped_copy.pop("c", None)
                    output_words.append(skipped_copy)

            line_copy = dict(base_line)
            submitted_line_box = _valid_box(submitted_line.get("b"))
            if submitted_line_box is not None:
                _validate_page_bounds(
                    submitted_line_box,
                    width=page_width,
                    height=page_height,
                    label=f"Line {line_id}",
                )
                line_copy["b"] = [round(c) for c in submitted_line_box]

            _assign_added_word_boxes(
                line=line_copy,
                words=output_words,
                additions=additions,
                page_width=page_width,
                page_height=page_height,
                warnings=warnings,
            )
            line_copy["words"] = output_words
            output_lines.append(line_copy)

        else:
            submitted_line_box = _valid_box(submitted_line.get("b"))
            if submitted_line_box is not None:
                _validate_page_bounds(
                    submitted_line_box,
                    width=page_width,
                    height=page_height,
                    label=f"Line {line_id}",
                )
                line_box = [round(c) for c in submitted_line_box]
            else:
                prev_box = next(
                    (
                        _valid_box(l.get("b"))
                        for l in reversed(output_lines)
                        if _valid_box(l.get("b")) is not None
                    ),
                    None,
                )
                next_box = None
                for future_line in normalized_submitted_lines[line_index + 1 :]:
                    if _valid_box(future_line.get("b")) is not None:
                        next_box = _valid_box(future_line["b"])
                        break
                    if future_line["id"] in base_lines:
                        base_b = _valid_box(base_lines[future_line["id"]].get("b"))
                        if base_b is not None:
                            next_box = base_b
                            break

                line_box = _estimate_added_line_box(
                    prev_box=prev_box,
                    next_box=next_box,
                    page_width=page_width,
                    page_height=page_height,
                    line_id=line_id,
                    warnings=warnings,
                )

            seen_word_ids = set()
            additions = []
            output_words = []
            next_generated_word_id = 1

            for index, word in enumerate(submitted_words, start=1):
                if not isinstance(word, dict):
                    raise RevisionDocumentError(
                        f"Word {index} in line {line_id} must be an object."
                    )
                word_id = word.get("id")
                text = word.get("t")
                if not isinstance(text, str):
                    raise RevisionDocumentError(
                        f"Word {word_id or index} in line {line_id} must have text."
                    )

                if isinstance(word_id, str) and word_id:
                    if word_id in seen_word_ids:
                        raise RevisionDocumentError(
                            f"Duplicate word ID {word_id} in line {line_id}."
                        )
                else:
                    while f"w{next_generated_word_id}" in seen_word_ids:
                        next_generated_word_id += 1
                    word_id = f"w{next_generated_word_id}"
                    next_generated_word_id += 1

                seen_word_ids.add(word_id)
                number = _word_number(word_id)
                if number is None:
                    raise RevisionDocumentError(
                        f"Word IDs in line {line_id} must use the w-number format."
                    )
                word_box = word.get("b", [])
                _validate_box(word_box, f"New word {word_id} in line {line_id}")
                if word_box != []:
                    raise RevisionDocumentError(
                        f"New word {word_id} must have an empty box for realignment."
                    )
                if not text.strip():
                    raise RevisionDocumentError(
                        f"New word {word_id} cannot be blank; remove the empty "
                        "placeholder before saving."
                    )
                new_word = {key: value for key, value in word.items() if key != "c"}
                new_word["id"] = word_id
                new_word["b"] = []
                additions.append(new_word)
                output_words.append(new_word)

            new_line_entry = {
                key: value
                for key, value in submitted_line.items()
                if key not in ("words", "b", "id")
            }
            new_line_entry["id"] = line_id
            new_line_entry["b"] = line_box
            new_line_entry["words"] = output_words

            _assign_added_word_boxes(
                line=new_line_entry,
                words=output_words,
                additions=additions,
                page_width=page_width,
                page_height=page_height,
                warnings=warnings,
            )
            output_lines.append(new_line_entry)

    output["lines"] = output_lines
    return output, warnings


def _estimate_added_line_box(
    *,
    prev_box: tuple[float, float, float, float] | None,
    next_box: tuple[float, float, float, float] | None,
    page_width: int | None,
    page_height: int | None,
    line_id: str,
    warnings: list[str],
) -> list[int]:
    if prev_box is not None and next_box is not None:
        px0, py0, px1, py1 = prev_box
        nx0, ny0, nx1, ny1 = next_box
        x0 = min(px0, nx0)
        x1 = max(px1, nx1)
        prev_h = py1 - py0
        next_h = ny1 - ny0
        height = max(1, round((prev_h + next_h) / 2))
        gap = ny0 - py1
        if gap >= height:
            y0 = round(py1 + (gap - height) / 2)
            y1 = y0 + height
        else:
            warnings.append(
                f"Line {line_id}: vertical space between neighboring lines is tight; "
                "the estimated box may overlap."
            )
            y0 = round(py1 + 1)
            y1 = min(round(ny0 - 1), y0 + height) if ny0 > y0 + 1 else y0 + height
    elif prev_box is not None:
        px0, py0, px1, py1 = prev_box
        height = max(1, round(py1 - py0))
        spacing = max(2, round(height * 0.25))
        x0 = px0
        x1 = px1
        y0 = py1 + spacing
        y1 = y0 + height
        warnings.append(
            f"Line {line_id}: placed below the preceding line using estimated line height."
        )
    elif next_box is not None:
        nx0, ny0, nx1, ny1 = next_box
        height = max(1, round(ny1 - ny0))
        spacing = max(2, round(height * 0.25))
        x0 = nx0
        x1 = nx1
        y1 = max(1, round(ny0 - spacing))
        y0 = max(0, y1 - height)
        warnings.append(
            f"Line {line_id}: placed above the following line using estimated line height."
        )
    else:
        x0 = 0.0
        y0 = 0.0
        x1 = float(page_width) if page_width else 500.0
        height = 30
        y1 = float(height)
        warnings.append(
            f"Line {line_id}: no neighboring line boxes; using default page placement."
        )

    if page_width is not None:
        x0 = max(0.0, min(float(x0), float(page_width - 1)))
        x1 = max(float(x0 + 1), min(float(x1), float(page_width)))
    else:
        x0 = max(0.0, float(x0))
        x1 = max(float(x0 + 1), float(x1))

    if page_height is not None:
        y0 = max(0.0, min(float(y0), float(page_height - 1)))
        y1 = max(float(y0 + 1), min(float(y1), float(page_height)))
    else:
        y0 = max(0.0, float(y0))
        y1 = max(float(y0 + 1), float(y1))

    return [round(x0), round(y0), round(x1), round(y1)]


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
        word_boxes = [b for w in words if (b := _valid_box(w.get("b"))) is not None]
        if word_boxes:
            line_bounds = (
                min(b[0] for b in word_boxes),
                min(b[1] for b in word_boxes),
                max(b[2] for b in word_boxes),
                max(b[3] for b in word_boxes),
            )
            line["b"] = [round(c) for c in line_bounds]
        else:
            raise RevisionDocumentError(
                f"Cannot place added words because line {line['id']} has no valid box."
            )
    x0, y0, x1, y1 = line_bounds
    if page_width is not None:
        x1 = max(x0 + 1, min(x1, page_width))
    if page_height is not None:
        y1 = max(y0 + 1, min(y1, page_height))

    added_ids = {id(word) for word in additions}
    existing_boxes = [
        (word, box)
        for word in words
        if id(word) not in added_ids
        and word.get("t")
        and (box := _valid_box(word.get("b"))) is not None
    ]
    existing_heights = sorted(
        box[3] - box[1]
        for _, box in existing_boxes
        if box[3] > box[1]
    )
    typical_height = (
        existing_heights[len(existing_heights) // 2]
        if existing_heights
        else max(1.0, y1 - y0)
    )
    # Lines may contain isolated elements (such as a page number) far from
    # the text. Exclude those layout gaps from the single-space estimate.
    max_word_gap = max(2.0, typical_height * 2)
    existing_gaps = sorted(
        gap
        for (_, previous_box), (_, following_box) in zip(
            existing_boxes, existing_boxes[1:]
        )
        if 0 < (gap := following_box[0] - previous_box[2]) <= max_word_gap
    )
    if existing_gaps:
        middle = len(existing_gaps) // 2
        word_gap = (
            existing_gaps[middle]
            if len(existing_gaps) % 2
            else (existing_gaps[middle - 1] + existing_gaps[middle]) / 2
        )
    else:
        word_gap = max(1.0, typical_height * 0.2)

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
        height = max(1, round(sum(heights) / len(heights))) if heights else max(1, round(y1 - y0))
        center_y = (
            sum((box[1] + box[3]) / 2 for box in anchor_boxes) / len(anchor_boxes)
            if anchor_boxes
            else (y0 + y1) / 2
        )
        char_widths = [
            (box[2] - box[0]) / _text_width_units(anchor["t"])
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
        estimated_width = max(
            1,
            math.ceil(_text_width_units(word["t"]) * average_char_width),
        )
        left = previous_box[2] + word_gap if previous_box else x0
        if following_box is None:
            # The current line box ends at the last OCR word, so it is not a
            # right-hand limit for an added word at the end of the line. Keep
            # the normal word gap after its preceding word.
            box_x0 = left
            box_width = estimated_width
        else:
            right = following_box[0] - word_gap
            available_width = right - left
            if available_width <= 0:
                warnings.append(
                    f"{line['id']}/{word['id']}: no horizontal gap; the estimated "
                    "box may overlap a neighboring word."
                )
                box_x0 = max(x0, min(left, right - 1))
                box_width = estimated_width
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

        if page_width is not None:
            if box_x0 >= page_width:
                box_x0 = max(0, page_width - 1)
            if box_x0 + box_width > page_width:
                warnings.append(
                    f"{line['id']}/{word['id']}: the estimated box extends beyond "
                    "the page and was clipped to the page edge."
                )
                box_width = max(1, page_width - box_x0)

        box_y0 = max(y0, min(round(center_y - height / 2), y1 - 1))
        box_y1 = min(y1, box_y0 + height)
        word["b"] = [
            round(box_x0),
            round(box_y0),
            round(box_x0 + box_width),
            round(box_y1),
        ]

    placed_boxes = [
        box
        for word in words
        if (box := _valid_box(word.get("b"))) is not None
    ]
    if placed_boxes:
        expanded = [
            min(x0, *(box[0] for box in placed_boxes)),
            min(y0, *(box[1] for box in placed_boxes)),
            max(x1, *(box[2] for box in placed_boxes)),
            max(y1, *(box[3] for box in placed_boxes)),
        ]
        if page_width is not None:
            expanded[2] = min(expanded[2], page_width)
        if page_height is not None:
            expanded[3] = min(expanded[3], page_height)
        line["b"] = [round(coordinate) for coordinate in expanded]


def _text_width_units(text: str) -> float:
    """Estimate proportional-font width in em units for added OCR words."""
    narrow = "ilI.,'`!:;|"
    wide = "mwMW@%&"
    units = 0.0
    for character in text:
        if character.isspace():
            units += 0.3
        elif character in narrow:
            units += 0.3
        elif character in wide:
            units += 0.85
        elif character.isupper():
            units += 0.66
        elif character.isdigit():
            units += 0.56
        else:
            units += 0.52
    return max(units, 0.3)


def _word_number(word_id: str) -> int | None:
    match = _WORD_ID.fullmatch(word_id)
    return int(match.group(1)) if match else None


def _line_number(line_id: str) -> int | None:
    match = _LINE_ID.fullmatch(line_id)
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
