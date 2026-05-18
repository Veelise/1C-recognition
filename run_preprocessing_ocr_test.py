import argparse
import io
import json
import re
import time
from pathlib import Path

import fitz
from PIL import Image

from ocr_backend import OCRBackend
from preprocessing import preprocess_for_ocr


def render_page(pdf_path, page_index, zoom=1.5):
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_index)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return Image.open(io.BytesIO(pix.tobytes("ppm"))).convert("RGB")


def score_lines(lines):
    useful = 0
    garbage = 0
    for line in lines:
        compact = re.sub(r"\s+", "", line)
        if len(compact) < 2:
            garbage += 1
            continue
        alnum = sum(ch.isalnum() for ch in compact)
        if alnum / max(len(compact), 1) >= 0.55:
            useful += 1
        else:
            garbage += 1
    return {
        "lines": len(lines),
        "useful": useful,
        "garbage": garbage,
        "score": useful * 1.5 - garbage * 0.5,
    }


def parse_pages(value, total_pages):
    if value == "all":
        return list(range(total_pages))

    result = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            result.extend(range(int(start) - 1, int(end)))
        else:
            result.append(int(part) - 1)
    return [idx for idx in result if 0 <= idx < total_pages]


def write_text(path, lines):
    path.write_text("\n".join(lines), encoding="utf-8")


def resize_for_ocr(image, max_width):
    if max_width <= 0 or image.width <= max_width:
        return image
    ratio = max_width / image.width
    return image.resize((max_width, max(1, int(image.height * ratio))))


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end preprocessing OCR test without DB or GUI."
    )
    parser.add_argument("pdf_path")
    parser.add_argument("--pages", default="all", help="Examples: all, 1, 1,3, 1-4")
    parser.add_argument("--ocr-pages", default="1", help="Pages to run OCR on, or none")
    parser.add_argument("--ocr-max-width", type=int, default=1400)
    parser.add_argument("--out", default="demo_preprocessing_test")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    pages = parse_pages(args.pages, len(doc))
    ocr_pages = [] if args.ocr_pages == "none" else parse_pages(args.ocr_pages, len(doc))
    backend = OCRBackend(mode="easyocr", gpu=False)

    summary = {
        "pdf": str(pdf_path),
        "pages_total": len(doc),
        "pages_tested": [idx + 1 for idx in pages],
        "ocr_pages": [idx + 1 for idx in ocr_pages],
        "results": [],
    }

    started = time.time()
    for page_index in pages:
        page_num = page_index + 1
        page_dir = out_dir / f"page_{page_num}"
        page_dir.mkdir(parents=True, exist_ok=True)

        original = render_page(pdf_path, page_index)
        original.save(page_dir / f"original_page_{page_num}.jpg")

        preprocessed = preprocess_for_ocr(
            original,
            page_num=page_num,
            save_files=False,
            debug=False,
        )
        preprocessed["temp"].save(page_dir / f"temp_page_{page_num}.jpg")
        preprocessed["cleared"].save(page_dir / f"cleared_page_{page_num}.jpg")

        if page_index in ocr_pages:
            original_for_ocr = resize_for_ocr(original.convert("L"), args.ocr_max_width)
            processed_for_ocr = resize_for_ocr(
                preprocessed["processed"].convert("L"),
                args.ocr_max_width,
            )
            original_ocr = backend.recognize(original_for_ocr)
            processed_ocr = backend.recognize(processed_for_ocr)

            write_text(page_dir / f"original_page_{page_num}.txt", original_ocr.lines)
            write_text(page_dir / f"processed_page_{page_num}.txt", processed_ocr.lines)

            original_score = score_lines(original_ocr.lines)
            processed_score = score_lines(processed_ocr.lines)
        else:
            original_score = None
            processed_score = None

        result = {
            "page": page_num,
            "deskew_angle": round(float(preprocessed["deskew_angle"]), 4),
            "hough_lines": int(preprocessed["lines_detected"]),
            "original": original_score,
            "processed": processed_score,
            "processed_better": (
                processed_score["score"] >= original_score["score"]
                if original_score and processed_score
                else None
            ),
        }
        summary["results"].append(result)

        print(
            f"Page {page_num}: "
            f"deskew={result['deskew_angle']:.2f}, "
            f"lines={result['hough_lines']}"
        )
        if original_score and processed_score:
            print(
                f"  OCR: original score={original_score['score']:.2f}, "
                f"processed score={processed_score['score']:.2f}"
            )

    summary["elapsed_sec"] = round(time.time() - started, 2)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Output dir: {out_dir.resolve()}")
    print(f"Summary: {out_dir.resolve() / 'summary.json'}")


if __name__ == "__main__":
    main()
