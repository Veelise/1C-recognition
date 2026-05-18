import argparse
from pathlib import Path

import torch
from torch import nn
from torch.optim import Adam
from torch.utils.data import DataLoader

from gost_ocr_common import CHECKPOINTS_ROOT, GENERATED_ROOT, GOST_CHARSET
from gost_ocr_dataset import CharsetCodec, GostLineDataset, ctc_collate_fn
from gost_ocr_model import CRNN


def resolve_device(requested_device=None):
    if requested_device:
        if requested_device == "mps":
            print("MPS для этого обучения отключен: CTCLoss не поддерживается. Использую CPU.")
            return "cpu"
        return requested_device

    if torch.cuda.is_available():
        return "cuda"

    if torch.backends.mps.is_available():
        print("MPS доступен, но отключен для CTCLoss. Использую CPU.")
        return "cpu"

    return "cpu"


def greedy_decode_batch(log_probs, codec):
    prediction = log_probs.argmax(2).permute(1, 0)
    return [codec.decode_greedy(row.tolist()) for row in prediction]


def char_error_rate(reference, hypothesis):
    if not reference:
        return 0.0 if not hypothesis else 1.0

    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    dp = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        dp[i][0] = i
    for j in range(cols):
        dp[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1] / len(reference)


def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    total_cer = 0.0
    total_samples = 0
    preview = []
    with torch.no_grad():
        for images, targets, target_lengths, texts in loader:
            images = images.to(device)
            targets = targets.to(device)
            logits = model(images)
            log_probs = logits.log_softmax(2)
            input_lengths = torch.full(
                size=(images.size(0),),
                fill_value=log_probs.size(0),
                dtype=torch.long,
                device=device,
            )
            loss = criterion(log_probs, targets, input_lengths, target_lengths.to(device))
            total_loss += loss.item()
            predictions = greedy_decode_batch(log_probs, loader.dataset.codec)
            for truth, pred in zip(texts, predictions):
                total_cer += char_error_rate(truth, pred)
                total_samples += 1
                if len(preview) < 3:
                    preview.append((truth, pred))
    return (
        total_loss / max(len(loader), 1),
        total_cer / max(total_samples, 1),
        preview,
    )


def main():
    parser = argparse.ArgumentParser(description="Обучение OCR-модели под ГОСТ-шрифты.")
    parser.add_argument("--data-root", default=str(GENERATED_ROOT))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--checkpoint", default=str(CHECKPOINTS_ROOT / "gost_crnn.pt"))
    parser.add_argument("--device", default=None)
    parser.add_argument("--resume-from", default=None)
    parser.add_argument(
        "--save-last",
        action="store_true",
        help="Сохранить последний checkpoint даже если validation metric не улучшилась",
    )
    args = parser.parse_args()

    device = resolve_device(args.device)
    print(f"Training device: {device}")
    codec = CharsetCodec(GOST_CHARSET)
    train_ds = GostLineDataset(args.data_root, "train_manifest.jsonl", codec)
    val_ds = GostLineDataset(args.data_root, "val_manifest.jsonl", codec)
    train_loader = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=ctc_collate_fn
    )
    val_loader = DataLoader(
        val_ds, batch_size=args.batch_size, shuffle=False, collate_fn=ctc_collate_fn
    )

    model = CRNN(img_h=64, num_channels=1, num_classes=codec.num_classes).to(device)
    criterion = nn.CTCLoss(blank=0, zero_infinity=True)
    optimizer = Adam(model.parameters(), lr=args.lr)

    best_val = float("inf")
    best_cer = float("inf")
    checkpoint_path = Path(args.checkpoint)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    if args.resume_from:
        resume_path = Path(args.resume_from)
        if not resume_path.exists():
            raise FileNotFoundError(f"Resume checkpoint not found: {resume_path}")
        payload = torch.load(resume_path, map_location=device)
        model.load_state_dict(payload["model_state"])
        print(f"Resumed model from {resume_path}")
        best_val, best_cer, preview = evaluate(model, val_loader, criterion, device)
        print(
            f"Resume baseline: val_loss={best_val:.4f}, val_cer={best_cer:.4f}"
        )
        for truth, pred in preview:
            print(f"  BASE GT: {truth}")
            print(f"  BASE PR: {pred}")

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0

        for images, targets, target_lengths, _ in train_loader:
            images = images.to(device)
            targets = targets.to(device)
            logits = model(images)
            log_probs = logits.log_softmax(2)
            input_lengths = torch.full(
                size=(images.size(0),),
                fill_value=log_probs.size(0),
                dtype=torch.long,
                device=device,
            )
            loss = criterion(log_probs, targets, input_lengths, target_lengths.to(device))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        train_loss = total_loss / max(len(train_loader), 1)
        val_loss, val_cer, preview = evaluate(model, val_loader, criterion, device)
        print(
            f"Epoch {epoch}: train_loss={train_loss:.4f}, "
            f"val_loss={val_loss:.4f}, val_cer={val_cer:.4f}"
        )
        for truth, pred in preview:
            print(f"  GT: {truth}")
            print(f"  PR: {pred}")

        is_better = (val_cer < best_cer) or (
            abs(val_cer - best_cer) < 1e-9 and val_loss < best_val
        )
        if is_better:
            best_val = val_loss
            best_cer = val_cer
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "charset": GOST_CHARSET,
                    "img_h": 64,
                },
                checkpoint_path,
            )
            print(
                f"Saved best checkpoint to {checkpoint_path} "
                f"(val_loss={val_loss:.4f}, val_cer={val_cer:.4f})"
            )

    if args.save_last:
        torch.save(
            {
                "model_state": model.state_dict(),
                "charset": GOST_CHARSET,
                "img_h": 64,
            },
            checkpoint_path,
        )
        print(f"Saved last checkpoint to {checkpoint_path}")


if __name__ == "__main__":
    main()
