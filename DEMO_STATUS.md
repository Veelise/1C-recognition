# Demo status

## 1. Предобработка

Команда для воспроизводимого прогона без GUI и базы:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 run_preprocessing_ocr_test.py "/Users/skritosss/Downloads/Telegram Desktop/0491-КЖ6 (1).PDF" --pages all --ocr-pages 1 --ocr-max-width 1000 --out demo_preprocessing_test_0491_clean
```

Актуальный результат:

- PDF: `/Users/skritosss/Downloads/Telegram Desktop/0491-КЖ6 (1).PDF`
- страниц в PDF: 4
- OCR сравнение: страница 1
- original score: `8.00`
- processed score: `15.00`
- вывод: предобработка улучшила OCR-score на тестовой странице

Что показывать:

- `demo_preprocessing_test_0491_clean/page_1/original_page_1.jpg`
- `demo_preprocessing_test_0491_clean/page_1/cleared_page_1.jpg`
- `demo_preprocessing_test_0491_clean/page_1/original_page_1.txt`
- `demo_preprocessing_test_0491_clean/page_1/processed_page_1.txt`
- `demo_preprocessing_test_0491_clean/summary.json`

Важно: GUI теперь вызывает тот же общий `preprocessing.py`, что и этот demo script.

## 2. Custom ГОСТ-OCR

Команда для проверки встроенной обучаемой модели:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 run_gost_ocr_debug.py "/Users/skritosss/Downloads/Telegram Desktop/0491-КЖ6 (1).PDF" --page 1 --checkpoint "/Users/skritosss/Documents/1c project/gost_ocr/checkpoints/gost_crnn.pt"
```

Актуальный результат:

```text
=== GOST OCR RESULT ===
01: УТВ.
```

Последний fine-tune:

- synthetic датасет: `gost_ocr/data/stamp_generated`
- clean real overrides: `gost_ocr/data/real_labeled/clean_overrides.json`
- профиль генерации: короткие поля штампа + вручную проверенные реальные кропы
- baseline на stamp validation: `val_cer=0.8564`
- после synthetic stamp fine-tune: `val_cer=0.7965`
- после clean real overrides fine-tune: `val_cer=0.6997`
- clean real crop eval: `Mean CER=0.6865` вместо `0.9592`
- checkpoint обновлен: `gost_ocr/checkpoints/gost_crnn.pt`

Команда для оценки clean real crops:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 evaluate_gost_ocr.py --checkpoint "/Users/skritosss/Documents/1c project/gost_ocr/checkpoints/gost_crnn.pt"
```

Команда для проверки области штампа:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 run_gost_ocr_debug.py "/Users/skritosss/Downloads/Telegram Desktop/0491-КЖ6 (1).PDF" --page 1 --roi title-block --max-lines 30 --checkpoint "/Users/skritosss/Documents/1c project/gost_ocr/checkpoints/gost_crnn.pt"
```

Честная формулировка для показа:

Кастомная нейросеть под ГОСТ-шрифты уже встроена в OCR-пайплайн через `OCRBackend`, checkpoint загружается и инференс запускается. Сейчас это обучаемый прототип: качество на полном реальном листе пока слабое, поэтому рабочая демонстрация распознавания остается на EasyOCR + предобработка, а custom OCR показывается как подключенная экспериментальная ветка для дальнейшего обучения на размеченных строках.

## 3. Что уже подключено в коде

- `db_app_v2.py` использует `OCRBackend`.
- `ocr_backend.py` переключает режимы `easyocr` и `custom`.
- `preprocessing.py` является общей предобработкой для GUI и demo script.
- `gost_ocr/checkpoints/gost_crnn.pt` используется как checkpoint custom OCR.
