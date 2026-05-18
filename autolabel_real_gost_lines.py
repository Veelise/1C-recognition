import argparse
import json
from pathlib import Path

from PIL import Image

from ocr_backend import OCRBackend


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Предзаполняет real labeled строки текущим OCR для ускорения ручной разметки."
    )
    parser.add_argument("root", help="Путь к gost_ocr/data/real_labeled")
    parser.add_argument("--backend", default="easyocr", help="OCR backend для автоподписи")
    parser.add_argument("--overwrite", action="store_true", help="Перезаписать уже заполненные text")
    args = parser.parse_args()

    root = Path(args.root)
    backend = OCRBackend(mode=args.backend, gpu=False)
    labels_dir = root / "labels"
    updated = 0

    for json_path in sorted(labels_dir.glob("*.json")):
        payload = load_json(json_path)
        changed = False
        for item in payload:
            if item.get("text") and not args.overwrite:
                continue
            image_path = root / item["image"]
            try:
                result = backend.recognize(Image.open(image_path).convert("L"))
            except Exception as exc:
                item["autolabel_error"] = str(exc)
                changed = True
                continue

            predicted = result.text.strip()
            item["text"] = predicted
            item["autolabel_backend"] = args.backend
            item["autolabel_lines"] = result.lines
            changed = True
            updated += 1

        if changed:
            save_json(json_path, payload)

    print("Real line autolabel complete.")
    print(f"Root: {root.resolve()}")
    print(f"Updated items: {updated}")


if __name__ == "__main__":
    main()
