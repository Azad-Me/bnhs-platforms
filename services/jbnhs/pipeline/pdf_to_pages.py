
import fitz  # PyMuPDF
from pathlib import Path
import argparse


def convert_pdf_to_jpegs(pdf_path, output_dir, dpi=300):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    pdf = fitz.open(pdf_path)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    try:
        total_pages = len(pdf)

        for page_index, page in enumerate(pdf):
            pix = page.get_pixmap(
                matrix=matrix,
                colorspace=fitz.csRGB,
                alpha=False,
            )

            output_path = output_dir / (
                f"page_{page_index + 1:05d}.jpg"
            )

            pix.save(str(output_path), jpg_quality=95)

            print(
                f"Converted page {page_index + 1}/{total_pages}: "
                f"{output_path}"
            )

        print(f"\nConversion completed: {total_pages} pages")
        print(f"Images saved in: {output_dir.resolve()}")

    finally:
        pdf.close()


if __name__ == "__main__":

    convert_pdf_to_jpegs("./i1_toned.pdf", "./JBNHS")
