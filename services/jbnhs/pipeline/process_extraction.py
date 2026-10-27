
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2
import pytesseract
from pytesseract import Output


# --------------------------------------------------
# Configuration
# --------------------------------------------------

DEFAULT_CONFIDENCE_THRESHOLD = 0.60


# --------------------------------------------------
# 1. Image utilities
# --------------------------------------------------

def load_image(image_path):
    """Load an image and return it with its dimensions."""

    image_path = Path(image_path)

    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    image = cv2.imread(str(image_path))

    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    height, width = image.shape[:2]

    return image, {
        "filename": image_path.name,
        "width": width,
        "height": height,
    }


def calculate_sha256(image_path):
    """Identify the exact source image used for OCR."""

    digest = hashlib.sha256()

    with open(image_path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


# --------------------------------------------------
# 2. OCR extraction
# --------------------------------------------------

def extract_ocr_data(image, language="eng", psm=3):
    """
    Extract word-level text, confidence, and bounding boxes.

    Tesseract provides word-level confidence and geometry.
    Line-level geometry is calculated later from its words.
    """

    config = f"--oem 3 --psm {psm}"

    data = pytesseract.image_to_data(
        image,
        lang=language,
        config=config,
        output_type=Output.DICT,
    )

    words = []

    for i, raw_text in enumerate(data["text"]):
        text = raw_text.strip()

        if not text:
            continue

        try:
            confidence = float(data["conf"][i])
        except (ValueError, TypeError):
            continue

        # Tesseract uses negative confidence for invalid entries.
        if confidence < 0:
            continue

        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])

        if w <= 0 or h <= 0:
            continue

        words.append({
            "text": text,
            "confidence": round(confidence / 100.0, 4),
            "bbox": {
                "x1": x,
                "y1": y,
                "x2": x + w,
                "y2": y + h,
            },
            "source_ids": {
                "block": int(data["block_num"][i]),
                "paragraph": int(data["par_num"][i]),
                "line": int(data["line_num"][i]),
                "word": int(data["word_num"][i]),
            },
        })

    return words, config


# --------------------------------------------------
# 3. Group words into lines
# --------------------------------------------------

def group_words_into_lines(words, confidence_threshold):
    """
    Group words using Tesseract's block, paragraph, and line IDs.

    The line bbox is the union of its word boxes.
    Line confidence is the mean of word confidences,
    NOT a native Tesseract line-confidence measurement.
    """

    groups = {}

    for word in words:
        ids = word["source_ids"]

        key = (
            ids["block"],
            ids["paragraph"],
            ids["line"],
        )

        groups.setdefault(key, []).append(word)

    lines = []

    for line_number, (key, line_words) in enumerate(
        groups.items(), start=1
    ):
        xs1 = [w["bbox"]["x1"] for w in line_words]
        ys1 = [w["bbox"]["y1"] for w in line_words]
        xs2 = [w["bbox"]["x2"] for w in line_words]
        ys2 = [w["bbox"]["y2"] for w in line_words]

        line_bbox = {
            "x1": min(xs1),
            "y1": min(ys1),
            "x2": max(xs2),
            "y2": max(ys2),
        }

        line_confidence = sum(
            w["confidence"] for w in line_words
        ) / len(line_words)

        output_words = []

        for word_number, word in enumerate(line_words, start=1):
            low_confidence = (
                word["confidence"] < confidence_threshold
            )

            output_words.append({
                "word_id": f"line_{line_number:04d}_word_{word_number:03d}",
                "text": word["text"],
                "confidence": word["confidence"],
                "bbox": word["bbox"],
                "reading_order": word_number,
                "quality": {
                    "low_confidence": low_confidence,
                    "suggested_review": low_confidence,
                },
            })

        lines.append({
            "line_id": f"line_{line_number:04d}",
            "text": " ".join(w["text"] for w in output_words),
            "confidence": round(line_confidence, 4),
            "bbox": line_bbox,
            "reading_order": line_number,
            "source_ids": {
                "block": key[0],
                "paragraph": key[1],
                "line": key[2],
            },
            "words": output_words,
        })

    return lines


# --------------------------------------------------
# 4. Build the project JSON
# --------------------------------------------------

def build_document(
    document_id,
    page_number,
    image_metadata,
    image_path,
    lines,
    language,
    config,
    confidence_threshold,
):
    """Build structured OCR output for the JBNHS backend."""

    try:
        tesseract_version = str(
            pytesseract.get_tesseract_version()
        )
    except Exception:
        tesseract_version = "unknown"

    return {
        "schema_version": "1.0",
        "document_id": document_id,
        "page_number": page_number,
        "source": {
            **image_metadata,
            "sha256": calculate_sha256(image_path),
        },
        "ocr": {
            "engine": "Tesseract",
            "engine_version": tesseract_version,
            "language": language,
            "config": config,
            "confidence_threshold": confidence_threshold,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        },
        "statistics": {
            "line_count": len(lines),
            "word_count": sum(
                len(line["words"]) for line in lines
            ),
            "low_confidence_word_count": sum(
                word["quality"]["low_confidence"]
                for line in lines
                for word in line["words"]
            ),
        },
        "lines": lines,
    }


# --------------------------------------------------
# 5. Save JSON and plain text
# --------------------------------------------------

def save_outputs(document, output_dir):
    """Write the structured JSON and readable OCR text."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "ocr.json"
    text_path = output_dir / "ocr.txt"

    json_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    text = "\n".join(
        line["text"] for line in document["lines"]
    )

    text_path.write_text(text, encoding="utf-8")

    return json_path, text_path


# --------------------------------------------------
# 6. Draw OCR bounding boxes
# --------------------------------------------------

def save_annotated_image(image, lines, output_path):
    """
    Draw line and word boxes for visual validation.

    Low-confidence words receive a different box color.
    """

    annotated = image.copy()

    for line in lines:
        box = line["bbox"]

        cv2.rectangle(
            annotated,
            (box["x1"], box["y1"]),
            (box["x2"], box["y2"]),
            (255, 0, 0),
            2,
        )

        for word in line["words"]:
            b = word["bbox"]

            color = (
                (0, 0, 255)
                if word["quality"]["low_confidence"]
                else (0, 180, 0)
            )

            cv2.rectangle(
                annotated,
                (b["x1"], b["y1"]),
                (b["x2"], b["y2"]),
                color,
                1,
            )

    output_path = Path(output_path)

    if not cv2.imwrite(str(output_path), annotated):
        raise RuntimeError(
            f"Unable to save annotated image: {output_path}"
        )

    return output_path


# --------------------------------------------------
# 7. Pipeline entry point
# --------------------------------------------------

def process_page(
    image_path,
    document_id,
    page_number,
    output_root="output",
    language="eng",
    psm=3,
    confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
):
    """Run the complete OCR pipeline for one page."""

    image_path = Path(image_path)
    image, image_metadata = load_image(image_path)

    words, config = extract_ocr_data(
        image,
        language=language,
        psm=psm,
    )

    lines = group_words_into_lines(
        words,
        confidence_threshold=confidence_threshold,
    )

    document = build_document(
        document_id=document_id,
        page_number=page_number,
        image_metadata=image_metadata,
        image_path=image_path,
        lines=lines,
        language=language,
        config=config,
        confidence_threshold=confidence_threshold,
    )

    output_dir = (
        Path(output_root)
        / f"{document_id}_page_{page_number}"
    )

    json_path, text_path = save_outputs(
        document, output_dir
    )

    image_output_path = output_dir / "ocr_annotated.jpg"

    save_annotated_image(
        image, lines, image_output_path
    )

    print("OCR completed successfully.")
    print(f"Document: {document_id}")
    print(f"Page: {page_number}")
    print(f"Lines: {document['statistics']['line_count']}")
    print(f"Words: {document['statistics']['word_count']}")
    print(
        "Low-confidence words:",
        document["statistics"]["low_confidence_word_count"],
    )
    print(f"JSON: {json_path}")
    print(f"Text: {text_path}")
    print(f"Annotated image: {image_output_path}")

    return document
# --------------------------------------------------

def main():
    import glob
    for page,img_path in enumerate(sorted(glob.glob("/content/JBNHS/*.jpg"))):
      print(img_path)
      process_page(
          image_path=img_path,
          document_id = "JBNHS-Vol-1",
          page_number=page,
          output_root="./fresh_tess_output",
      )


if __name__ == "__main__":
    main()