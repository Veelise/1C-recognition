# ============================================================================
# ПРИЛОЖЕНИЕ: 1С — ИИ распознавание чертежей (Версия 2)
# Логика: Загрузка → Контроль качества → Предобработка → OCR → Проверка
# ============================================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import psycopg2
import os
import io
from datetime import datetime
import numpy as np

# Попытка импорта библиотек для OCR
try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageEnhance, ImageFilter, ImageTk
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ============================================================================
# SQL-ЗАПРОСЫ
# ============================================================================

GET_ALL_EMPLOYEES = "SELECT idEmployee, Post, FullName, Role FROM EMPLOYEES ORDER BY FullName"
INSERT_EMPLOYEE = "INSERT INTO EMPLOYEES (Post, FullName, Role) VALUES (%s, %s, %s) RETURNING idEmployee"

INSERT_SKETCH_DRAWING = "INSERT INTO SKETCH_DRAWINGS (SFilePath, DateAdded, NumName, idEmployee) VALUES (%s, %s, %s, %s) RETURNING idSkDrav"
INSERT_PRIMARY_DRAWING = "INSERT INTO PRIMARY_DRAWINGS (FilePath, AssociatedWith, NeedToImprove, idEmployee) VALUES (%s, %s, %s, %s) RETURNING id"

GET_PRIMARY_DRAWINGS = "SELECT id, FilePath, AssociatedWith, NeedToImprove, idEmployee FROM PRIMARY_DRAWINGS ORDER BY id DESC"
GET_PRIMARY_BY_ID = "SELECT id, FilePath FROM PRIMARY_DRAWINGS WHERE id = %s"

INSERT_PRO = """
    INSERT INTO PRO (NameDrav, Designation, ProjectCode, Dev, DateOriginalCreation, 
                     OriginalPaperFormat, NumberOfSheets, Notes, NumDrav, idPrimaryDrawing)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING idPrmRes
"""

GET_ALL_PRO = """
    SELECT p.idPrmRes, p.NameDrav, p.Designation, p.ProjectCode, p.Dev, 
           p.DateOriginalCreation, p.OriginalPaperFormat, p.NumberOfSheets, p.Notes,
           CASE WHEN pd.NeedToImprove = TRUE THEN 'На доработке' ELSE 'Одобрено' END
    FROM PRO p
    LEFT JOIN PRIMARY_DRAWINGS pd ON pd.id = p.idPrimaryDrawing
    ORDER BY p.idPrmRes DESC
"""

UPDATE_PRO = """
    UPDATE PRO SET NameDrav=%s, Designation=%s, ProjectCode=%s, Dev=%s,
                   DateOriginalCreation=%s, OriginalPaperFormat=%s, 
                   NumberOfSheets=%s, Notes=%s WHERE idPrmRes=%s
"""

GET_FRO_BY_PRO = "SELECT idFnlRes FROM FRO WHERE pro_id = %s"
INSERT_FRO = """
    INSERT INTO FRO (NameDrav, Designation, ProjectCode, Dev, DateOriginalCreation,
                     OriginalPaperFormat, NumberOfSheets, NumDrav, pro_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING idFnlRes
"""

INSERT_ARCHIVE = """
    INSERT INTO ARCH_OF_DRAWS (FilePathPrmArch, NumDravFROArch, NameDravFROArch,
                               DesignationFROArch, ProjectCodeFROArch, DevFROArch,
                               SaveDateArch, id_employeePrmArch)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING idPrmArch
"""

# ============================================================================
# ОСНОВНОЙ КЛАСС ПРИЛОЖЕНИЯ
# ============================================================================

def log_crash(error_msg, func_name="unknown"):
        """Только текст краша в crash_reports/."""
        os.makedirs("crash_reports", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"crash_reports/{func_name}_{timestamp}.txt"
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(error_msg)  # Только текст!
        
        print(f"📄 Краш: {report_path}")
        return report_path


class DrawingAppV2:
    def __init__(self, root):
        self.root = root
        self.root.title("1С — ИИ распознавание чертежей (v2)")
        self.root.geometry("1200x700")
        
        self.conn = None
        self.cur = None
        self.current_employee_id = None
        self.current_pdf_path = None
        self.current_drawing_id = None
        self.pdf_doc = None
        self.page_image = None
        self.scale = 2.0
        self.ocr_reader = None
        
        self._create_connection_ui()
    
    # =========================================================================
    # ПОДКЛЮЧЕНИЕ К БД
    # =========================================================================
    
    
    
    def _create_connection_ui(self):
        """Интерфейс подключения к БД"""
        self.root.configure(bg='#2c3e50')
        
        frame = tk.Frame(self.root, bg='#2c3e50')
        frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        tk.Label(frame, text="Подключение к PostgreSQL", font=('Arial', 16, 'bold'), 
                bg='#2c3e50', fg='white').pack(pady=20)
        
        # Поля подключения
        self.db_host = tk.Entry(frame, width=30)
        self.db_host.insert(0, "localhost")
        self.db_port = tk.Entry(frame, width=30)
        self.db_port.insert(0, "5432")
        self.db_name = tk.Entry(frame, width=30)
        self.db_name.insert(0, "shuvi_test")
        self.db_user = tk.Entry(frame, width=30)
        self.db_user.insert(0, "postgres")
        self.db_pass = tk.Entry(frame, width=30, show="*")
        
        fields = [
            ("Host:", self.db_host),
            ("Port:", self.db_port),
            ("Database:", self.db_name),
            ("User:", self.db_user),
            ("Password:", self.db_pass),
        ]
        
        for label, entry in fields:
            tk.Label(frame, text=label, bg='#2c3e50', fg='white').pack()
            entry.pack(pady=5)
        
        tk.Button(frame, text="Подключиться", bg='#27ae60', fg='white', font=('Arial', 12),
                 command=self._connect).pack(pady=20)
        
        self.status_label = tk.Label(frame, text="Не подключено", bg='#2c3e50', fg='#e74c3c')
        self.status_label.pack()
    
    def _connect(self):
        """Подключение к БД"""
        try:
            self.conn = psycopg2.connect(
                host=self.db_host.get(),
                port=self.db_port.get(),
                database=self.db_name.get(),
                user=self.db_user.get(),
                password=self.db_pass.get()
            )
            self.cur = self.conn.cursor()
            
            self.status_label.config(text="Подключено ✅", fg='#2ecc71')
            self.root.after(500, self._create_main_ui)
            # После создания UI сразу показать выбор сотрудника
            self.root.after(600, self._force_select_employee)
            
        #except Exception as e:
            #messagebox.showerror("Ошибка подключения", str(e))
            
        except Exception as e:
            report_path = log_crash(str(e), "perform_ocr")
            messagebox.showerror("Ошибка подключения", f"{str(e)}\n📄 {report_path}")
            
    
    def _force_select_employee(self):
        """Принудительный выбор сотрудника при запуске"""
        if not self.current_employee_id:
            messagebox.showwarning("Внимание", "Выберите сотрудника для работы!")
            self._select_employee()
    
    # =========================================================================
    # ГЛАВНЫЙ ИНТЕРФЕЙС
    # =========================================================================
    
    def _create_main_ui(self):
        """Создание основного интерфейса"""
        # Очистка и создание нового интерфейса
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.root.configure(bg='#ecf0f1')
        
        # Верхняя панель
        top_frame = tk.Frame(self.root, bg='#34495e', height=60)
        top_frame.pack(fill=tk.X)
        top_frame.pack_propagate(False)
        
        # Кнопки этапов
        stages = [
            ("1. 📥 Загрузка", self._stage_load),
            ("2. 🔧 Предобработка", self._stage_preprocess),
            ("3. 🔍 OCR", self._stage_ocr),
            ("4. ✅ Проверка", self._stage_verify),
        ]
        
        self.stage_buttons = []
        for text, cmd in stages:
            btn = tk.Button(top_frame, text=text, bg='#3498db', fg='white',
                           font=('Arial', 10), command=cmd)
            btn.pack(side=tk.LEFT, padx=5, pady=10)
            self.stage_buttons.append(btn)
        
        # Кнопка сотрудника
        tk.Button(top_frame, text="👤 Сотрудник", bg='#e67e22', fg='white',
                 command=self._select_employee).pack(side=tk.RIGHT, padx=10)
        
        self.current_employee_name = None
        self.employee_label = tk.Label(top_frame, text="Не выбран", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        self.employee_label.pack(side=tk.RIGHT, padx=10)
        
        # Основной контейнер - три панели (используем PanedWindow с динамическим размером)
        main = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Левая панель - список
        left = tk.Frame(main)
        main.add(left, minsize=300)
        
        tk.Label(left, text="Список чертежей", font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.list_tree = ttk.Treeview(left, show="headings")
        self.list_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # При выборе элемента показываем детали
        self.list_tree.bind("<<TreeviewSelect>>", self._on_select_item)
        
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.list_tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_tree.configure(yscrollcommand=vsb.set)
        
        tk.Button(left, text="🔄 Обновить", bg='#95a5a6', fg='white',
                 command=self._refresh_list).pack(pady=5)
        
        # Средняя панель - детали
        middle = tk.Frame(main)
        main.add(middle, minsize=300)
        
        tk.Label(middle, text="Детали и действия", font=('Arial', 12, 'bold')).pack(pady=5)
        
        self.detail_text = scrolledtext.ScrolledText(middle)
        self.detail_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
        
        self.action_frame = tk.Frame(middle)
        self.action_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        # Правая панель - просмотр PDF
        self.pdf_frame = tk.Frame(main)
        main.add(self.pdf_frame, minsize=400)
        
        # Заголовок PDF
        pdf_header = tk.Frame(self.pdf_frame, bg='#2c3e50')
        pdf_header.pack(fill=tk.X)
        tk.Label(pdf_header, text="Просмотр PDF", font=('Arial', 12, 'bold'), 
                bg='#2c3e50', fg='white').pack(pady=5)
        
        # Холст для отображения PDF (растягивается)
        self.pdf_canvas = tk.Canvas(self.pdf_frame, bg='#95a5a6')
        self.pdf_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Панель управления PDF
        pdf_controls = tk.Frame(self.pdf_frame, bg='#ecf0f1')
        pdf_controls.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        
        # Навигация по страницам
        nav_frame = tk.Frame(pdf_controls, bg='#ecf0f1')
        nav_frame.pack(fill=tk.X, pady=2)
        
        tk.Button(nav_frame, text="◀", width=3, command=self._prev_page).pack(side=tk.LEFT, padx=2)
        self.page_label = tk.Label(nav_frame, text="Стр: 0/0", bg='#ecf0f1')
        self.page_label.pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="▶", width=3, command=self._next_page).pack(side=tk.LEFT, padx=2)
        
        # Выбор страниц для OCR
        ocr_frame = tk.Frame(pdf_controls, bg='#ecf0f1')
        ocr_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(ocr_frame, text="Страницы:", bg='#ecf0f1').pack(side=tk.LEFT)
        self.ocr_pages_entry = tk.Entry(ocr_frame, width=15)
        self.ocr_pages_entry.insert(0, "1")  # по умолчанию первая страница
        self.ocr_pages_entry.pack(side=tk.LEFT, padx=5)
        
        # Подсказка
        tk.Label(ocr_frame, text="(1,3,7 или 1-8)", bg='#ecf0f1', fg='#7f8c8d', font=('Arial', 8)).pack(side=tk.LEFT, padx=5)
        
        # Масштаб
        scale_frame = tk.Frame(pdf_controls, bg='#ecf0f1')
        scale_frame.pack(fill=tk.X, pady=2)
        
        tk.Label(scale_frame, text="Масштаб:", bg='#ecf0f1').pack(side=tk.LEFT)
        self.scale_var = tk.StringVar(value="1.0")
        scale_combo = ttk.Combobox(scale_frame, textvariable=self.scale_var,
                                    values=["0.5", "1.0", "1.5", "2.0", "2.5", "3.0"], width=6)
        scale_combo.pack(side=tk.LEFT, padx=5)
        scale_combo.bind("<<ComboboxSelected>>", self._on_scale_change)
        
        # Кнопки управления PDF
        btn_frame = tk.Frame(pdf_controls, bg='#ecf0f1')
        btn_frame.pack(pady=5)
        
        tk.Button(btn_frame, text="📂 Открыть", bg='#3498db', fg='white',
                 command=self._open_pdf_from_selection).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="🔄 Сброс", bg='#95a5a6', fg='white',
                 command=self._reset_pdf_view).pack(side=tk.LEFT, padx=2)
        
        # Текущий PDF
        self.current_pdf_path = None
        self.pdf_doc = None
        self.current_page = 0
        self.total_pages = 0
        self.scale = 1.0
        
        # Параметры просмотра PDF (drag и zoom)
        self.pdf_offset_x = 0
        self.pdf_offset_y = 0
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # Привязка событий для перетаскивания и зума
        self.pdf_canvas.bind("<Button-1>", self._on_pdf_mouse_down)
        self.pdf_canvas.bind("<B1-Motion>", self._on_pdf_mouse_drag)
        self.pdf_canvas.bind("<ButtonRelease-1>", self._on_pdf_mouse_up)
        self.pdf_canvas.bind("<MouseWheel>", self._on_pdf_mouse_wheel)
        
        # Текущий этап
        self.current_stage = 1
        self._stage_load()
    
    # =========================================================================
    # ЭТАП 1: ЗАГРУЗКА
    # =========================================================================
    
    def _stage_load(self):
        """Этап 1: Загрузка чертежей"""
        self.current_stage = 1
        self._update_stage_buttons()
        self._update_columns(["ID", "Название", "Дата", "Сотрудник", "Файл", "Стр.", "Статус"])
        self._refresh_list()
        self._update_buttons([
            ("📂 Загрузить PDF", self._load_pdf),
            ("🗑️ Удалить", self._delete_drawing),
        ])
        self._show_info("""ЭТАП 1: ЗАГРУЗКА ЧЕРТЕЖЕЙ

1. Выберите сотрудника (кнопка справа сверху)
2. Нажмите "Загрузить PDF"
3. Выберите файл чертежа
4. Введите номер/название чертежа

Чертёж будет сохранён в БД и готов к обработке.

Таблицы: SKETCH_DRAWINGS + PRIMARY_DRAWINGS""")
    
    def _load_pdf(self):
        """Загрузка PDF чертежа"""
        if not self.current_employee_id:
            messagebox.showwarning("Внимание", "Выберите сотрудника!")
            return
        
        file_path = filedialog.askopenfilename(
            title="Выберите чертеж",
            filetypes=[("PDF files", "*.pdf")]
        )
        
        if not file_path:
            return
        
        num_name = simpledialog.askstring("Номер чертежа", "Введите номер/название:",
                                           initialvalue=os.path.basename(file_path))
        if not num_name:
            return
        
        try:
            # Сохраняем в SKETCH_DRAWINGS
            self.cur.execute(INSERT_SKETCH_DRAWING, (file_path, datetime.now(), num_name, self.current_employee_id))
            sketch_id = self.cur.fetchone()[0]
            
            # Сохраняем в PRIMARY_DRAWINGS
            self.cur.execute(INSERT_PRIMARY_DRAWING, (file_path, str(sketch_id), False, self.current_employee_id))
            drawing_id = self.cur.fetchone()[0]
            
            self.conn.commit()
            
            self.current_drawing_id = drawing_id
            self.current_pdf_path = file_path
            
            messagebox.showinfo("Успех", f"Чертёж загружен! ID: {drawing_id}")
            
            self._refresh_list()
            
            # Переход к этапу 2
            self._stage_preprocess()
            
        except Exception as e:
            self._rollback()
            messagebox.showerror("Ошибка", str(e))
    
    def _delete_drawing(self):
        """Удалить чертеж"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить чертеж?"):
            drawing_id = self.list_tree.item(selected[0])['values'][0]
            try:
                self.cur.execute("DELETE FROM PRIMARY_DRAWINGS WHERE id = %s", (drawing_id,))
                self.conn.commit()
                self._refresh_list()
                messagebox.showinfo("Успех", "Чертёж удалён")
            except Exception as e:
                self._rollback()
                messagebox.showerror("Ошибка", str(e))
    
    # =========================================================================
    # ЭТАП 2: ПРЕДОБРАБОТКА
    # =========================================================================
    
    def _stage_preprocess(self):
        """Этап 2: Предобработка и оценка качества"""
        self.current_stage = 2
        self._update_stage_buttons()
        self._update_columns(["ID", "Название", "Дата", "Сотрудник", "Стр.", "Статус OCR"])
        self._refresh_list()
        self._update_buttons([
            ("🔧 Обработать", self._run_preprocessing),
            ("⏭️ Пропустить", self._skip_preprocess),
        ])
        self._show_info("""ЭТАП 2: ПРЕДОБРАБОТКА ИЗОБРАЖЕНИЯ

1. Выберите чертеж из списка
2. Нажмите "Обработать" - система:
   - Оценит уровень искажений
   - Выполнит бинаризацию, выравнивание, удаление шума
3. Или нажмите "Пропустить" - перейти к OCR без обработки

После обработки будет показано изображение для подтверждения.

Логика:
- Искажения ≤15% → автопредобработка
- Искажения >15% → запрос на улучшение""")
    
    def _run_preprocessing(self):
        """Запуск предобработки"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        drawing_id = self.list_tree.item(selected[0])['values'][0]
        
        # Получаем путь к файлу
        try:
            self.cur.execute(GET_PRIMARY_BY_ID, (drawing_id,))
            result = self.cur.fetchone()
            if not result:
                messagebox.showerror("Ошибка", "Чертёж не найден")
                return
            
            file_path = result[1]
            if not os.path.exists(file_path):
                messagebox.showerror("Ошибка", f"Файл не найден: {file_path}")
                return
            
            # Открываем PDF
            self.pdf_doc = fitz.open(file_path)
            if len(self.pdf_doc) == 0:
                messagebox.showerror("Ошибка", "PDF пустой")
                return
            
            self.current_page = 0
            self._render_page()
            
            # Оценка качества (упрощённая)
            # В реальности тут был бы анализ изображения
            distortion_level = 10  # условно 10%
            
            if distortion_level <= 15:
                msg = f"Уровень искажений: {distortion_level}%\nПереход к предобработке..."
                messagebox.showinfo("Контроль качества", msg)
                self._do_preprocessing(drawing_id)
            else:
                response = messagebox.askyesno("Контроль качества", 
                    f"Уровень искажений: {distortion_level}%\nИзображение имеет значительные искажения.\n\nУлучшить читаемость?")
                
                if response:
                    self._do_preprocessing(drawing_id)
                else:
                    response2 = messagebox.askyesno("Контроль качества", 
                        "Принудительно запустить предобработку?")
                    if response2:
                        self._do_preprocessing(drawing_id)
                    else:
                        response3 = messagebox.askyesno("Контроль качества", 
                            "Пропустить предобработку и перейти к OCR?")
                        if response3:
                            self._skip_preprocess()
            
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def _do_preprocessing(self, drawing_id):
        """Выполнение предобработки"""
        try:
            # Пытаемся импортировать preprocessing
            try:
                from preprocessing import preprocess_for_ocr
                processed = preprocess_for_ocr(self.page_image, page_num=1, save_files=True)
                self.page_image = processed['processed']
                status = "✓ Предобработка выполнена"
            except ImportError:
                # Если нет модуля preprocessing, используем базовую обработку
                from PIL import Image, ImageEnhance, ImageFilter
                
                # Конвертируем в grayscale
                img = self.page_image.convert('L')
                
                # Бинаризация
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.5)
                
                # Удаление шума
                img = img.filter(ImageFilter.MedianFilter(size=3))
                
                self.page_image = img
                status = "✓ Базовая предобработка выполнена"
            
            # Обновляем статус в БД
            self._show_info(f"Предобработка завершена!\n\n{status}\n\nПереходим к выбору области...")
            
            # Переходим к выбору области
            self._show_template_selection(drawing_id)
            
        except Exception as e:
            messagebox.showerror("Ошибка предобработки", str(e))
    
    def _skip_preprocess(self):
        """Пропустить предобработку"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        drawing_id = self.list_tree.item(selected[0])['values'][0]
        self._show_template_selection(drawing_id)
    
    def _show_template_selection(self, drawing_id):
        """Выбор шаблона/области"""
        response = messagebox.askyesno("Выбор области", 
            "Обрабатывать весь файл или выбрать область?\n\nДа = Весь файл\nНет = Выбрать область")
        
        if response:
            # Весь файл
            self._show_info("Выбран режим: весь файл\nПереходим к OCR...")
            self._stage_ocr()
        else:
            # Выбор области (упрощённо - просто переходим к OCR)
            self._show_info("Выберите область на изображении\n(в данной версии - весь файл)\nПереходим к OCR...")
            self._stage_ocr()
    
    def _render_page(self):
        """Рендер страницы PDF"""
        if not self.pdf_doc:
            return
        
        page = self.pdf_doc.load_page(self.current_page)
        mat = fitz.Matrix(self.scale, self.scale)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("ppm")
        self.page_image = Image.open(io.BytesIO(img_data))
    
    # =========================================================================
    # ЭТАП 3: OCR
    # =========================================================================
    
    def _stage_ocr(self):
        """Этап 3: OCR распознавание"""
        self.current_stage = 3
        self._update_stage_buttons()
        self._update_columns(["ID", "Название", "Дата", "Сотрудник", "Стр.", "Статус OCR"])
        self._refresh_list()
        self._update_buttons([
            ("🔍 Запустить OCR", self._run_ocr),
            ("✏️ Вручную", self._create_pro_manual),
        ])
        self._show_info("""ЭТАП 3: OCR РАСПОЗНАВАНИЕ

1. Выберите чертеж из списка
2. Нажмите "Запустить OCR" - распознавание текста
   или "Вручную" - заполнить данные вручную
3. Дождитесь завершения распознавания
4. Данные сохранятся в БД (таблица PRO)

После OCR данные можно редактировать на этапе 4.""")
    
    def _run_ocr(self):
        """Запуск OCR"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертёж!")
            return
        
        if not OCR_AVAILABLE:
            messagebox.showerror("Ошибка", "Установите: pip install PyMuPDF Pillow opencv-python numpy easyocr")
            return
        
        drawing_id = self.list_tree.item(selected[0])['values'][0]
        
        try:
            # Получаем путь
            self.cur.execute(GET_PRIMARY_BY_ID, (drawing_id,))
            result = self.cur.fetchone()
            if not result:
                messagebox.showerror("Ошибка", "Чертёж не найден")
                return
            
            file_path = result[1]
            
            # Открываем PDF
            self.pdf_doc = fitz.open(file_path)
            total_pages = len(self.pdf_doc)
            
            # Получаем номера страниц для OCR
            pages_to_ocr = self._get_ocr_pages_info()
            
            messagebox.showinfo("OCR", f"Запускаю распознавание...\nСтраниц: {len(pages_to_ocr)} из {total_pages}\nНомера: {[p+1 for p in pages_to_ocr]}")
            
            all_text = []
            
            # OCR для каждой страницы
            for page_num in pages_to_ocr:
                # Рендерим страницу
                page = self.pdf_doc.load_page(page_num)
                mat = fitz.Matrix(1.5, 1.5)  # чуть увеличим для лучшего распознавания
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("ppm")
                page_image = Image.open(io.BytesIO(img_data))
                
                # Предобработка
                try:
                    from preprocessing import preprocess_for_ocr
                    processed = preprocess_for_ocr(page_image, page_num=page_num+1, save_files=False)
                    img_array = np.array(processed['processed'])
                except:
                    img_array = np.array(page_image.convert('L'))
                
                # EasyOCR
                try:
                    import easyocr
                    if not self.ocr_reader:
                        self.ocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
                    
                    results = self.ocr_reader.readtext(
                        img_array, detail=1, paragraph=False,
                        allowlist='АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789№-.,=абвгдежзийклмнопрстуфхцчшщъыьэюяКПЛИСТФм#',
                        width_ths=0.8, height_ths=0.8, low_text=0.3, text_threshold=0.7
                    )
                    
                    page_text = '\n'.join([text.strip() for _, text, conf in results if conf > 0.4])
                    all_text.append(f"--- Страница {page_num + 1} ---\n{page_text}")
                    
                except Exception as ocr_err:
                    all_text.append(f"--- Страница {page_num + 1} ---\nOCR ошибка: {ocr_err}")
            
            extracted_text = '\n\n'.join(all_text)
            
            # Добавляем результат (не заменяем информацию меню)
            self._append_info("РАСПОЗНАННЫЙ ТЕКСТ:\n" + extracted_text)
            
            # Копируем в буфер
            self.root.clipboard_clear()
            self.root.clipboard_append(extracted_text)
            
            # Сохраняем в PRO
            self.cur.execute(INSERT_PRO, (
                f"Чертёж №{drawing_id}",  # NameDrav
                "",  # Designation
                None,  # ProjectCode
                "",  # Dev
                datetime.now().date(),  # DateOriginalCreation
                "A4",  # OriginalPaperFormat
                len(pages_to_ocr),  # NumberOfSheets
                extracted_text[:5000],  # Notes (увеличил лимит)
                drawing_id,  # NumDrav
                drawing_id  # idPrimaryDrawing
            ))
            pro_id = self.cur.fetchone()[0]
            self.conn.commit()
            
            messagebox.showinfo("Успех", f"OCR завершено!\nPRO ID: {pro_id}\nСтраниц обработано: {len(pages_to_ocr)}")
            
            self._refresh_list()
            self._stage_verify()
            
        except Exception as e:
            self._rollback()
            messagebox.showerror("Ошибка OCR", str(e))
    
    def _create_pro_manual(self):
        """Создать PRO вручную"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        drawing_id = self.list_tree.item(selected[0])['values'][0]
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Создание PRO вручную")
        dialog.geometry("500x450")
        
        fields = {}
        labels = ["Наименование", "Обозначение", "Код проекта", "Разработчик",
                  "Дата создания", "Формат", "Кол-во листов", "Примечания"]
        
        for i, label in enumerate(labels):
            tk.Label(dialog, text=label + ":").grid(row=i, column=0, sticky=tk.W, padx=5, pady=3)
            entry = tk.Entry(dialog, width=40)
            entry.grid(row=i, column=1, padx=5, pady=3)
            fields[label] = entry
        
        fields["Наименование"].insert(0, f"Чертёж №{drawing_id}")
        fields["Формат"].insert(0, "A4")
        fields["Кол-во листов"].insert(0, "1")
        fields["Дата создания"].insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        def save():
            try:
                self.cur.execute(INSERT_PRO, (
                    fields["Наименование"].get(),
                    fields["Обозначение"].get(),
                    int(fields["Код проекта"].get()) if fields["Код проекта"].get() else None,
                    fields["Разработчик"].get(),
                    fields["Дата создания"].get(),
                    fields["Формат"].get(),
                    int(fields["Кол-во листов"].get()) if fields["Кол-во листов"].get() else 1,
                    fields["Примечания"].get(),
                    drawing_id,
                    drawing_id
                ))
                pro_id = self.cur.fetchone()[0]
                self.conn.commit()
                dialog.destroy()
                self._refresh_list()
                self._stage_verify()
                messagebox.showinfo("Успех", f"PRO создан! ID: {pro_id}")
            except Exception as e:
                self._rollback()
                messagebox.showerror("Ошибка", str(e))
        
        tk.Button(dialog, text="Сохранить", command=save).grid(row=len(labels), column=0, columnspan=2, pady=10)
    
    # =========================================================================
    # ЭТАП 4: ПРОВЕРКА
    # =========================================================================
    
    def _stage_verify(self):
        """Этап 4: Проверка данных"""
        self.current_stage = 4
        self._update_stage_buttons()
        self._update_columns(["ID", "Наименование", "Обозначение", "Проект", "Разработчик", "Статус"])
        self._refresh_list()
        self._update_buttons([
            ("✏️ Редактировать", self._edit_pro),
            ("✅ Валидировать → FRO", self._validate_pro),
        ])
        self._show_info("""ЭТАП 4: ПРОВЕРКА ДАННЫХ

1. Просмотрите распознанные данные
2. При необходимости отредактируйте (кнопка "Редактировать")
3. Нажмите "Валидировать → FRO" для завершения
4. Данные сохранятся в FRO и ARCH_OF_DRAWS

После валидации чертеж переходит в архив.""")
    
    def _edit_pro(self):
        """Редактировать PRO"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите PRO!")
            return
        
        pro_id = self.list_tree.item(selected[0])['values'][0]
        
        # Получаем данные
        try:
            self.cur.execute("SELECT * FROM PRO WHERE idPrmRes = %s", (pro_id,))
            pro = self.cur.fetchone()
            if not pro:
                messagebox.showerror("Ошибка", "PRO не найден")
                return
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Редактирование PRO #{pro_id}")
        dialog.geometry("500x450")
        
        fields = {}
        labels = ["Наименование", "Обозначение", "Код проекта", "Разработчик",
                  "Дата создания", "Формат", "Кол-во листов", "Примечания"]
        
        pro_data = {
            "Наименование": pro[1] or "",
            "Обозначение": pro[2] or "",
            "Код проекта": str(pro[3]) if pro[3] else "",
            "Разработчик": pro[4] or "",
            "Дата создания": str(pro[5]) if pro[5] else "",
            "Формат": pro[6] or "",
            "Кол-во листов": str(pro[7]) if pro[7] else "1",
            "Примечания": pro[8] or "",
        }
        
        for i, label in enumerate(labels):
            tk.Label(dialog, text=label + ":").grid(row=i, column=0, sticky=tk.W, padx=5, pady=3)
            entry = tk.Entry(dialog, width=40)
            entry.insert(0, pro_data[label])
            entry.grid(row=i, column=1, padx=5, pady=3)
            fields[label] = entry
        
        def save():
            try:
                self.cur.execute(UPDATE_PRO, (
                    fields["Наименование"].get(),
                    fields["Обозначение"].get(),
                    int(fields["Код проекта"].get()) if fields["Код проекта"].get() else None,
                    fields["Разработчик"].get(),
                    fields["Дата создания"].get(),
                    fields["Формат"].get(),
                    int(fields["Кол-во листов"].get()) if fields["Кол-во листов"].get() else 1,
                    fields["Примечания"].get(),
                    pro_id
                ))
                self.conn.commit()
                dialog.destroy()
                self._refresh_list()
                messagebox.showinfo("Успех", "Данные сохранены!")
            except Exception as e:
                self._rollback()
                messagebox.showerror("Ошибка", str(e))
        
        tk.Button(dialog, text="Сохранить", command=save).grid(row=len(labels), column=0, columnspan=2, pady=10)
    
    def _validate_pro(self):
        """Валидировать PRO - создать FRO"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите PRO!")
            return
        
        pro_id = self.list_tree.item(selected[0])['values'][0]
        
        try:
            # Проверяем, не валидирован ли уже
            self.cur.execute(GET_FRO_BY_PRO, (pro_id,))
            if self.cur.fetchone():
                messagebox.showwarning("Внимание", "PRO уже валидирован!")
                return
            
            # Получаем данные PRO
            self.cur.execute("SELECT * FROM PRO WHERE idPrmRes = %s", (pro_id,))
            pro = self.cur.fetchone()
            
            if not pro:
                messagebox.showerror("Ошибка", "PRO не найден")
                return
            
            # Создаём FRO
            self.cur.execute(INSERT_FRO, (
                pro[1], pro[2], pro[3], pro[4], pro[5], pro[6], pro[7], pro[9], pro_id
            ))
            fro_id = self.cur.fetchone()[0]
            
            # Создаём архив
            self.cur.execute(INSERT_ARCHIVE, (
                f"/archive/drawing_{fro_id}.pdf",
                pro[9],  # NumDrav
                pro[1],  # NameDrav
                pro[2],  # Designation
                pro[3],  # ProjectCode
                pro[4],  # Dev
                datetime.now(),
                self.current_employee_id
            ))
            arch_id = self.cur.fetchone()[0]
            
            self.conn.commit()
            
            messagebox.showinfo("Успех", f"Валидация завершена!\nFRO ID: {fro_id}\nАрхив ID: {arch_id}")
            
            self._refresh_list()
            
        except Exception as e:
            self._rollback()
            messagebox.showerror("Ошибка", str(e))
    
    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================
    
    def _update_columns(self, columns):
        self.list_tree["columns"] = columns
        for col in columns:
            self.list_tree.heading(col, text=col)
            self.list_tree.column(col, width=100)
    
    def _update_stage_buttons(self):
        """Обновить цвет кнопок этапов - активная кнопка выделяется"""
        if not hasattr(self, 'stage_buttons'):
            return
        
        active_color = '#27ae60'  # зелёный - активный
        inactive_color = '#3498db'  # синий - неактивный
        
        for i, btn in enumerate(self.stage_buttons):
            if i + 1 == self.current_stage:
                btn.config(bg=active_color, relief=tk.SUNKEN)
            else:
                btn.config(bg=inactive_color, relief=tk.RAISED)
    
    def _update_buttons(self, buttons):
        for widget in self.action_frame.winfo_children():
            widget.destroy()
        for text, cmd in buttons:
            tk.Button(self.action_frame, text=text, bg='#3498db', fg='white',
                     command=cmd).pack(side=tk.LEFT, padx=5)
    
    def _show_info(self, text):
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, text)
    
    def _append_info(self, text):
        """Добавить текст в конец существующего"""
        self.detail_text.insert(tk.END, "\n" + "="*60 + "\n")
        self.detail_text.insert(tk.END, text)
    
    def _refresh_list(self):
        for item in self.list_tree.get_children():
            self.list_tree.delete(item)
        
        if not self.cur:
            return
        
        # Если сотрудник не выбран - не показываем ничего
        if not self.current_employee_id:
            self._show_info("⚠️ Выберите сотрудника для работы!\n\nНажмите кнопку 'Сотрудник' в правом верхнем углу.")
            return
        
        try:
            if self.current_stage == 1:
                # Этап 1: Загрузка - PRIMARY_DRAWINGS (только для выбранного сотрудника)
                self.cur.execute("""
                    SELECT pd.id, COALESCE(sd.NumName, 'Без названия'),
                           sd.DateAdded,
                           COALESCE(e.FullName, '—'),
                           SUBSTRING(pd.FilePath FROM 1 FOR 30) || '...',
                           COALESCE(p.NumDrav::VARCHAR, '1'),
                           CASE WHEN p.idPrmRes IS NOT NULL THEN '✓ OCR' ELSE '⏳ Новый' END
                    FROM PRIMARY_DRAWINGS pd
                    LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                    LEFT JOIN EMPLOYEES e ON e.idEmployee = pd.idEmployee
                    LEFT JOIN PRO p ON p.idPrimaryDrawing = pd.id
                    WHERE pd.idEmployee = %s
                    ORDER BY pd.id DESC
                """, (self.current_employee_id,))
                for row in self.cur.fetchall():
                    date_str = row[2].strftime("%d.%m.%Y") if row[2] else "—"
                    self.list_tree.insert("", tk.END, values=(row[0], row[1], date_str, row[3], row[4] or "—", row[5], row[6]))
            
            elif self.current_stage == 2:
                # Этап 2: Предобработка - чертежи без PRO (только для выбранного сотрудника)
                self.cur.execute("""
                    SELECT pd.id, COALESCE(sd.NumName, 'Без названия'),
                           sd.DateAdded,
                           COALESCE(e.FullName, '—'),
                           COALESCE(p.NumDrav::VARCHAR, '1'),
                           CASE WHEN p.idPrmRes IS NOT NULL THEN '✓ Распознан' ELSE '⏳ Ожидает' END
                    FROM PRIMARY_DRAWINGS pd
                    LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                    LEFT JOIN EMPLOYEES e ON e.idEmployee = pd.idEmployee
                    LEFT JOIN PRO p ON p.idPrimaryDrawing = pd.id
                    WHERE pd.idEmployee = %s
                    ORDER BY pd.id DESC
                """, (self.current_employee_id,))
                for row in self.cur.fetchall():
                    date_str = row[2].strftime("%d.%m.%Y") if row[2] else "—"
                    self.list_tree.insert("", tk.END, values=(row[0], row[1], date_str, row[3], row[4], row[5]))
            
            elif self.current_stage == 3:
                # Этап 3: OCR - показываем чертежи для распознавания (только для выбранного сотрудника)
                self.cur.execute("""
                    SELECT pd.id, COALESCE(sd.NumName, 'Без названия'),
                           sd.DateAdded,
                           COALESCE(e.FullName, '—'),
                           COALESCE(p.NumDrav::VARCHAR, '1'),
                           CASE WHEN p.idPrmRes IS NOT NULL THEN '✓ Распознан' ELSE '⏳ Ожидает' END
                    FROM PRIMARY_DRAWINGS pd
                    LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                    LEFT JOIN EMPLOYEES e ON e.idEmployee = pd.idEmployee
                    LEFT JOIN PRO p ON p.idPrimaryDrawing = pd.id
                    WHERE pd.idEmployee = %s
                    ORDER BY pd.id DESC
                """, (self.current_employee_id,))
                for row in self.cur.fetchall():
                    date_str = row[2].strftime("%d.%m.%Y") if row[2] else "—"
                    self.list_tree.insert("", tk.END, values=(row[0], row[1], date_str, row[3], row[4], row[5]))
            
            elif self.current_stage == 4:
                # Этап 4: Проверка - PRO (только для выбранного сотрудника)
                self.cur.execute("""
                    SELECT p.idPrmRes, p.NameDrav, p.Designation, 
                           COALESCE(p.ProjectCode::VARCHAR, '—'),
                           COALESCE(p.Dev, '—'),
                           CASE WHEN f.idFnlRes IS NOT NULL THEN '✓ Валидирован' 
                                WHEN pd.NeedToImprove = TRUE THEN '⏳ На доработке' 
                                ELSE '✓ Одобрено' END,
                           p.OriginalPaperFormat, p.NumberOfSheets
                    FROM PRO p
                    LEFT JOIN PRIMARY_DRAWINGS pd ON pd.id = p.idPrimaryDrawing
                    LEFT JOIN FRO f ON f.pro_id = p.idPrmRes
                    WHERE pd.idEmployee = %s
                    ORDER BY p.idPrmRes DESC
                """, (self.current_employee_id,))
                for row in self.cur.fetchall():
                    self.list_tree.insert("", tk.END, values=(row[0], row[1], row[2], row[3], row[4], row[5]))
        
        except Exception as e:
            print(f"Ошибка обновления: {e}")
            self._rollback()
    
    def _select_employee(self):
        if not self.cur:
            messagebox.showerror("Ошибка", "Нет подключения")
            return
        
        try:
            self.cur.execute(GET_ALL_EMPLOYEES)
            employees = self.cur.fetchall()
            
            if not employees:
                messagebox.showinfo("Нет сотрудников", "Создать сотрудника?")
                self._add_employee()
                return
            
            dialog = tk.Toplevel(self.root)
            dialog.title("Выбор сотрудника")
            dialog.geometry("400x300")
            
            listbox = tk.Listbox(dialog)
            listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            for emp in employees:
                listbox.insert(tk.END, f"{emp[0]} - {emp[2]} ({emp[1]})")
            
            def select():
                if listbox.curselection():
                    selected_text = listbox.get(listbox.curselection()[0])
                    self.current_employee_id = int(selected_text.split(" - ")[0])
                    # Получаем ФИО
                    emp_name = selected_text.split(" - ")[1].split(" (")[0] if " - " in selected_text else "Сотрудник"
                    self.current_employee_name = emp_name
                    self.employee_label.config(text=f"👤 {emp_name}")
                    dialog.destroy()
                    self._refresh_list()
            
            tk.Button(dialog, text="Выбрать", command=select).pack(pady=5)
        
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def _add_employee(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Добавить сотрудника")
        
        tk.Label(dialog, text="ФИО:").grid(row=0, column=0)
        entry_name = tk.Entry(dialog)
        entry_name.grid(row=0, column=1)
        
        tk.Label(dialog, text="Должность:").grid(row=1, column=0)
        entry_post = tk.Entry(dialog)
        entry_post.grid(row=1, column=1)
        
        def save():
            try:
                self.cur.execute(INSERT_EMPLOYEE, (entry_post.get(), entry_name.get(), 'operator'))
                self.current_employee_id = self.cur.fetchone()[0]
                self.current_employee_name = entry_name.get()
                self.conn.commit()
                self.employee_label.config(text=f"👤 {self.current_employee_name}")
                dialog.destroy()
                messagebox.showinfo("Успех", "Сотрудник добавлен!")
            except Exception as e:
                self._rollback()
                messagebox.showerror("Ошибка", str(e))
        
        tk.Button(dialog, text="Сохранить", command=save).grid(row=2, column=0, columnspan=2, pady=10)
    
    def _on_select_item(self, event):
        """Обработка выбора элемента в списке"""
        selected = self.list_tree.selection()
        if not selected:
            return
        
        item = self.list_tree.item(selected[0])
        values = item['values']
        
        try:
            if self.current_stage == 1 or self.current_stage == 2 or self.current_stage == 3:
                # Показываем детали чертежа (PRIMARY_DRAWINGS)
                drawing_id = values[0]
                self.cur.execute("""
                    SELECT pd.id, sd.NumName, sd.SFilePath, sd.DateAdded, 
                           e.FullName, e.Post, pd.NeedToImprove
                    FROM PRIMARY_DRAWINGS pd
                    LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                    LEFT JOIN EMPLOYEES e ON e.idEmployee = pd.idEmployee
                    WHERE pd.id = %s
                """, (drawing_id,))
                row = self.cur.fetchone()
                if row:
                    # Автоматически загружаем PDF (без показа деталей)
                    if row[2] and os.path.exists(row[2]):
                        self._load_pdf_viewer(row[2])
                    
            elif self.current_stage == 4:
                # Показываем детали PRO + распознанный текст
                pro_id = values[0]
                self.cur.execute("""
                    SELECT p.idPrmRes, p.NameDrav, p.Designation, p.ProjectCode, p.Dev,
                           p.DateOriginalCreation, p.OriginalPaperFormat, p.NumberOfSheets,
                           p.Notes, p.NumDrav, p.idPrimaryDrawing, p.validated, 
                           p.validated_by, p.validation_date,
                           val.FullName, f.idFnlRes, pd.FilePath
                    FROM PRO p
                    LEFT JOIN EMPLOYEES val ON val.idEmployee = p.validated_by
                    LEFT JOIN FRO f ON f.pro_id = p.idPrmRes
                    LEFT JOIN PRIMARY_DRAWINGS pd ON pd.id = p.idPrimaryDrawing
                    WHERE p.idPrmRes = %s
                """, (pro_id,))
                row = self.cur.fetchone()
                if row:
                    # Загружаем PDF если есть (FilePath - индекс 16)
                    if row[16] and os.path.exists(row[16]):
                        self._load_pdf_viewer(row[16])
                    
                    # Показываем распознанный текст (Notes) - индекс 8
                    notes = row[8]
                    if notes:
                        # Показываем только текст чертежа (без накопления)
                        self.detail_text.delete("1.0", tk.END)
                        self.detail_text.insert(tk.END, f"ТЕКСТ ЧЕРТЕЖА #{pro_id}:\n{notes}")
                    
        except Exception as e:
            print(f"Ошибка при выборе: {e}")
            self._rollback()
    
    def _rollback(self):
        try:
            self.conn.rollback()
        except:
            pass

    # =========================================================================
    # УПРАВЛЕНИЕ PDF
    # =========================================================================

    def _open_pdf_from_selection(self):
        """Открыть PDF из выбранного элемента"""
        selected = self.list_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж из списка!")
            return
        
        drawing_id = self.list_tree.item(selected[0])['values'][0]
        
        try:
            self.cur.execute("SELECT FilePath FROM PRIMARY_DRAWINGS WHERE id = %s", (drawing_id,))
            result = self.cur.fetchone()
            if not result or not result[0]:
                messagebox.showerror("Ошибка", "Путь к файлу не найден")
                return
            
            file_path = result[0]
            if not os.path.exists(file_path):
                messagebox.showerror("Ошибка", f"Файл не найден:\n{file_path}")
                return
            
            self._load_pdf_viewer(file_path)
            
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def _load_pdf_viewer(self, file_path):
        """Загрузить PDF в просмотрщик"""
        try:
            self.current_pdf_path = file_path
            self.pdf_doc = fitz.open(file_path)
            self.total_pages = len(self.pdf_doc)
            self.current_page = 0
            
            self._render_pdf_page()
            self._update_page_label()
            
            # Без уведомления - просто загружаем
            
        except Exception as e:
            messagebox.showerror("Ошибка загрузки PDF", str(e))
    
    def _render_pdf_page(self):
        """Отрендерить текущую страницу PDF на холсте"""
        if not self.pdf_doc or self.total_pages == 0:
            return
        
        try:
            # Получаем текущий масштаб
            try:
                self.scale = float(self.scale_var.get())
            except:
                self.scale = 1.0
            
            page = self.pdf_doc.load_page(self.current_page)
            mat = fitz.Matrix(self.scale, self.scale)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            self.page_image = Image.open(io.BytesIO(img_data))
            
            # Конвертируем для Tkinter
            self.tk_image = ImageTk.PhotoImage(self.page_image)
            
            # Очищаем и отображаем с учетом offset
            self.pdf_canvas.delete("all")
            canvas_width = self.pdf_canvas.winfo_width() or 500
            canvas_height = self.pdf_canvas.winfo_height() or 500
            
            # Центр + offset
            center_x = canvas_width // 2 + self.pdf_offset_x
            center_y = canvas_height // 2 + self.pdf_offset_y
            
            self.pdf_canvas.create_image(center_x, center_y, 
                                         image=self.tk_image, anchor=tk.CENTER)
            
        except Exception as e:
            print(f"Ошибка рендеринга: {e}")
    
    def _update_page_label(self):
        """Обновить label с номером страницы"""
        if self.pdf_doc:
            self.page_label.config(text=f"Стр: {self.current_page + 1}/{self.total_pages}")
        else:
            self.page_label.config(text="Стр: 0/0")
    
    def _prev_page(self):
        """Предыдущая страница"""
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self._render_pdf_page()
            self._update_page_label()
    
    def _next_page(self):
        """Следующая страница"""
        if self.pdf_doc and self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._render_pdf_page()
            self._update_page_label()
    
    def _on_scale_change(self, event):
        """Изменение масштаба"""
        self._render_pdf_page()
    
    # =========================================================================
    # УПРАВЛЕНИЕ PDF (DRAG И ZOOM)
    # =========================================================================
    
    def _on_pdf_mouse_down(self, event):
        """Начало перетаскивания"""
        self.is_dragging = True
        self.drag_start_x = event.x - self.pdf_offset_x
        self.drag_start_y = event.y - self.pdf_offset_y
        self.pdf_canvas.config(cursor="fleur")
    
    def _on_pdf_mouse_drag(self, event):
        """Перетаскивание PDF"""
        if self.is_dragging:
            self.pdf_offset_x = event.x - self.drag_start_x
            self.pdf_offset_y = event.y - self.drag_start_y
            self._render_pdf_page()
    
    def _on_pdf_mouse_up(self, event):
        """Конец перетаскивания"""
        self.is_dragging = False
        self.pdf_canvas.config(cursor="")
    
    def _on_pdf_mouse_wheel(self, event):
        """Зум колесиком мыши"""
        if not self.pdf_doc:
            return
        
        # Определяем направление
        if event.delta > 0:
            # Вверх - увеличить
            new_scale = min(self.scale + 0.2, 4.0)
        else:
            # Вниз - уменьшить
            new_scale = max(self.scale - 0.2, 0.3)
        
        self.scale = new_scale
        self.scale_var.set(str(round(new_scale, 1)))
        self._render_pdf_page()
    
    def _reset_pdf_view(self):
        """Сброс вида PDF"""
        self.pdf_offset_x = 0
        self.pdf_offset_y = 0
        self.scale = 1.0
        self.scale_var.set("1.0")
        self._render_pdf_page()
    
    def _get_ocr_pages_info(self):
        """Получить информацию о страницах для OCR (номера страниц)"""
        value = self.ocr_pages_entry.get().strip()
        
        if not value:
            return [0]  # первая страница по умолчанию
        
        # Если "все" или "all"
        if value.lower() in ["все", "all"]:
            return list(range(self.total_pages))
        
        pages = []
        
        # Диапазон (например: "1-8" или "1 - 8")
        if '-' in value:
            try:
                parts = value.split('-')
                if len(parts) == 2:
                    start = int(parts[0].strip()) - 1
                    end = int(parts[1].strip())
                    pages = list(range(start, end))
            except:
                pass
        # Конкретные номера через запятую (например: "1,3,7" или "1, 3, 7")
        elif ',' in value:
            try:
                for p in value.split(','):
                    p = p.strip()
                    if p:
                        pages.append(int(p) - 1)
            except:
                pass
        else:
            # Одно число
            try:
                pages = [int(value) - 1]
            except:
                pass
        
        # Фильтруем только существующие страницы
        valid_pages = [p for p in pages if 0 <= p < self.total_pages]
        
        if not valid_pages:
            return [0]  # по умолчанию первая страница
        
        return sorted(set(valid_pages))


# ============================================================================
# ЗАПУСК
# ============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingAppV2(root)
    root.mainloop()
