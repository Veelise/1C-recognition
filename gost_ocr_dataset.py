import json
from pathlib import Path

import torch
from PIL import Image
from torch.utils.data import Dataset

from gost_ocr_common import DEFAULT_LINE_HEIGHT, normalize_text, prepare_line_image


class CharsetCodec:
    def __init__(self, charset):
        self.charset = charset
        self.blank_index = 0
        self.char_to_idx = {char: idx + 1 for idx, char in enumerate(charset)}
        self.idx_to_char = {idx + 1: char for idx, char in enumerate(charset)}

    @property
    def num_classes(self):
        return len(self.charset) + 1

    def encode(self, text):
        return [self.char_to_idx[ch] for ch in text if ch in self.char_to_idx]

    def decode_greedy(self, sequence):
        decoded = []
        prev = None
        for idx in sequence:
            idx = int(idx)
            if idx != self.blank_index and idx != prev:
                decoded.append(self.idx_to_char.get(idx, ""))
            prev = idx
        return "".join(decoded)


class GostLineDataset(Dataset):
    def __init__(self, root, manifest_name, codec, image_height=DEFAULT_LINE_HEIGHT):
        self.root = Path(root)
        self.codec = codec
        self.image_height = image_height
        self.records = []
        manifest_path = self.root / manifest_name
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                self.records.append(json.loads(line))

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        record = self.records[index]
        image = Image.open(self.root / record["image"]).convert("L")
        image_tensor = prepare_line_image(image, image_height=self.image_height)
        text = normalize_text(record["text"], self.codec.charset)
        encoded = torch.tensor(self.codec.encode(text), dtype=torch.long)
        return image_tensor, encoded, text


def ctc_collate_fn(batch):
    images = torch.stack([item[0] for item in batch], dim=0)
    targets = torch.cat([item[1] for item in batch], dim=0)
    target_lengths = torch.tensor([len(item[1]) for item in batch], dtype=torch.long)
    texts = [item[2] for item in batch]
    return images, targets, target_lengths, texts
