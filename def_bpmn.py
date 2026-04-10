import tkinter as tk
from tkinter import filedialog, messagebox
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import io
import easyocr
import numpy as np
from preprocessing import preprocess_for_ocr
import os
import datetime

# Инициализация EasyOCR (один раз!)
reader = easyocr.Reader(['ru', 'en'], gpu=False)



def log_crash(error_msg, func_name="unknown"):
    """Только текст краша в crash_reports/."""
    os.makedirs("crash_reports", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"crash_reports/{func_name}_{timestamp}.txt"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(error_msg)  # Только текст!
    
    print(f"📄 Краш: {report_path}")
    return report_path


def load_pdf_with_buttons():
    root = tk.Tk()
    root.title("Загрузка чертежа (многостраничный)")
    root.geometry("2560x1440")
    root.state('zoomed')
    root.resizable(True, True)
    
    
    pdf_path = [None] 
    doc = [None]
    current_page = [0]
    total_pages = [0]
    scale = [1.0]
    canvas_image = [None]  # Список для nonlocal
    page_image = [None]    # ← НОВОЕ: для OCR
    page_spin = None
    page_label = None
    
    # Фрейм предпросмотра
    preview_frame = tk.Frame(root)
    preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    canvas = tk.Canvas(preview_frame, bg='white')
    scrollbar_v = tk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollbar_h = tk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=canvas.xview)
    canvas.configure(yscrollcommand=scrollbar_v.set, xscrollcommand=scrollbar_h.set)
    
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar_v.pack(side=tk.RIGHT, fill=tk.Y)
    scrollbar_h.pack(side=tk.BOTTOM, fill=tk.X)
    
    # Label и Spinbox
    page_label = tk.Label(root, text="Страница 0 из 0", font=('Arial', 12))
    page_label.pack(pady=5)
    
    page_spin = tk.Spinbox(root, from_=1, to=1, width=5, font=('Arial', 12))
    page_spin.pack(side=tk.LEFT, padx=10)
    tk.Label(root, text="№ Чертежа:", font=('Arial', 12)).pack(side=tk.LEFT, padx=10)
    # 🔥 1. СОЗДАЁМ → 2. НАСТРАИВАЕМ → 3. pack()
    drawing_num_entry = tk.Entry(root, width=15, font=('Arial', 12))
    drawing_num_entry.insert(0, "1")
    drawing_num_entry.pack(side=tk.LEFT, padx=5)
    drawing_num_entry.focus_set() 
    
    
    def ensure_drawing_dirs(drawing_num):
        """Создаёт drawing_XXX/ + подпапки"""
        main_dir = f"drawing_{drawing_num}"
        subdirs = ['temp_pages', 'cleared_pages', 'ocr_pages']
        for subdir in subdirs:
            os.makedirs(os.path.join(main_dir, subdir), exist_ok=True)
        print(f"📁 Создана структура: drawing_{drawing_num}/...")
        return main_dir
    
    # ✅ ИСПРАВЛЕННАЯ render_page
    def render_page():
        nonlocal canvas_image
        if not doc[0]:
            return
        try:
            page = doc[0].load_page(current_page[0])
            mat = fitz.Matrix(scale[0], scale[0])
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))
            
            # ← СОХРАНЯЕМ ДЛЯ OCR (глобально доступно)
            page_image[0] = img.copy()
            
            photo = ImageTk.PhotoImage(img)
            
            canvas.delete("all")
            canvas_image[0] = photo
            canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.image = photo
            
            page_label.config(text=f"Страница {current_page[0]+1} из {total_pages[0]}")
        except Exception as e:
            print(f"Ошибка рендера: {e}")
    
    def go_to_page(page_num):
        if 0 <= page_num < total_pages[0]:
            current_page[0] = page_num
            render_page()
            page_spin.delete(0, tk.END)
            page_spin.insert(0, str(current_page[0] + 1))
    
    def update_spinbox():
        if page_spin and total_pages[0] > 0:
            page_spin.delete(0, tk.END)
            page_spin.insert(0, str(current_page[0] + 1))
    
    # Биндинги Spinbox
    page_spin.bind('<Return>', lambda e: go_to_page(int(page_spin.get()) - 1))
    page_spin.bind('<FocusOut>', lambda e: go_to_page(int(page_spin.get()) - 1))
    page_spin.bind('<<Increment>>', lambda e: go_to_page(min(total_pages[0]-1, current_page[0] + 1)))
    page_spin.bind('<<Decrement>>', lambda e: go_to_page(max(0, current_page[0] - 1)))
    
    # Кнопки страниц
    tk.Button(root, text="<< Пред", command=lambda: go_to_page(max(0, current_page[0]-1))).pack(side=tk.LEFT, padx=5)
    tk.Button(root, text="След >>", command=lambda: go_to_page(min(total_pages[0]-1, current_page[0]+1))).pack(side=tk.LEFT, padx=5)
    
    # Зум
    def zoom(event):
        if event.delta > 0:
            scale[0] = min(scale[0] * 1.2, 5.0)
        else:
            scale[0] = max(scale[0] / 1.2, 0.2)
        render_page()
    
    def zoom_in(): 
        scale[0] = min(scale[0]*1.2, 5.0)
        render_page()
    
    def zoom_out(): 
        scale[0] = max(scale[0]/1.2, 0.2)
        render_page()
    
    
    
    # ✅ OCR функция
    def perform_ocr():
        if not page_image[0]:
            messagebox.showerror("Ошибка", "Нет изображения страницы!")
            return
        
        try:
            # 🔥 1. НОМЕР ЧЕРТЕЖА + ПАПКИ (ПЕРВЫМ ДЕЛОМ)
            drawing_num = drawing_num_entry.get().strip()
            if not drawing_num:
                drawing_num = "unnamed"
            main_dir = ensure_drawing_dirs(drawing_num)
            page_num = current_page[0] + 1
            
            root.update()
            messagebox.showinfo("OCR", "Распознавание... (5-60 сек)")
            
            # 🔥 2. АВТОЗУМ (если нужно)
            original_scale = scale[0]
            ocr_scale = 5.0
            high_res_rendered = False
            
            if original_scale < 3.8:
                print(f"🔍 Автозум: {original_scale:.1f}x → {ocr_scale}x")
                scale[0] = ocr_scale
                render_page()  # page_image теперь высокого разрешения
                root.update()
                high_res_rendered = True
            
            # 🔥 3. ПРЕДОБРАБОТКА
            pil_img = page_image[0]  # Высокое или текущее разрешение
            result = preprocess_for_ocr(
                pil_img, 
                page_num=page_num,
                save_files=False  # НЕ сохраняем в preprocessing!
            )
            
            # 🔥 4. СОХРАНЕНИЕ В ПАПКИ (result содержит PIL Image, НЕ список!)
            temp_path = os.path.join(main_dir, 'temp_pages', f'temp_page_{page_num}.jpg')
            cleared_path = os.path.join(main_dir, 'cleared_pages', f'cleared_page_{page_num}.jpg')
            result['temp'].save(temp_path)      # PIL Image
            result['processed'].save(cleared_path)
            
            print(f"✅ {main_dir}/temp_pages/temp_page_{page_num}.jpg")
            print(f"✅ {main_dir}/cleared_pages/cleared_page_{page_num}.jpg")
            
            # 🔥 5. OCR
            processed_pil = result['processed']
            img_array = np.array(processed_pil)
            print(f"📊 Deskew: {result['deskew_angle']:.2f}°, Линий: {result['lines_detected']}")
            
            results = reader.readtext(
                img_array, 
                detail=1, paragraph=False,
                allowlist='АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789№-.,=абвгдежзийклмнопрстуфхцчшщъыьэюяКПЛИСТФм#', 
                width_ths=0.8, height_ths=0.8, low_text=0.3, text_threshold=0.7
            )
            extracted_text = '\n'.join([text.strip() for _, text, conf in results if conf > 0.4])
            
            # 🔥 6. ВОЗВРАТ ЗУМА
            if high_res_rendered:
                scale[0] = original_scale
                render_page()
                root.update()
            
            # 🔥 7. СОХРАНЕНИЕ TXT
            ocr_path = os.path.join(main_dir, 'ocr_pages', f'ocr_page_{page_num}.txt')
            with open(ocr_path, "w", encoding="utf-8") as f:
                f.write(extracted_text)
            
            # Окно результатов
            text_window = tk.Toplevel(root)
            text_window.title(f"OCR: drawing_{drawing_num} стр.{page_num}")
            text_window.geometry("900x700")
            
            stats = f"📁 drawing_{drawing_num}/\n"
            stats += f"Всего: {len(results)} | Надёж >0.5: {len([r for r in results if r[2]>0.5])}\n"
            stats += f"📏 Зум: {ocr_scale if high_res_rendered else original_scale:.1f}x\n"
            stats += f"🔄 Deskew: {result['deskew_angle']:.2f}°\n\n"
            stats += "ТЕКСТ:\n" + "="*50 + "\n"
            
            text_area = tk.Text(text_window, wrap=tk.WORD, font=('Consolas', 10))
            text_area.insert(tk.END, stats + extracted_text)
            text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Буфер + сообщение
            root.clipboard_clear()
            root.clipboard_append(extracted_text)
            messagebox.showinfo("✅ Готово!", 
                f"📁 drawing_{drawing_num}/\n"
                f"📄 {len(results)} объектов\n"
                f"💾 temp_pages/ | cleared_pages/ | ocr_pages/\n"
                f"📋 В буфере")
            
            print(f"OCR: {len([r for r in results if r[2]>0.5])} строк conf>0.5")
            
        except Exception as e:
            report_path = log_crash(str(e), "perform_ocr")
            messagebox.showerror("Ошибка OCR", f"{str(e)}\n📄 {report_path}")
            
            if high_res_rendered:
                scale[0] = original_scale
                render_page()
                root.update()
    
    # select_file
    def select_file():
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            pdf_path[0] = path
            if doc[0]:
                doc[0].close()
            doc[0] = fitz.open(path)
            total_pages[0] = len(doc[0])
            current_page[0] = 0
            scale[0] = 1.0
            page_label.config(text=f"Страница 1 из {total_pages[0]}")
            page_spin.config(from_=1, to=total_pages[0])
            update_spinbox()
            render_page()
            drawing_num_entry.focus_set()
            drawing_num_entry.select_range(0, tk.END)  # Выделить текст
            root.update()  # Принудительно обновить GUI
    
    # Кнопки управления
    buttons_frame = tk.Frame(root)
    buttons_frame.pack(pady=10)
    
    tk.Button(buttons_frame, text="-", command=zoom_out, width=3).pack(side=tk.LEFT, padx=5)
    tk.Button(buttons_frame, text="+", command=zoom_in, width=3).pack(side=tk.LEFT, padx=5)
    tk.Button(buttons_frame, text="Изменить", command=select_file, bg="orange").pack(side=tk.LEFT, padx=10)
    
    # ✅ КНОПКА OCR
    tk.Button(buttons_frame, text="🔍 OCR", command=perform_ocr, bg="blue", fg="white", width=8).pack(side=tk.LEFT, padx=10)
    
    tk.Button(buttons_frame, text="Отмена", command=root.quit, bg="red", fg="white").pack(side=tk.LEFT, padx=10)
    
    # Биндинги зума
    canvas.bind("<MouseWheel>", zoom)
    canvas.bind("<Button-4>", lambda e: zoom({"delta": 120}))
    canvas.bind("<Button-5>", lambda e: zoom({"delta": -120}))
    
    # Старт
    root.mainloop()
    if doc[0]:
        doc[0].close()
    return pdf_path[0]

if __name__ == "__main__":
    path = load_pdf_with_buttons()
    if path:
        print(f"Выбран чертеж: {path}")