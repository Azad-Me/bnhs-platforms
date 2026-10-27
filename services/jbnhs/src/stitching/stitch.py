
import argparse
import json
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader


# --------------------------------------------------
# Configuration
# --------------------------------------------------

FONT_NAME = "JBNHSUnicode"
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]

# PDF points per image pixel at the chosen output width.
DEFAULT_PAGE_WIDTH_PT = 595.28  # Approximate A4 width


# --------------------------------------------------
# 1. Register a Unicode font
# --------------------------------------------------

def register_font():
    for font_path in FONT_PATHS:
        if Path(font_path).exists():
            pdfmetrics.registerFont(
                TTFont(FONT_NAME, font_path)
            )
            return FONT_NAME

    raise FileNotFoundError(
        "No supported font found. Install DejaVu Sans "
        "or configure FONT_PATHS for your environment."
    )


# --------------------------------------------------
# 2. Read and validate OCR JSON
# --------------------------------------------------

def load_ocr_json(json_path):
    with open(json_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if "lines" not in data:
        raise ValueError(
            f"Missing 'lines' in OCR JSON: {json_path}"
        )

    return data


# --------------------------------------------------
# 3. Draw one word as invisible searchable text
# --------------------------------------------------

def draw_invisible_word(pdf, word, image_height, visible=True):
    x1, y1, x2, y2 = bbox_values(word["bbox"])

    # Clamp the bounding box to the image dimensions
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = max(x1, x2)
    y2 = max(y1, y2)

    box_width = x2 - x1
    box_height = y2 - y1

    if box_width <= 0 or box_height <= 0:
        return

    # Convert image coordinates (top-left origin)
    # to PDF coordinates (bottom-left origin).
    pdf_x = x1
    pdf_bottom = image_height - y2

    # Font size is based on OCR box height.
    font_size = max(1, box_height * 0.8)

    # Font vertical metrics, in PDF points.
    ascent = pdfmetrics.getAscent("OCRFont") * font_size / 1000
    descent = pdfmetrics.getDescent("OCRFont") * font_size / 1000
    text_height = ascent - descent

    # Position baseline using the same vertical alignment logic.
    pdf_y = (
        pdf_bottom
        + (box_height - text_height) / 2
        - descent
    )

    # Calculate natural width of this word at the chosen font size.
    natural_width = pdfmetrics.stringWidth(
        word["text"],
        "OCRFont",
        font_size
    )

    if natural_width <= 0:
        return

    # Stretch/compress text to fill the OCR bounding-box width.
    horizontal_scale = (box_width / natural_width) * 100

    if visible:
        # Draw bbox for debugging.
        pdf.setStrokeColorRGB(1, 0, 0)
        pdf.setLineWidth(0.5)
        pdf.rect(
            pdf_x,
            pdf_bottom,
            box_width,
            box_height,
            stroke=1,
            fill=0
        )

        # Visible OCR text, horizontally fitted to bbox.
        pdf.saveState()
        pdf.setFillColorRGB(0, 0.55, 0)
        text_obj = pdf.beginText()
        text_obj.setTextOrigin(pdf_x, pdf_y)
        text_obj.setFont("OCRFont", font_size)
        text_obj.setHorizScale(horizontal_scale)
        text_obj.textOut(word["text"])
        pdf.drawText(text_obj)
        pdf.restoreState()

        confidence = word.get("confidence")
        if confidence is not None:
            pdf.setFillColorRGB(0, 0, 1)
            pdf.setFont("OCRFont", max(1, min(8, box_height * 0.25)))
            pdf.drawString(
                pdf_x,
                max(0, pdf_bottom - 8),
                str(confidence)
            )

    else:
        # Invisible text layer for searching and selection.
        pdf.saveState()

        text_obj = pdf.beginText()
        text_obj.setTextOrigin(pdf_x, pdf_y)
        text_obj.setFont("OCRFont", font_size)
        text_obj.setHorizScale(horizontal_scale)
        text_obj.setTextRenderMode(3)
        text_obj.textOut(word["text"])

        pdf.drawText(text_obj)
        pdf.restoreState()


# --------------------------------------------------
# 4. Draw a complete page
# --------------------------------------------------

def add_page(pdf, image_path, ocr_data, font_name):
    with Image.open(image_path) as image:
        image_width, image_height = image.size

    # Scale image proportionally to an A4-like page width.
    scale = DEFAULT_PAGE_WIDTH_PT / image_width

    # page_width = image_width * scale
    # page_height = image_height * scale

    page_width = image_width
    page_height = image_height

    pdf.setPageSize((page_width, page_height))

    # Visible layer: original scanned page.
    pdf.drawImage(
        ImageReader(str(image_path)),
        0,
        0,
        width=page_width,
        height=page_height,
        preserveAspectRatio=False,
        mask="auto",
    )

    # Invisible layer: searchable OCR words.
    lines = ocr_data["lines"]

    for line in lines:
        for word in line.get("words", []):
            draw_invisible_word(
                pdf=pdf,
                word=word,
                image_height=image_height,
                # scale=scale,
                # font_name=font_name,
            )

    pdf.showPage()


# --------------------------------------------------
# 5. Find source images
# --------------------------------------------------

def build_image_index(image_dir):
    image_extensions = {
        ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"
    }

    index = {}

    for path in Path(image_dir).rglob("*"):
        if path.is_file() and path.suffix.lower() in image_extensions:
            # Store all paths for a basename so duplicates can
            # be detected instead of silently choosing the wrong scan.
            index.setdefault(path.name, []).append(path)

    return index


# --------------------------------------------------
# 6. Create a multi-page searchable PDF
# --------------------------------------------------

def bbox_values(bbox):
    """Accept either {x1,y1,x2,y2} or [x1,y1,x2,y2]."""
    if isinstance(bbox, dict):
        return (
            float(bbox["x1"]),
            float(bbox["y1"]),
            float(bbox["x2"]),
            float(bbox["y2"]),
        )

    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return tuple(float(v) for v in bbox)

    raise ValueError(f"Unsupported bbox format: {bbox}")


def create_searchable_pdf(
    json_dir,
    image_dir,
    output_pdf,
):
    json_files = sorted(Path(json_dir).rglob("ocr.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No ocr.json files found under {json_dir}"
        )

    image_index = build_image_index(image_dir)

    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    font_name = register_font()

    pdf = canvas.Canvas(str(output_pdf), pageCompression=1)

    processed_pages = 0

    for json_path in json_files:
        ocr_data = load_ocr_json(json_path)

        source = ocr_data.get("source", {})
        image_filename = source.get("filename")

        if not image_filename:
            raise ValueError(
                f"Missing source.filename in {json_path}"
            )

        matches = image_index.get(Path(image_filename).name, [])

        if not matches:
            raise FileNotFoundError(
                f"Image '{image_filename}' not found in {image_dir}"
            )

        if len(matches) > 1:
            raise ValueError(
                f"Multiple images named '{image_filename}'. "
                "Remove ambiguity or map this page explicitly."
            )

        image_path = matches[0]

        print(
            f"Processing page {ocr_data.get('page_number', '?')}: "
            f"{image_path.name}"
        )

        add_page(pdf, image_path, ocr_data, font_name)
        processed_pages += 1

    pdf.save()

    # Basic validation: the PDF should have one page per JSON.
    reader = PdfReader(str(output_pdf))

    if len(reader.pages) != processed_pages:
        raise RuntimeError(
            "PDF page count does not match processed OCR pages."
        )

    print("\nSearchable PDF created.")
    print("Pages:", len(reader.pages))
    print("Output:", output_pdf.resolve())

    # Verify that the PDF has an extractable text layer.
    extracted_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )

    print("Extracted text characters:", len(extracted_text))
    print("Text-layer check:", "PASS" if extracted_text.strip() else "FAIL")

    return output_pdf


# --------------------------------------------------
# 7. Command-line entry point
# --------------------------------------------------

def main():
    create_searchable_pdf(
        json_dir="/content/fresh_tess_output",
        image_dir="/content/JBNHS",
        output_pdf="./searchable_pdf_debug_v5_i3.pdf"
    )


if __name__ == "__main__":
    main()
