import argparse
import json
from pathlib import Path

from PIL import Image

from gost_ocr_common import REAL_DATA_ROOT, normalize_pseudo_label
from gost_ocr_infer import load_predictor, predict_text
from train_gost_ocr import char_error_rate


def load_clean_overrides(root):
    path = root / "clean_overrides.json"
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    records = []
    for item in payload:
        text = normalize_pseudo_label(item.get("text") or "")
        if not item.get("image") or not text:
            continue
        records.append({
            "image": item["image"],
            "text": text,
        })
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Оценка custom ГОСТ-OCR на вручную проверенных real crops."
    )
    parser.add_argument("--real-root", default=str(REAL_DATA_ROOT))
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    real_root = Path(args.real_root)
    predictor = load_predictor(args.checkpoint)
    records = load_clean_overrides(real_root)
    if args.limit > 0:
        records = records[:args.limit]

    total_cer = 0.0
    rows = []
    for record in records:
        image = Image.open(real_root / record["image"]).convert("L")
        prediction = " ".join(predict_text(predictor, image))
        prediction = normalize_pseudo_label(prediction)
        cer = char_error_rate(record["text"], prediction)
        total_cer += cer
        rows.append((cer, record["text"], prediction, record["image"]))

    rows.sort(key=lambda item: item[0], reverse=True)
    print("=== REAL CLEAN OCR EVAL ===")
    print(f"Samples: {len(rows)}")
    print(f"Mean CER: {total_cer / max(len(rows), 1):.4f}")
    print()
    for cer, truth, pred, image in rows[:20]:
        print(f"CER={cer:.3f} | GT: {truth}")
        print(f"          PR: {pred}")
        print(f"          IMG: {image}")


if __name__ == "__main__":
    main()
