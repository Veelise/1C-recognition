import argparse
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from gost_ocr_common import (
    CHECKPOINTS_ROOT,
    DEFAULT_IMAGE_WIDTH,
    DEFAULT_LINE_HEIGHT,
    FONTS_ROOT,
    GENERATED_ROOT,
    normalize_text,
)


VOCAB_TEMPLATES = [
    "ЛИСТ {n}",
    "ЛИСТОВ {n}",
    "МАСШТАБ 1:{n}",
    "МАССА {num}",
    "СТАДИЯ {abbr}",
    "ГОСТ {n}-{year}",
    "A-{n}",
    "КЖ-{n}",
    "АР-{n}",
    "АС-{n}",
    "ПРОВЕРИЛ {name}",
    "РАЗРАБОТАЛ {name}",
    "УТВЕРДИЛ {name}",
    "ДАТА {date}",
    "ИНВ. № {n}",
    "ОБОЗНАЧЕНИЕ {code}",
    "НАИМЕНОВАНИЕ {object_name}",
    "СТАДИЯ {abbr} ЛИСТ {n}",
    "{code}",
    "{code}-{n}",
    "{abbr}-{n}/{sheet}",
    "МОНТАЖНЫЙ ПЛАН",
    "СПЕЦИФИКАЦИЯ ИЗДЕЛИЙ",
    "УЗЕЛ {n}",
    "СХЕМА {abbr}-{n}",
    "ФРАГМЕНТ {n}",
    "ЭКСПЛИКАЦИЯ ПОМЕЩЕНИЙ",
    "ИНВ.№ {n}",
    "ЗАМ.ИНВ.№ {n}",
    "ПОДПИСЬ",
    "РАЗР.",
    "ПРОВ.",
    "Н.КОНТР.",
    "УТВ.",
]

STAMP_TEMPLATES = [
    "ЛИСТ {n}",
    "ЛИСТОВ {n}",
    "МАСШТАБ 1:{n}",
    "МАССА {num}",
    "СТАДИЯ {abbr}",
    "ГОСТ {n}-{year}",
    "A-{n}",
    "КЖ-{n}",
    "АР-{n}",
    "АС-{n}",
    "{code}",
    "{code}-{n}",
    "{abbr}-{n}",
    "{abbr}-{n}/{sheet}",
    "ДАТА {date}",
    "ИНВ. № {n}",
    "РАЗР.",
    "ПРОВ.",
    "Н.КОНТР.",
    "УТВ.",
    "ПОДПИСЬ",
]

ABBR = ["П", "Р", "ЭП", "РД", "КЖ", "АР", "АС", "ОВ", "ВК"]
NAMES = ["ИВАНОВ", "ПЕТРОВ", "СИДОРОВ", "КУЗНЕЦОВ", "СМИРНОВ"]
OBJECTS = [
    "ПЛАН ЭТАЖА",
    "СХЕМА РАСПОЛОЖЕНИЯ",
    "ФУНДАМЕНТЫ",
    "УЗЕЛ КРЕПЛЕНИЯ",
    "СПЕЦИФИКАЦИЯ",
    "ПЛИТА ПЕРЕКРЫТИЯ",
    "СВОДНЫЙ ПЛАН СЕТЕЙ",
    "СХЕМА АРМИРОВАНИЯ",
    "МОНТАЖНАЯ СХЕМА",
]

TECHNICAL_FONT_HINTS = [
    "DIN",
    "Courier",
    "Arial Narrow",
    "Arial",
    "Helvetica",
    "Andale Mono",
    "PT Mono",
    "PT Sans",
]


def discover_fonts():
    custom_fonts = list(FONTS_ROOT.glob("*.ttf")) + list(FONTS_ROOT.glob("*.otf"))
    if custom_fonts:
        return custom_fonts

    fallback_dirs = [
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        Path("/System/Library/AssetsV2"),
    ]
    discovered = []
    for root in fallback_dirs:
        if root.exists():
            discovered.extend(root.rglob("*.ttf"))
            discovered.extend(root.rglob("*.otf"))

    prioritized = []
    other = []
    for path in discovered:
        name = path.name.lower()
        if any(hint.lower() in name for hint in TECHNICAL_FONT_HINTS):
            prioritized.append(path)
        else:
            other.append(path)

    result = prioritized[:30]
    if len(result) < 10:
        result.extend(other[: max(0, 20 - len(result))])
    return result


def build_text(profile="mixed"):
    if profile == "stamp":
        template = random.choice(STAMP_TEMPLATES)
    else:
        template = random.choice(VOCAB_TEMPLATES)
    text = template.format(
        n=random.randint(1, 9999),
        year=random.randint(70, 2026),
        num=f"{random.randint(1, 999)}.{random.randint(0, 9)}",
        abbr=random.choice(ABBR),
        name=random.choice(NAMES),
        date=f"{random.randint(1, 28):02d}.{random.randint(1, 12):02d}.{random.randint(2018, 2026)}",
        code=f"{random.randint(1,999)}-{random.choice(ABBR)}{random.randint(1,99)}",
        object_name=random.choice(OBJECTS),
        sheet=random.randint(1, 24),
    )
    return normalize_text(text)


def make_font(font_paths, font_size):
    font_path = random.choice(font_paths)
    return ImageFont.truetype(str(font_path), font_size)


def choose_fitting_font(text, font_paths, draw, max_width, min_size=14, max_size=36):
    """
    Подбирает шрифт так, чтобы synthetic label соответствовал видимому тексту.
    Обрезанные строки сильно портят CTC-обучение.
    """
    shuffled_fonts = list(font_paths)
    random.shuffle(shuffled_fonts)
    for font_path in shuffled_fonts[:12]:
        start_size = random.randint(22, max_size)
        for font_size in range(start_size, min_size - 1, -2):
            font = ImageFont.truetype(str(font_path), font_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return font
    return None


def add_speckle_noise(image, amount=0.01):
    arr = np.array(image).astype(np.uint8)
    count = int(arr.size * amount)
    if count <= 0:
        return image

    ys = np.random.randint(0, arr.shape[0], size=count)
    xs = np.random.randint(0, arr.shape[1], size=count)
    vals = np.random.choice([0, 255], size=count)
    arr[ys, xs] = vals
    return Image.fromarray(arr)


def add_scan_shadow(image):
    arr = np.array(image).astype(np.float32)
    h, w = arr.shape
    gradient = np.linspace(random.uniform(0.92, 0.99), random.uniform(0.98, 1.04), w)
    arr *= gradient[None, :]
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def draw_table_guides(draw, width, height):
    if random.random() < 0.45:
        x = random.randint(width // 6, width - width // 6)
        draw.line((x, 0, x, height), fill=random.randint(120, 190), width=1)
    if random.random() < 0.35:
        y = random.randint(height // 4, height - height // 4)
        draw.line((0, y, width, y), fill=random.randint(120, 190), width=1)


def render_text_line(text, font_paths, width, height):
    image = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(image)
    font = choose_fitting_font(text, font_paths, draw, max_width=width - 12)
    if font is None:
        return None

    draw_table_guides(draw, width, height)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    if text_w > width - 8:
        return None

    x = random.randint(4, max(4, width - text_w - 4))
    y = max(0, (height - text_h) // 2 + random.randint(-4, 4))

    draw.text((x, y), text, fill=0, font=font)

    if random.random() < 0.35:
        image = add_scan_shadow(image)

    if random.random() < 0.7:
        image = image.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.0, 0.8)))

    if random.random() < 0.7:
        noise = Image.effect_noise((width, height), random.uniform(2, 8)).convert("L")
        image = Image.blend(image, noise, alpha=random.uniform(0.02, 0.08))

    if random.random() < 0.5:
        image = add_speckle_noise(image, amount=random.uniform(0.001, 0.008))

    if random.random() < 0.3:
        image = image.rotate(random.uniform(-1.5, 1.5), fillcolor=255)

    if random.random() < 0.25:
        image = image.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=3))

    return image


def save_manifest(records, manifest_path):
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Генерация синтетического датасета строк под OCR ГОСТ-шрифтов."
    )
    parser.add_argument("--train-size", type=int, default=4000)
    parser.add_argument("--val-size", type=int, default=500)
    parser.add_argument("--width", type=int, default=DEFAULT_IMAGE_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_LINE_HEIGHT)
    parser.add_argument("--output-root", default=str(GENERATED_ROOT))
    parser.add_argument(
        "--profile",
        choices=["mixed", "stamp"],
        default="mixed",
        help="mixed: разные технические строки; stamp: короткие поля штампа",
    )
    args = parser.parse_args()

    font_paths = discover_fonts()
    if not font_paths:
        raise RuntimeError("Не найдены .ttf/.otf шрифты для генерации датасета")

    output_root = Path(args.output_root)
    train_dir = output_root / "train"
    val_dir = output_root / "val"
    train_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS_ROOT.mkdir(parents=True, exist_ok=True)

    train_records = []
    val_records = []

    for split, total, split_dir, records in [
        ("train", args.train_size, train_dir, train_records),
        ("val", args.val_size, val_dir, val_records),
    ]:
        attempts = 0
        while len(records) < total:
            attempts += 1
            if attempts > total * 20:
                raise RuntimeError(
                    f"Не удалось сгенерировать {total} подходящих строк для split={split}"
                )

            text = build_text(profile=args.profile)
            if not text:
                continue
            image = render_text_line(text, font_paths, args.width, args.height)
            if image is None:
                continue
            idx = len(records)
            image_name = f"{split}_{idx:05d}.png"
            image_path = split_dir / image_name
            image.save(image_path)
            records.append({"image": str(image_path.relative_to(output_root)), "text": text})

    save_manifest(train_records, output_root / "train_manifest.jsonl")
    save_manifest(val_records, output_root / "val_manifest.jsonl")

    print("Synthetic GOST OCR dataset generated.")
    print(f"Root: {output_root.resolve()}")
    print(f"Train samples: {len(train_records)}")
    print(f"Val samples: {len(val_records)}")


if __name__ == "__main__":
    main()
