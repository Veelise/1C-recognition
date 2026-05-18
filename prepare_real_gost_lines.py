import argparse
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from gost_ocr_common import REAL_DATA_ROOT


def load_page_image(path, page_num, zoom=2.0):
    lower = path.lower()
    if lower.endswith(".pdf"):
        import fitz

        doc = fitz.open(path)
        page = doc.load_page(page_num - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.open(io.BytesIO(pix.tobytes("ppm"))).convert("L")

    return Image.open(path).convert("L")


def detect_line_boxes(pil_image, min_width=40, min_height=10):
    gray = np.array(pil_image.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_width or h < min_height:
            continue
        if w < h * 2:
            continue
        boxes.append((x, y, w, h))

    boxes.sort(key=lambda item: (item[1], item[0]))
    return boxes


def save_candidates(pil_image, boxes, output_root, stem):
    images_dir = output_root / "images"
    labels_dir = output_root / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for idx, (x, y, w, h) in enumerate(boxes, start=1):
        pad_x = 6
        pad_y = 4
        crop = pil_image.crop((
            max(0, x - pad_x),
            max(0, y - pad_y),
            min(pil_image.size[0], x + w + pad_x),
            min(pil_image.size[1], y + h + pad_y),
        ))
        image_name = f"{stem}_line_{idx:03d}.png"
        crop.save(images_dir / image_name)
        manifest.append({
            "image": f"images/{image_name}",
            "text": "",
            "source": stem,
            "bbox": [int(x), int(y), int(w), int(h)],
        })

    with open(labels_dir / f"{stem}.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return len(manifest)


def main():
    parser = argparse.ArgumentParser(
        description="Подготовка реальных кандидатов строк из чертежей для кастомного OCR."
    )
    parser.add_argument("input_path", help="Путь к PDF или изображению")
    parser.add_argument("--page", type=int, default=1, help="Номер страницы PDF, начиная с 1")
    parser.add_argument("--output-root", default=str(REAL_DATA_ROOT))
    args = parser.parse_args()

    output_root = Path(args.output_root)
    page_image = load_page_image(args.input_path, args.page)
    boxes = detect_line_boxes(page_image)
    stem = f"{Path(args.input_path).stem}_page_{args.page:03d}"
    count = save_candidates(page_image, boxes, output_root, stem)

    print("Real line candidates prepared.")
    print(f"Root: {output_root.resolve()}")
    print(f"Page stem: {stem}")
    print(f"Candidates: {count}")


if __name__ == "__main__":
    main()
