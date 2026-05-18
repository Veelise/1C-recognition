from pathlib import Path
import re

import numpy as np
from PIL import Image
from torchvision import transforms


PROJECT_ROOT = Path(__file__).resolve().parent
GOST_OCR_ROOT = PROJECT_ROOT / "gost_ocr"
DATA_ROOT = GOST_OCR_ROOT / "data"
GENERATED_ROOT = DATA_ROOT / "generated"
REAL_DATA_ROOT = DATA_ROOT / "real_labeled"
FONTS_ROOT = GOST_OCR_ROOT / "fonts"
CHECKPOINTS_ROOT = GOST_OCR_ROOT / "checkpoints"


GOST_CHARSET = (
    " 0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
    "№-.,=()/\\:+\"'[]"
)


DEFAULT_LINE_HEIGHT = 64
DEFAULT_IMAGE_WIDTH = 320


def normalize_text(text, charset=GOST_CHARSET):
    text = (text or "").upper().replace("Ё", "Е")
    allowed = set(charset)
    return "".join(ch for ch in text if ch in allowed).strip()


LATIN_TO_CYRILLIC = str.maketrans({
    "A": "А",
    "B": "В",
    "C": "С",
    "E": "Е",
    "H": "Н",
    "K": "К",
    "M": "М",
    "O": "О",
    "P": "Р",
    "T": "Т",
    "X": "Х",
    "Y": "У",
})


def normalize_pseudo_label(text):
    text = (text or "").upper().replace("Ё", "Е")
    text = text.translate(LATIN_TO_CYRILLIC)
    text = text.replace("#", "").replace("'", "").replace('"', "")
    text = re.sub(r"\s+", " ", text).strip()

    tokens = text.split()
    if tokens:
        short_ratio = sum(1 for tok in tokens if len(tok) <= 2) / len(tokens)
        if len(tokens) >= 3 and short_ratio >= 0.65:
            text = "".join(tokens)

    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
    text = re.sub(r"([А-ЯA-Z])\s+([А-ЯA-Z])", r"\1\2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return normalize_text(text)


def prepare_line_image(pil_image, image_height=DEFAULT_LINE_HEIGHT, image_width=DEFAULT_IMAGE_WIDTH):
    """
    Приводит строку к фиксированному размеру без растяжения символов по ширине.
    """
    image = pil_image.convert("L")
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        image = Image.new("L", (image_width, image_height), color=255)
        return transforms.ToTensor()(image)

    scale = min(image_width / src_w, image_height / src_h)
    new_w = max(1, min(image_width, int(round(src_w * scale))))
    new_h = max(1, min(image_height, int(round(src_h * scale))))

    resized = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (image_width, image_height), color=255)
    offset_x = (image_width - new_w) // 2
    offset_y = (image_height - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return transforms.ToTensor()(canvas)


def crop_non_white(pil_image, threshold=245, pad=4):
    gray = np.array(pil_image.convert("L"))
    mask = gray < threshold
    if not mask.any():
        return pil_image.convert("L")

    ys, xs = np.where(mask)
    x1 = max(0, int(xs.min()) - pad)
    y1 = max(0, int(ys.min()) - pad)
    x2 = min(gray.shape[1], int(xs.max()) + pad + 1)
    y2 = min(gray.shape[0], int(ys.max()) + pad + 1)
    return pil_image.crop((x1, y1, x2, y2)).convert("L")
