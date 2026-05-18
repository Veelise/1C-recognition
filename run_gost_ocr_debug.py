import argparse
import io

from PIL import Image

from gost_ocr_infer import load_predictor, predict_text


def load_input_image(path, page_num):
    lower = path.lower()
    if lower.endswith(".pdf"):
        import fitz

        doc = fitz.open(path)
        page = doc.load_page(page_num - 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        return Image.open(io.BytesIO(pix.tobytes("ppm"))).convert("L")

    return Image.open(path).convert("L")


def crop_roi(image, roi):
    if roi == "full":
        return image

    width, height = image.size
    if roi == "title-block":
        return image.crop((
            int(width * 0.50),
            int(height * 0.58),
            width,
            height,
        ))

    raise ValueError(f"Unknown ROI: {roi}")


def main():
    parser = argparse.ArgumentParser(
        description="Отладочный прогон кастомного OCR под ГОСТ-шрифты."
    )
    parser.add_argument("input_path", help="Путь к PDF или изображению")
    parser.add_argument("--page", type=int, default=1, help="Номер страницы PDF, начиная с 1")
    parser.add_argument("--checkpoint", default=None, help="Путь к checkpoint модели")
    parser.add_argument(
        "--roi",
        choices=["full", "title-block"],
        default="full",
        help="Область распознавания: весь лист или нижний правый штамп",
    )
    parser.add_argument("--max-lines", type=int, default=0, help="Ограничить число выводимых строк")
    args = parser.parse_args()

    predictor = load_predictor(args.checkpoint)
    image = crop_roi(load_input_image(args.input_path, args.page), args.roi)
    lines = predict_text(predictor, image)
    if args.max_lines > 0:
        lines = lines[:args.max_lines]

    print("=== GOST OCR RESULT ===")
    if not lines:
        print("(no text)")
        return
    for idx, line in enumerate(lines, start=1):
        print(f"{idx:02d}: {line}")


if __name__ == "__main__":
    main()
