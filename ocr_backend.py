import os
from dataclasses import dataclass

import numpy as np


DEFAULT_ALLOWLIST = (
    ' АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'
    'абвгдежзийклмнопрстуфхцчшщъыьэюя'
    '0123456789№-.,=()«»"\'# '
)


@dataclass
class OCRResult:
    lines: list
    raw: list

    @property
    def text(self):
        return "\n".join(self.lines)


class OCRBackend:
    """
    Единая точка OCR для приложения.

    Сейчас по умолчанию использует EasyOCR.
    Позже сюда можно подключить обученную модель под ГОСТ-шрифты,
    не переписывая GUI и бизнес-логику.
    """

    def __init__(self, mode=None, gpu=False):
        self.mode = mode or os.getenv("OCR_BACKEND", "easyocr")
        self.gpu = gpu
        self.easyocr_reader = None
        self.custom_predictor = None

    def recognize(self, pil_image, allowlist=DEFAULT_ALLOWLIST):
        if self.mode == "custom":
            return self._recognize_custom(pil_image, allowlist=allowlist)
        return self._recognize_easyocr(pil_image, allowlist=allowlist)

    def _recognize_easyocr(self, pil_image, allowlist=DEFAULT_ALLOWLIST):
        try:
            import easyocr
        except ImportError as exc:
            raise RuntimeError(
                "Выбран backend easyocr, но библиотека easyocr не установлена. "
                "Установите: pip install easyocr"
            ) from exc

        if self.easyocr_reader is None:
            self.easyocr_reader = easyocr.Reader(["ru", "en"], gpu=self.gpu)

        img_array = np.array(pil_image)
        results = self.easyocr_reader.readtext(
            img_array,
            detail=1,
            paragraph=False,
            allowlist=allowlist,
            width_ths=0.6,
            height_ths=0.6,
            low_text=0.35,
            text_threshold=0.65,
            mag_ratio=1.3,
        )

        lines = []
        for item in results:
            try:
                _, text, conf = item
            except ValueError:
                _, (text, conf) = item
            if conf > 0.45 and len(text.strip()) > 1:
                lines.append(text.strip())

        return OCRResult(lines=lines, raw=results)

    def _recognize_custom(self, pil_image, allowlist=DEFAULT_ALLOWLIST):
        """
        Заглушка под будущую обученную модель.

        Ожидается модуль `gost_ocr_infer.py` с функцией:
            load_predictor()
            predict_text(predictor, pil_image) -> list[str] | str
        """
        if self.custom_predictor is None:
            try:
                from gost_ocr_infer import load_predictor
            except ImportError as exc:
                raise RuntimeError(
                    "Выбран OCR_BACKEND=custom, но модуль gost_ocr_infer.py не найден"
                ) from exc
            self.custom_predictor = load_predictor()

        from gost_ocr_infer import predict_text

        prediction = predict_text(self.custom_predictor, pil_image)
        if isinstance(prediction, str):
            lines = [line.strip() for line in prediction.splitlines() if line.strip()]
        else:
            lines = [str(line).strip() for line in prediction if str(line).strip()]

        return OCRResult(lines=lines, raw=prediction)
