import cv2
import numpy as np
import os

img_path = r'E:\1C_recognation\drawing_0491\page_1\cleared_page\page_1_cleared.jpg'

# ✅ ПРОВЕРКА 1: существует ли файл?
if not os.path.exists(img_path):
    print(f"❌ Файл не найден: {img_path}")
    exit()

print(f"✅ Файл найден: {os.path.getsize(img_path)} байт")

img = cv2.imread(img_path)
if img is None:
    print("❌ cv2.imread вернул None - проблема с форматом/доступом")
    exit()

print(f"✅ Изображение загружено: {img.shape}")
h, w = img.shape[:2]

# Примерно правый низ: 40% от верха, 30% от левого края
rough_crop = img[int(h*0.78):h, int(w*0.60):w]
cv2.imwrite('rough_table.png', rough_crop)

gray = cv2.cvtColor(rough_crop, cv2.COLOR_BGR2GRAY)

# ✅ 1. УПЛОТНЯЕМ ИЗНАЧАЛЬНОЕ ИЗОБРАЖЕНИЕ (ДО H/V)
_, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

# УПЛОТНЕНИЕ ЛИНИЙ ПРЯМО В binary
dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (4, 4))
close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel, iterations=2)  # Закрыть поры
binary = cv2.morphologyEx(binary, cv2.MORPH_DILATE, dilate_kernel, iterations=3) # Утолщить

cv2.imwrite('enhanced_binary.png', binary)  # ← СПЛОШНЫЕ ЛИНИИ!

# ✅ 2. Теперь H/V на улучшенном
h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 2))
v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 30))
h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)

table_lines = cv2.bitwise_or(h_lines, v_lines)
cv2.imwrite('debug_lines.png', table_lines)

# Наложение (оставляем как есть)
lines_overlay = rough_crop.copy()
lines_overlay[table_lines > 0] = [0, 255, 0]
cv2.imwrite('debug_lines_overlay.png', lines_overlay)

# ✅ КОНТУРЫ ТОЛЬКО ЛИНИЙ ТАБЛИЦЫ
contours, hierarchy = cv2.findContours(table_lines, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

# Остальной код фильтров без изменений...
valid_contours = []
for i, contour in enumerate(contours):  # ← i добавлен!
    # ✅ 1. БЕЗ ДЕТЕЙ = сетка таблицы (буквы имеют дырки)
    if hierarchy[0][i][2] != -1: continue  # Пропустить буквы
    
    area = cv2.contourArea(contour)
    x, y, bw, bh = cv2.boundingRect(contour)
    
    # Фильтры для таблиц (БЕЗ ИЗМЕНЕНИЙ):
    if area < 200 or area > 80000: continue
    aspect = bw / float(bh)
    if aspect < 0.3 or aspect > 8: continue
    fill = cv2.contourArea(contour) / (bw * bh)
    if fill > 0.6: continue
    
    rect = cv2.minAreaRect(contour)
    angle = abs(rect[2])
    if angle > 10 and angle < 80: continue
    
    valid_contours.append(contour)
    print(f"✓ Контур {i}: area={area}")

if valid_contours:
    largest_contour = max(valid_contours, key=cv2.contourArea)
    x, y, table_w, table_h = cv2.boundingRect(largest_contour)
    
    # Отступы
    margin = 5
    x, y = max(0, x-margin), max(0, y-margin)
    table_w, table_h = table_w+2*margin, table_h+2*margin
    
    clean_table = rough_crop[y:y+table_h, x:x+table_w]
    cv2.imwrite('clean_table.png', clean_table)
    
    # ✅ ДИАГНОСТИКА - посмотрите!
    debug = rough_crop.copy()
    cv2.drawContours(debug, [largest_contour], -1, (0,255,0), 3)
    cv2.rectangle(debug, (x,y,x+table_w,y+table_h), (0,0,255), 2)
    cv2.imwrite('debug_table.png', debug)
else:
    print("❌ Таблица не найдена - используем весь rough_crop")
    cv2.imwrite('clean_table.png', rough_crop)