import os
from pathlib import Path

import cv2
import numpy as np
import torch

from gost_ocr_common import (
    CHECKPOINTS_ROOT,
    DEFAULT_LINE_HEIGHT,
    GOST_CHARSET,
    crop_non_white,
    prepare_line_image,
)
from gost_ocr_dataset import CharsetCodec
from gost_ocr_model import CRNN


DEFAULT_CHECKPOINT = CHECKPOINTS_ROOT / "gost_crnn.pt"


def load_predictor(checkpoint_path=None):
    checkpoint_path = Path(
        checkpoint_path
        or os.getenv("GOST_OCR_CHECKPOINT", str(DEFAULT_CHECKPOINT))
    )
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Не найден checkpoint кастомного OCR: {checkpoint_path}"
        )

    payload = torch.load(checkpoint_path, map_location="cpu")
    charset = payload.get("charset", GOST_CHARSET)
    codec = CharsetCodec(charset)
    model = CRNN(img_h=payload.get("img_h", 64), num_channels=1, num_classes=codec.num_classes)
    model.load_state_dict(payload["model_state"])
    model.eval()

    return {
        "model": model,
        "codec": codec,
        "image_height": payload.get("img_h", DEFAULT_LINE_HEIGHT),
    }


def _segment_lines_by_contours(pil_image, min_width=35, min_height=8):
    gray = np.array(pil_image.convert("L"))
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel_w = max(12, gray.shape[1] // 90)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 3))
    connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    crops = []
    boxes = []
    page_area = gray.shape[0] * gray.shape[1]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_width or h < min_height:
            continue
        if w < h * 1.5:
            continue
        if (w * h) > page_area * 0.08:
            continue
        boxes.append((x, y, w, h))

    boxes.sort(key=lambda item: (item[1], item[0]))
    for x, y, w, h in boxes:
        pad_x = 6
        pad_y = 4
        crop = pil_image.crop((
            max(0, x - pad_x),
            max(0, y - pad_y),
            min(pil_image.size[0], x + w + pad_x),
            min(pil_image.size[1], y + h + pad_y),
        ))
        crops.append(crop)

    return crops


def _segment_lines_by_rows(pil_image):
    gray = np.array(pil_image.convert("L"))
    binary = gray < 220
    row_activity = binary.sum(axis=1)

    lines = []
    in_line = False
    start = 0
    for idx, value in enumerate(row_activity):
        if value > 0 and not in_line:
            start = idx
            in_line = True
        elif value == 0 and in_line:
            if idx - start > 6:
                lines.append((start, idx))
            in_line = False
    if in_line and len(row_activity) - start > 6:
        lines.append((start, len(row_activity)))

    width = pil_image.size[0]
    return [
        pil_image.crop((0, max(0, y1 - 4), width, min(pil_image.size[1], y2 + 4)))
        for y1, y2 in lines
    ]


def _segment_lines(pil_image):
    width, height = pil_image.size
    if height <= DEFAULT_LINE_HEIGHT * 2 and width >= height * 1.2:
        return [pil_image]

    contour_crops = _segment_lines_by_contours(pil_image)
    if contour_crops:
        return contour_crops

    row_crops = _segment_lines_by_rows(pil_image)
    if row_crops:
        return row_crops

    return [pil_image]


def _predict_single_line(predictor, pil_image):
    model = predictor["model"]
    codec = predictor["codec"]
    image_height = predictor["image_height"]

    line_image = crop_non_white(pil_image)
    image_tensor = prepare_line_image(line_image, image_height=image_height).unsqueeze(0)
    with torch.no_grad():
        logits = model(image_tensor)
        pred = logits.softmax(2).argmax(2).permute(1, 0)
    return codec.decode_greedy(pred[0].tolist())


def predict_text(predictor, pil_image):
    line_images = _segment_lines(pil_image)
    texts = []
    for line_img in line_images:
        text = _predict_single_line(predictor, line_img)
        if text.strip():
            texts.append(text.strip())
    return texts
