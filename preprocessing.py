import cv2
import numpy as np
from PIL import Image
import os

def preprocess_for_ocr(pil_image, page_num=1, save_files=True, debug=True):
    """
    page_num: для имён файлов (int)
    save_files: сохранять temp/cleared jpg (bool)
    debug: принты в консоль (bool)
    
    Возвращает: {
        'processed': PIL для EasyOCR,
        'temp': после denoise (сравнение),
        'cleared': финальное ч/б,
        'deskew_angle': угол поворота (°),
        'lines_detected': кол-во линий Hough
    }
    """
    img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    
    # 1. Резкость + CLAHE + denoise
    gaussian = cv2.GaussianBlur(gray, (0, 0), 1.0)
    sharpened = cv2.addWeighted(gray, 1.5, gaussian, -0.5, 0)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(sharpened)
    denoised = cv2.medianBlur(enhanced, 3)
    
    # temp_img (после denoise)
    temp_img = Image.fromarray(denoised)
    if save_files:
        temp_img.save(f"temp_page_{page_num}.jpg")
        if debug: print(f"✅ temp_page_{page_num}.jpg ({temp_img.size})")
    
    # 2. Deskew (улучшенный)
    edges = cv2.Canny(denoised, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 80, minLineLength=w//15, maxLineGap=15)
    angles = []
    lines_count = len(lines) if lines is not None else 0
    
    if lines is not None:
        for line in lines[:30]:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2-y1, x2-x1))
            if 0.5 < abs(angle) < 45:
                angles.append(angle)
    
    deskew_angle = np.median(angles) if angles else 0
    if abs(deskew_angle) > 0.3:
        center = (w//2, h//2)
        M = cv2.getRotationMatrix2D(center, deskew_angle, 1.0)
        denoised = cv2.warpAffine(denoised, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        if debug: print(f"🔄 Deskew: {deskew_angle:.2f}° ({len(angles)} углов)")
    
    # 3. Морфология + adaptive binary
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
    cleaned = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel)
    binary = cv2.adaptiveThreshold(cleaned, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    if np.mean(cleaned) < 127:
        binary = cv2.bitwise_not(binary)
    
    # cleared_img (финал)
    cleared_img = Image.fromarray(binary)
    if save_files:
        cleared_img.save(f"cleared_page_{page_num}.jpg")
        if debug: print(f"✅ cleared_page_{page_num}.jpg")
    
    return {
        'processed': cleared_img,  # Для EasyOCR
        'temp': temp_img,
        'cleared': cleared_img,
        'deskew_angle': deskew_angle,
        'lines_detected': lines_count,
        'mean_intensity': np.mean(cleaned)
    }

# Тест (опционально)
if __name__ == "__main__":
    dummy = Image.new('RGB', (800, 600))
    result = preprocess_for_ocr(dummy, page_num=999, save_files=True)
    print("✅ Модуль готов:", result['processed'].size)