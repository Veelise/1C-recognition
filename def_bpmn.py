import tkinter as tk
from tkinter import filedialog, messagebox
import fitz  # PyMuPDF
from PIL import Image, ImageTk
import io
import easyocr
import numpy as np
import os


# Инициализация EasyOCR (один раз!)
reader = easyocr.Reader(['ru', 'en'], gpu=False)

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
    
    # ✅ НОВАЯ: OCR функция
    def perform_ocr():
        if not page_image[0]:
            messagebox.showerror("Ошибка", "Нет изображения страницы!")
            return
    
        try:
            root.update()
            messagebox.showinfo("OCR", "Распознавание... (30-60 сек)")
        
            # ✅ КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: PIL → numpy array
            import numpy as np
            img_array = np.array(page_image[0])  # Конвертируем PIL в numpy
        
            results = reader.readtext(img_array, detail=1, paragraph=False)
            extracted_text = '\n'.join([text.strip() for _, text, conf in results if conf > 0.4])
        
            # Окно с результатом
            text_window = tk.Toplevel(root)
            text_window.title(f"OCR: Страница {current_page[0]+1}")
            text_window.geometry("900x700")
        
            # Добавим статистику
            stats = f"Всего найдено: {len(results)} объектов\n"
            stats += f"Надёжных (>0.5): {len([r for r in results if r[2]>0.5])}\n\n"
            stats += "РАСПОЗНАННЫЙ ТЕКСТ:\n"
            stats += "="*50 + "\n"
        
            text_area = tk.Text(text_window, wrap=tk.WORD, font=('Consolas', 10))
            full_text = stats + extracted_text
            text_area.insert(tk.END, full_text)
            text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Копируем в буфер обмена
            root.clipboard_clear()
            root.clipboard_append(extracted_text)
        
        # Сохранить
            filename = f"ocr_page_{current_page[0]+1}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(extracted_text)
        
            messagebox.showinfo("✅ Готово!", 
                          f"📄 Найдено {len(results)} объектов\n"
                          f"💾 Сохранено: {filename}\n"
                          f"📋 Текст в буфере обмена")
        
            print(f"OCR: {len([r for r in results if r[2]>0.5])} строк с conf>0.5")
        
        except Exception as e:
            messagebox.showerror("Ошибка OCR", f"{str(e)}\n\nУстановите: pip install numpy")
    
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
    
    # Кнопки управления
    buttons_frame = tk.Frame(root)
    buttons_frame.pack(pady=10)
    
    tk.Button(buttons_frame, text="-", command=zoom_out, width=3).pack(side=tk.LEFT, padx=5)
    tk.Button(buttons_frame, text="+", command=zoom_in, width=3).pack(side=tk.LEFT, padx=5)
    tk.Button(buttons_frame, text="Изменить", command=select_file, bg="orange").pack(side=tk.LEFT, padx=10)
    
    # ✅ НОВАЯ КНОПКА OCR
    tk.Button(buttons_frame, text="🔍 OCR", command=perform_ocr, bg="blue", fg="white", width=8).pack(side=tk.LEFT, padx=10)
    
    def confirm_load():
        if pdf_path[0]:
            root.quit()
        else:
            messagebox.showwarning("Предупреждение", "Выберите файл!")
    
    tk.Button(buttons_frame, text="Загрузить", command=confirm_load, bg="green", fg="white").pack(side=tk.LEFT, padx=10)
    tk.Button(buttons_frame, text="Отмена", command=root.quit, bg="red", fg="white").pack(side=tk.LEFT, padx=10)
    
    # Биндинги зума
    canvas.bind("<MouseWheel>", zoom)
    canvas.bind("<Button-4>", lambda e: zoom({"delta": 120}))
    canvas.bind("<Button-5>", lambda e: zoom({"delta": -120}))
    
    # Старт
    select_file()
    root.mainloop()
    if doc[0]:
        doc[0].close()
    return pdf_path[0]

if __name__ == "__main__":
    path = load_pdf_with_buttons()
    if path:
        print(f"Выбран чертеж: {path}")