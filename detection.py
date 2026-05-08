import cv2
import numpy as np
import os
import torch
from transformers import TableTransformerForObjectDetection
from transformers.image_utils import load_image
from PIL import Image

# 1. ГРУБАЯ ОБРЕЗКА (ваш рабочий код)
img_path = r'E:\1C_recognation\drawing_123\cleared_pages\cleared_page_4.jpg'
img = cv2.imread(img_path)
h, w = img.shape[:2]
rough_crop = img[int(h*0.78):h, int(w*0.60):w]
cv2.imwrite('rough_crop.png', rough_crop)

# 2. Table Transformer DETECTION
model = TableTransformerForObjectDetection.from_pretrained("microsoft/table-transformer-detection")
model.eval()

# PIL для модели
pil_img = Image.fromarray(cv2.cvtColor(rough_crop, cv2.COLOR_BGR2RGB))
inputs = model.image_processor(pil_img, return_tensors="pt")
with torch.no_grad():
    outputs = model(**inputs)

# 3. Координаты таблицы
target_sizes = torch.tensor([rough_crop.shape[:2][::-1]])
results = model.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.7)[0]

print("🔍 Таблицы найдены:")
for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
    box = [round(i, 2) for i in box.tolist()]
    print(f"Таблица: {box}, уверенность: {score:.3f}")

# 4. Обрезка лучшей таблицы
if len(results["boxes"]) > 0:
    best_box_idx = torch.argmax(results["scores"])
    best_box = results["boxes"][best_box_idx].tolist()
    x1, y1, x2, y2 = map(int, best_box)
    
    # Отступы
    margin = 10
    clean_table = rough_crop[max(0,y1-margin):min(rough_crop.shape[0],y2+margin), 
                           max(0,x1-margin):min(rough_crop.shape[1],x2+margin)]
    cv2.imwrite('clean_table.png', clean_table)
    print("✅ clean_table.png готов (нейросеть)!")
else:
    print("❌ Таблицы не найдены")
    cv2.imwrite('clean_table.png', rough_crop)