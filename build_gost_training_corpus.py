import argparse
import json
import shutil
from pathlib import Path

from gost_ocr_common import (
    GENERATED_ROOT,
    REAL_DATA_ROOT,
    normalize_pseudo_label,
)


REAL_KEYWORDS = [
    "ЛИСТ",
    "ГОСТ",
    "РИС",
    "ОСЬ",
    "ОСИ",
    "СМ",
    "НАИМ",
    "СПЕЦ",
    "МАРК",
    "ЦЕХ",
    "СТАЛ",
    "Ф",
]


def score_real_label(text):
    score = 0
    compact = text.replace(" ", "")

    if any(keyword in text for keyword in REAL_KEYWORDS):
        score += 2
    if "-" in text:
        score += 1
    if any(ch.isdigit() for ch in text):
        score += 1
    if any(ch.isalpha() for ch in text):
        score += 1
    if 2 <= len(compact) <= 18:
        score += 1
    if compact.isdigit():
        score += 1
    if "," in text or "." in text:
        score += 1
    return score


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_jsonl(records, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def is_reasonable_real_label(text):
    text = normalize_pseudo_label(text)
    if not text:
        return False
    if len(text) < 2 or len(text) > 40:
        return False

    compact = text.replace(" ", "")
    if not compact:
        return False

    alnum = sum(ch.isalnum() or ch == "№" for ch in compact)
    if alnum / max(len(compact), 1) < 0.6:
        return False

    unique_chars = len(set(compact))
    if unique_chars <= 1:
        return False

    if score_real_label(text) < 3:
        return False

    return True


def copy_record(src_root, image_rel, dst_root, dst_rel):
    src = src_root / image_rel
    dst = dst_root / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def collect_synthetic_records(root, manifest_name):
    records = []
    with open(root / manifest_name, "r", encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    return records


def load_overrides(root):
    overrides_path = root / "clean_overrides.json"
    if not overrides_path.exists():
        return {}
    payload = load_json(overrides_path)
    return {
        item["image"]: normalize_pseudo_label(item.get("text") or "")
        for item in payload
        if item.get("image") and item.get("text")
    }


def collect_override_records(root):
    records = []
    for image, text in load_overrides(root).items():
        if is_reasonable_real_label(text):
            records.append({
                "image": image,
                "text": text,
            })
    return records


def collect_real_records(root, use_overrides=True):
    records = []
    labels_dir = root / "labels"
    if not labels_dir.exists():
        return records

    overrides = load_overrides(root) if use_overrides else {}
    used_overrides = set()
    for json_path in sorted(labels_dir.glob("*.json")):
        for item in load_json(json_path):
            image = item["image"]
            text = overrides.get(image)
            if text:
                used_overrides.add(image)
            else:
                text = normalize_pseudo_label(item.get("text") or "")

            if not is_reasonable_real_label(text):
                continue
            records.append({
                "image": image,
                "text": text,
            })

    for image, text in overrides.items():
        if image in used_overrides:
            continue
        if is_reasonable_real_label(text):
            records.append({
                "image": image,
                "text": text,
            })

    return records


def materialize(records, src_root, dst_root, split):
    split_dir = dst_root / split
    result = []
    for idx, record in enumerate(records):
        suffix = Path(record["image"]).suffix or ".png"
        dst_rel = Path(split) / f"{split}_{idx:05d}{suffix}"
        copy_record(src_root, record["image"], dst_root, dst_rel)
        result.append({
            "image": str(dst_rel),
            "text": record["text"],
        })
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Собирает общий training corpus из synthetic и real labeled строк."
    )
    parser.add_argument("--synthetic-root", default=str(GENERATED_ROOT))
    parser.add_argument("--real-root", default=str(REAL_DATA_ROOT))
    parser.add_argument("--output-root", default=str(GENERATED_ROOT.parent / "corpus"))
    parser.add_argument("--real-val-ratio", type=float, default=0.2)
    parser.add_argument(
        "--real-repeat",
        type=int,
        default=1,
        help="Сколько раз повторить real labeled записи в train split",
    )
    parser.add_argument(
        "--real-source",
        choices=["filtered", "overrides"],
        default="filtered",
        help="filtered: clean overrides + отфильтрованные autolabels; overrides: только ручные clean_overrides",
    )
    args = parser.parse_args()

    synthetic_root = Path(args.synthetic_root)
    real_root = Path(args.real_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    synthetic_train = collect_synthetic_records(synthetic_root, "train_manifest.jsonl")
    synthetic_val = collect_synthetic_records(synthetic_root, "val_manifest.jsonl")
    if args.real_source == "overrides":
        real_records = collect_override_records(real_root)
    else:
        real_records = collect_real_records(real_root)

    real_split = int(len(real_records) * (1 - args.real_val_ratio))
    real_train = real_records[:real_split]
    real_val = real_records[real_split:]

    train_records = []
    val_records = []

    train_records.extend(materialize(synthetic_train, synthetic_root, output_root, "train"))
    val_records.extend(materialize(synthetic_val, synthetic_root, output_root, "val"))

    if real_train:
        repeated_real_train = real_train * max(1, args.real_repeat)
        train_records.extend(materialize(repeated_real_train, real_root, output_root, "train"))
    if real_val:
        val_records.extend(materialize(real_val, real_root, output_root, "val"))

    write_jsonl(train_records, output_root / "train_manifest.jsonl")
    write_jsonl(val_records, output_root / "val_manifest.jsonl")

    print("Combined GOST OCR corpus prepared.")
    print(f"Root: {output_root.resolve()}")
    print(f"Train samples: {len(train_records)}")
    print(f"Val samples: {len(val_records)}")
    print(f"Real labeled used: {len(real_records)}")


if __name__ == "__main__":
    main()
