# GOST OCR

Ниже каркас для собственного OCR-распознавателя под ГОСТ-шрифты.

## Что добавлено

- `gost_ocr_common.py` — общие пути и charset
- `generate_gost_ocr_dataset.py` — генерация синтетического датасета строк
- `prepare_real_gost_lines.py` — вырезает кандидатов строк из реальных чертежей
- `autolabel_real_gost_lines.py` — предзаполняет реальные строки текущим OCR
- `build_gost_training_corpus.py` — собирает общий корпус из synthetic и real labeled строк
- `gost_ocr_dataset.py` — dataset и codec
- `gost_ocr_model.py` — CRNN + CTC
- `train_gost_ocr.py` — обучение
- `gost_ocr_infer.py` — инференс для интеграции в приложение
- `run_gost_ocr_debug.py` — отладочный запуск кастомного OCR на PDF/изображении
- `ocr_backend.py` уже умеет переключаться на `custom`

## Шаг 1. Сгенерировать датасет

```bash
cd "/Users/skritosss/Documents/1c project"
python3 generate_gost_ocr_dataset.py
```

Если есть подходящие ГОСТ-шрифты, положите `.ttf/.otf` в:

- `gost_ocr/fonts/`

Если своих шрифтов нет, генератор временно использует системные.

Генератор теперь старается приоритизировать более технические шрифты вроде `DIN`, `Courier`, `Arial Narrow`, а также добавляет более похожие на скан искажения:

- легкий blur
- фоновый шум
- speckle noise
- слабый перекос
- вертикальные/горизонтальные линии, похожие на элементы таблиц

## Шаг 2. Обучить модель

```bash
cd "/Users/skritosss/Documents/1c project"
python3 train_gost_ocr.py --epochs 10
```

По умолчанию обучение теперь идет на CPU. Это сделано специально, потому что на Mac `CTCLoss` не поддерживается на `MPS`.

Checkpoint сохраняется в:

- `gost_ocr/checkpoints/gost_crnn.pt`

Во время обучения выводятся:

- `train_loss`
- `val_loss`
- `val_cer`
- несколько пар `GT/PR`, чтобы сразу видеть, учится ли модель

## Шаг 2.1. Подготовить реальные строки

Для реального улучшения качества synthetic-данных мало. Нужно добавлять реальные строки из чертежей:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 prepare_real_gost_lines.py "/путь/к/скану.pdf" --page 1
```

Результат складывается в:

- `gost_ocr/data/real_labeled/images/`
- `gost_ocr/data/real_labeled/labels/`

В `labels/*.json` нужно потом вручную заполнить поле `"text"` у хороших кандидатов.

Чтобы не размечать все с нуля, можно сначала предзаполнить строки текущим OCR:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 autolabel_real_gost_lines.py "/Users/skritosss/Documents/1c project/gost_ocr/data/real_labeled"
```

После этого остается только быстро вычистить плохие подписи в `labels/*.json`.

## Шаг 2.2. Собрать общий training corpus

Когда появятся реальные размеченные строки:

```bash
cd "/Users/skritosss/Documents/1c project"
python3 build_gost_training_corpus.py
python3 train_gost_ocr.py --data-root "/Users/skritosss/Documents/1c project/gost_ocr/data/corpus" --epochs 10
```

## Шаг 2.3. Проверить checkpoint отдельно

```bash
cd "/Users/skritosss/Documents/1c project"
python3 run_gost_ocr_debug.py "/путь/к/скану.pdf" --page 1
```

Если checkpoint лежит не в стандартном месте:

```bash
python3 run_gost_ocr_debug.py "/путь/к/скану.pdf" --page 1 --checkpoint "/путь/к/gost_crnn.pt"
```

Для проверки только нижнего правого штампа:

```bash
python3 run_gost_ocr_debug.py "/путь/к/скану.pdf" --page 1 --roi title-block --max-lines 30
```

Для оценки на вручную проверенных real crops:

```bash
python3 evaluate_gost_ocr.py --checkpoint "/Users/skritosss/Documents/1c project/gost_ocr/checkpoints/gost_crnn.pt"
```

## Шаг 3. Подключить в приложение

Перед запуском:

```bash
export OCR_BACKEND=custom
export GOST_OCR_CHECKPOINT="/Users/skritosss/Documents/1c project/gost_ocr/checkpoints/gost_crnn.pt"
python3 "/Users/skritosss/Documents/1c project/db_app_v2.py"
```

Если используете `OCR_BACKEND=custom`, наличие `easyocr` больше не обязательно. Для custom-ветки нужен только корректный checkpoint.

## Важный статус

Сейчас это рабочий scaffold под вашу задачу.

Что уже есть:
- интеграционная точка в приложении
- recognizer model
- генерация синтетических train данных
- training / inference scripts
- отдельный debug-скрипт, чтобы проверять модель без запуска всего GUI

Что еще нужно сделать по-настоящему:
- положить максимально похожие на ГОСТ шрифты в `gost_ocr/fonts/`
- обучить checkpoint на большем synthetic corpus
- разметить реальные строки в `gost_ocr/data/real_labeled/labels/*.json`
- смешать synthetic и real data через `build_gost_training_corpus.py`
- протестировать качество на реальных кропах текста из чертежей
