# -*- coding: utf-8 -*-
"""
Единое приложение для распознавания чертежей с интеграцией PostgreSQL
Точка входа: python db_app.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import psycopg2
from datetime import datetime
import os
import sys
import io

# Импорт модулей для OCR
try:
    import fitz  # PyMuPDF
    import numpy as np
    from PIL import Image, ImageTk
    import cv2
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Внимание: Для OCR установите pip install PyMuPDF Pillow opencv-python numpy easyocr")

# SQL-запросы (исправленные)
from db_queries_fixed import (
    INSERT_SKETCH_DRAWING, INSERT_PRIMARY_DRAWING,
    GET_ALL_SKETCHES, GET_PRIMARY_DRAWINGS_BY_EMPLOYEE, GET_ALL_PRIMARY_DRAWINGS,
    GET_PRIMARY_DRAWING_BY_ID,
    INSERT_PRO_RESULT, GET_ALL_PRO, GET_PRO_BY_DRAWING, GET_PRO_BY_ID,
    INSERT_DRAWING_VERSION, UPDATE_DRAWING_NEED_IMPROVE, GET_DRAWINGS_NEED_IMPROVE,
    INSERT_FRO_RESULT, GET_FRO_BY_PRO, GET_ALL_FRO, GET_FRO_BY_ID,
    INSERT_ARCHIVE, GET_ALL_ARCHIVES,
    GET_ALL_EMPLOYEES, INSERT_EMPLOYEE,
    GET_ALL_TEMPLATES, INSERT_TEMPLATE,
    GET_DRAWINGS_STATISTICS, GET_EMPLOYEE_STATISTICS, GET_UNVALIDATED_PRO,
)

# Удаляем несуществующие запросы
UPDATE_PRO_VALIDATED = None  # Поля validated нет в текущей структуре БД


class DrawingApp:
    """Главное приложение для работы с чертежами и БД"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Система распознавания чертежей")
        self.root.geometry("1400x900")
        
        # Подключение к БД (одно на всё приложение!)
        self.db_config = {
            'host': 'localhost',
            'database': 'shuvi_test',
            'user': 'postgres',
            'password': 'postgres'
        }
        self.conn = None
        self.cur = None
        
        # Текущее состояние
        self.current_employee_id = None
        self.current_drawing_id = None
        self.current_pdf_path = None
        self.pdf_doc = None
        self.current_page = 0
        self.total_pages = 0
        self.scale = 1.0
        
        # Для OCR
        self.page_image = None
        self.ocr_reader = None
        
        # Создание интерфейса
        self._init_styles()
        self._create_connection_frame()
        self._create_main_ui()
        
        # Подключение к БД
        self._connect_db()
    
    # =========================================================================
    # ПОДКЛЮЧЕНИЕ К БД (ОДНО НА ВСЁ!)
    # =========================================================================
    
    def _init_styles(self):
        """Настройка стилей"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Цвета для этапов
        self.stage_colors = {
            1: '#3498db',  # Синий - Загрузка
            2: '#9b59b6',  # Фиолетовый - OCR
            3: '#e67e22',  # Оранжевый - Проверка
            4: '#27ae60',  # Зелёный - Валидация
            5: '#e74c3c',  # Красный - Архив
        }
    
    def _create_connection_frame(self):
        """Панель подключения к БД"""
        conn_frame = tk.Frame(self.root, bg='#2c3e50', height=50)
        conn_frame.pack(fill=tk.X)
        conn_frame.pack_propagate(False)
        
        # Метка
        tk.Label(conn_frame, text="📁", bg='#2c3e50', fg='white', font=('Arial', 14)).pack(side=tk.LEFT, padx=10)
        
        # Поля подключения
        tk.Label(conn_frame, text="Хост:", bg='#2c3e50', fg='white').pack(side=tk.LEFT)
        self.host_entry = tk.Entry(conn_frame, width=10)
        self.host_entry.insert(0, self.db_config['host'])
        self.host_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(conn_frame, text="БД:", bg='#2c3e50', fg='white').pack(side=tk.LEFT)
        self.db_entry = tk.Entry(conn_frame, width=10)
        self.db_entry.insert(0, self.db_config['database'])
        self.db_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(conn_frame, text="Пользователь:", bg='#2c3e50', fg='white').pack(side=tk.LEFT)
        self.user_entry = tk.Entry(conn_frame, width=10)
        self.user_entry.insert(0, self.db_config['user'])
        self.user_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(conn_frame, text="Пароль:", bg='#2c3e50', fg='white').pack(side=tk.LEFT)
        self.pass_entry = tk.Entry(conn_frame, width=10, show='*')
        self.pass_entry.insert(0, self.db_config['password'])
        self.pass_entry.pack(side=tk.LEFT, padx=5)
        
        # Кнопки
        tk.Button(conn_frame, text="Подключиться", bg='#27ae60', fg='white',
                 command=self._connect_db).pack(side=tk.LEFT, padx=10)
        
        # Статус
        self.status_label = tk.Label(conn_frame, text="Не подключено", 
                                     bg='#e74c3c', fg='white', width=15)
        self.status_label.pack(side=tk.RIGHT, padx=10, fill=tk.X)
        
        # Информация о сотруднике
        self.employee_label = tk.Label(conn_frame, text="Сотрудник: не выбран",
                                       bg='#2c3e50', fg='yellow')
        self.employee_label.pack(side=tk.RIGHT, padx=20)
    
    def _connect_db(self):
        """Подключение к PostgreSQL"""
        try:
            self.db_config['host'] = self.host_entry.get()
            self.db_config['database'] = self.db_entry.get()
            self.db_config['user'] = self.user_entry.get()
            self.db_config['password'] = self.pass_entry.get()
            
            # Закрываем старое подключение если есть
            if self.cur:
                self.cur.close()
            if self.conn:
                self.conn.close()
            
            # Новое подключение
            self.conn = psycopg2.connect(**self.db_config)
            self.cur = self.conn.cursor()
            
            # Таблицы уже созданы в БД
            self.status_label.config(text="Подключено ✅", bg='#27ae60')
            messagebox.showinfo("Успех", "Подключено к БД!")
            
            # Автообновление
            self._refresh_all()
            
        except Exception as e:
            self.status_label.config(text="Ошибка", bg='#e74c3c')
            messagebox.showerror("Ошибка подключения", str(e))
    
    # =========================================================================
    # ГЛАВНЫЙ ИНТЕРФЕЙС
    # =========================================================================
    
    def _create_main_ui(self):
        """Создание основного интерфейса"""
        # Верхняя панель с этапами
        stages_frame = tk.Frame(self.root, bg='#ecf0f1', height=60)
        stages_frame.pack(fill=tk.X, padx=10, pady=5)
        stages_frame.pack_propagate(False)
        
        # Кнопки этапов
        stages = [
            (1, "📥 Загрузка", self._show_stage_load),
            (2, "🔍 OCR", self._show_stage_ocr),
            (3, "✏️ Проверка", self._show_stage_quality),
            (4, "✅ Валидация", self._show_stage_validation),
            (5, "📦 Архив", self._show_stage_archive),
        ]
        
        for num, text, cmd in stages:
            btn = tk.Button(stages_frame, text=text, bg=self.stage_colors[num], fg='white',
                           font=('Arial', 10, 'bold'), width=15, height=2, command=cmd)
            btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Кнопка выбора сотрудника
        tk.Button(stages_frame, text="👤 Выбрать сотрудника", bg='#34495e', fg='white',
                 command=self._select_employee).pack(side=tk.RIGHT, padx=10)
        
        # Основной контейнер
        self.main_container = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Левая панель - список данных
        left_panel = tk.Frame(self.main_container, width=400)
        self.main_container.add(left_panel, width=400)
        
        tk.Label(left_panel, text="Список данных", font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Таблица
        self.data_tree = ttk.Treeview(left_panel, show="headings", height=25)
        self.data_tree.pack(fill=tk.BOTH, expand=True)
        
        vsb = ttk.Scrollbar(left_panel, orient="vertical", command=self.data_tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.data_tree.configure(yscrollcommand=vsb.set)
        
        # Обновить
        tk.Button(left_panel, text="🔄 Обновить", bg='#95a5a6', fg='white',
                 command=self._refresh_all).pack(pady=5)
        
        # Правая панель - детали и действия
        right_panel = tk.Frame(self.main_container)
        self.main_container.add(right_panel)
        
        tk.Label(right_panel, text="Детали и действия", font=('Arial', 12, 'bold')).pack(pady=5)
        
        # Текстовая область для деталей
        self.detail_text = scrolledtext.ScrolledText(right_panel, height=30, width=60)
        self.detail_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Кнопки действий
        self.action_frame = tk.Frame(right_panel)
        self.action_frame.pack(fill=tk.X, pady=5)
        
        # Текущая вкладка
        self.current_stage = 1
        self._show_stage_load()
    
    # =========================================================================
    # НАВИГАЦИЯ ПО ЭТАПАМ
    # =========================================================================
    
    def _show_stage_load(self):
        """Этап 1: Загрузка"""
        self.current_stage = 1
        self._update_tree_columns(["ID", "Название", "Дата загрузки", "Путь к файлу"])
        self._refresh_data_list()
        self._update_action_buttons([
            ("📂 Загрузить чертеж", self._load_drawing),
            ("🗑️ Удалить", self._delete_selected),
        ])
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, "ЭТАП 1: ЗАГРУЗКА ЧЕРТЕЖА\n\n")
        self.detail_text.insert(tk.END, "1. Выберите сотрудника (кнопка справа)\n")
        self.detail_text.insert(tk.END, "2. Нажмите 'Загрузить чертеж'\n")
        self.detail_text.insert(tk.END, "3. Выберите PDF-файл чертежа\n")
        self.detail_text.insert(tk.END, "4. Введите номер/название чертежа\n\n")
        self.detail_text.insert(tk.END, "Чертеж будет сохранён в БД и готов к OCR.")
    
    def _show_stage_ocr(self):
        """Этап 2: OCR"""
        self.current_stage = 2
        # Показываем первичные чертежи (из PRIMARY_DRAWINGS)
        self._update_tree_columns(["ID", "Название", "Дата загрузки", "Статус OCR"])
        self._refresh_data_list()
        self._update_action_buttons([
            ("🔍 Запустить OCR", self._run_ocr),
            ("✏️ Создать вручную", self._create_pro_manual),
        ])
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, "ЭТАП 2: OCR РАСПОЗНАВАНИЕ\n\n")
        self.detail_text.insert(tk.END, "1. Выберите чертеж из списка\n")
        self.detail_text.insert(tk.END, "2. Нажмите 'Запустить OCR' или 'Создать вручную'\n")
        self.detail_text.insert(tk.END, "3. Дождитесь распознавания / заполните данные\n")
        self.detail_text.insert(tk.END, "4. Данные сохранятся в БД\n")
    
    def _show_stage_quality(self):
        """Этап 3: Проверка качества"""
        self.current_stage = 3
        # Показываем PRO для проверки качества
        self._update_tree_columns(["ID", "Наименование", "Обозначение", "Статус"])
        self._refresh_data_list()
        self._update_action_buttons([
            ("✅ Качество ОК", self._mark_quality_ok),
            ("❌ Требует исправления", self._mark_quality_bad),
        ])
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, "ЭТАП 3: ПРОВЕРКА КАЧЕСТВА\n\n")
        self.detail_text.insert(tk.END, "Просмотр результатов OCR (PRO).\n")
        self.detail_text.insert(tk.END, "Выберите PRO и подтвердите качество или отправьте на доработку.")
    
    def _show_stage_validation(self):
        """Этап 4: Валидация"""
        self.current_stage = 4
        self._update_tree_columns(["ID", "Наименование", "Обозначение", "Валидирован"])
        self._refresh_data_list()
        self._update_action_buttons([
            ("✓ Валидировать", self._validate_pro),
        ])
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, "ЭТАП 4: ВАЛИДАЦИЯ\n\n")
        self.detail_text.insert(tk.END, "Выберите результат OCR и валидируйте его.\n")
        self.detail_text.insert(tk.END, "Валидированные данные пойдут в архив.")
    
    def _show_stage_archive(self):
        """Этап 5: Архив"""
        self.current_stage = 5
        self._update_tree_columns(["ID", "Наименование", "Обозначение", "Дата архива"])
        self._refresh_data_list()
        self._update_action_buttons([
            ("📦 Архивировать", self._archive_fro),
        ])
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert(tk.END, "ЭТАП 5: АРХИВ\n\n")
        self.detail_text.insert(tk.END, "Выберите валидированный чертеж для архивации.")
    
    # =========================================================================
    # РАБОТА С ДАННЫМИ
    # =========================================================================
    
    def _update_tree_columns(self, columns):
        """Обновить колонки таблицы"""
        self.data_tree["columns"] = columns
        for col in columns:
            self.data_tree.heading(col, text=col)
            self.data_tree.column(col, width=100)
    
    def _update_action_buttons(self, buttons):
        """Обновить кнопки действий"""
        for widget in self.action_frame.winfo_children():
            widget.destroy()
        
        for text, cmd in buttons:
            tk.Button(self.action_frame, text=text, bg='#3498db', fg='white',
                     command=cmd).pack(side=tk.LEFT, padx=5)
    
    def _refresh_all(self):
        """Обновить все данные"""
        self._refresh_data_list()
        self._refresh_employee_info()
    
    def _refresh_data_list(self):
        """Обновить список данных в зависимости от этапа"""
        if not self.cur:
            return
        
        # Очистка
        for item in self.data_tree.get_children():
            self.data_tree.delete(item)
        
        try:
            if self.current_stage == 1:
                # Загрузка - первичные чертежи с названием из SKETCH_DRAWINGS
                # Связь: pd.AssociatedWith = sd.idSkDrav
                if self.current_employee_id:
                    self.cur.execute("""
                        SELECT pd.id, COALESCE(sd.NumName, 'Без названия'), 
                               COALESCE(sd.DateAdded, pd.created_at), pd.FilePath
                        FROM PRIMARY_DRAWINGS pd
                        LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                        WHERE pd.idEmployee = %s
                        ORDER BY pd.id DESC
                    """, (self.current_employee_id,))
                else:
                    self.cur.execute("""
                        SELECT pd.id, COALESCE(sd.NumName, 'Без названия'), 
                               COALESCE(sd.DateAdded, pd.created_at), pd.FilePath
                        FROM PRIMARY_DRAWINGS pd
                        LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                        ORDER BY pd.id DESC
                    """)
                
                for row in self.cur.fetchall():
                    date_str = row[2].strftime("%d.%m.%Y %H:%M") if row[2] else "—"
                    self.data_tree.insert("", tk.END, values=(
                        row[0], row[1], date_str, row[3][:50] + "..." if row[3] and len(row[3]) > 50 else row[3] or ""
                    ))
            
            elif self.current_stage == 2:
                # OCR - первичные чертежи с проверкой статуса OCR
                # Связь: pd.AssociatedWith = sd.idSkDrav
                if self.current_employee_id:
                    self.cur.execute("""
                        SELECT pd.id, COALESCE(sd.NumName, 'Без названия'), 
                               COALESCE(sd.DateAdded, pd.created_at),
                               CASE WHEN p.idPrmRes IS NOT NULL THEN '✓ Распознан' ELSE '⏳ Ожидает' END
                        FROM PRIMARY_DRAWINGS pd
                        LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                        LEFT JOIN PRO p ON p.idPrimaryDrawing = pd.id
                        WHERE pd.idEmployee = %s
                        ORDER BY pd.id DESC
                    """, (self.current_employee_id,))
                else:
                    self.cur.execute("""
                        SELECT pd.id, COALESCE(sd.NumName, 'Без названия'), 
                               COALESCE(sd.DateAdded, pd.created_at),
                               CASE WHEN p.idPrmRes IS NOT NULL THEN '✓ Распознан' ELSE '⏳ Ожидает' END
                        FROM PRIMARY_DRAWINGS pd
                        LEFT JOIN SKETCH_DRAWINGS sd ON pd.AssociatedWith = sd.idSkDrav::VARCHAR
                        LEFT JOIN PRO p ON p.idPrimaryDrawing = pd.id
                        ORDER BY pd.id DESC
                    """)
                
                for row in self.cur.fetchall():
                    date_str = row[2].strftime("%d.%m.%Y %H:%M") if row[2] else "—"
                    self.data_tree.insert("", tk.END, values=(
                        row[0], row[1], date_str, row[3]
                    ))
            
            elif self.current_stage == 3:
                # Проверка качества - показываем PRO
                self.cur.execute("""
                    SELECT p.idPrmRes, p.NameDrav, p.Designation, 
                           CASE WHEN pd.NeedToImprove = TRUE THEN '⏳ На доработке' ELSE '✓ Одобрено' END
                    FROM PRO p
                    LEFT JOIN PRIMARY_DRAWINGS pd ON pd.id = p.idPrimaryDrawing
                    ORDER BY p.idPrmRes DESC
                """)
                for row in self.cur.fetchall():
                    self.data_tree.insert("", tk.END, values=row)
        
            elif self.current_stage == 4:
                # Валидация - невалидированные PRO
                self.cur.execute(GET_UNVALIDATED_PRO)
                for row in self.cur.fetchall():
                    self.data_tree.insert("", tk.END, values=(row[0], row[1], row[2], 'Нет'))
            
            elif self.current_stage == 5:
                # Архив - FRO
                self.cur.execute(GET_ALL_FRO)
                for row in self.cur.fetchall():
                    self.data_tree.insert("", tk.END, values=(
                        row[0], row[1], row[2], str(row[5]) if row[5] else ''
                    ))
        
        except Exception as e:
            print(f"Ошибка обновления: {e}")
            self._safe_rollback()
    
    def _refresh_employee_info(self):
        """Обновить информацию о сотруднике"""
        if self.current_employee_id:
            try:
                self.cur.execute(GET_ALL_EMPLOYEES)
                for emp in self.cur.fetchall():
                    if emp[0] == self.current_employee_id:
                        self.employee_label.config(text=f"Сотрудник: {emp[2]}")
                        break
            except:
                pass
    
    def _select_employee(self):
        """Выбор сотрудника"""
        if not self.cur:
            messagebox.showerror("Ошибка", "Нет подключения к БД")
            return
        
        try:
            self.cur.execute(GET_ALL_EMPLOYEES)
            employees = self.cur.fetchall()
            
            if not employees:
                messagebox.showinfo("Инфо", "Нет сотрудников. Создать?")
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
                    selected = listbox.get(listbox.curselection()[0])
                    self.current_employee_id = int(selected.split(" - ")[0])
                    self._refresh_employee_info()
                    self._refresh_all()
                    dialog.destroy()
            
            tk.Button(dialog, text="Выбрать", command=select).pack(pady=5)
        
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def _add_employee(self):
        """Добавить сотрудника"""
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
                self.conn.commit()
                self.current_employee_id = self.cur.fetchone()[0]
                dialog.destroy()
                self._refresh_employee_info()
                messagebox.showinfo("Успех", "Сотрудник добавлен!")
            except Exception as e:
                self._safe_rollback()
                messagebox.showerror("Ошибка", str(e))
        
        tk.Button(dialog, text="Сохранить", command=save).grid(row=2, column=0, columnspan=2, pady=10)
    
    # =========================================================================
    # ЭТАП 1: ЗАГРУЗКА
    # =========================================================================
    
    def _load_drawing(self):
        """Загрузка чертежа в БД"""
        if not self.current_employee_id:
            messagebox.showwarning("Внимание", "Сначала выберите сотрудника!")
            return
        
        file_path = filedialog.askopenfilename(
            title="Выберите чертеж",
            filetypes=[("PDF files", "*.pdf"), ("Images", "*.png *.jpg *.jpeg")]
        )
        
        if not file_path:
            return
        
        num_name = os.path.basename(file_path)
        result = simpledialog.askstring("Номер чертежа", "Введите номер/название:",
                                           initialvalue=num_name)
        if not result:
            return
        
        try:
            # Сохраняем в SKETCH_DRAWINGS
            self.cur.execute(INSERT_SKETCH_DRAWING, (file_path, datetime.now(), result))
            sketch_id = self.cur.fetchone()[0]
            
            # Сохраняем в PRIMARY_DRAWINGS
            self.cur.execute(INSERT_PRIMARY_DRAWING, (file_path, str(sketch_id), False, self.current_employee_id))
            drawing_id = self.cur.fetchone()[0]
            
            self.conn.commit()
            
            self.current_drawing_id = drawing_id
            self.current_pdf_path = file_path
            
            messagebox.showinfo("Успех", f"Чертеж загружен! ID: {drawing_id}")
            
            # АВТООБНОВЛЕНИЕ
            self._refresh_all()
            
            # Переход к OCR
            self._show_stage_ocr()
            
        except Exception as e:
            self._safe_rollback()
            messagebox.showerror("Ошибка", str(e))
    
    def _delete_selected(self):
        """Удалить выбранный чертеж"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        if messagebox.askyesno("Подтверждение", "Удалить выбранный чертеж?"):
            item = self.data_tree.item(selected[0])
            drawing_id = item['values'][0]
            
            try:
                self.cur.execute("DELETE FROM PRIMARY_DRAWINGS WHERE id = %s", (drawing_id,))
                self.conn.commit()
                self._refresh_all()
                messagebox.showinfo("Успех", "Чертеж удалён")
            except Exception as e:
                self._safe_rollback()
                messagebox.showerror("Ошибка", str(e))
    
    # =========================================================================
    # ЭТАП 2: OCR
    # =========================================================================
    
    def _run_ocr(self):
        """Запуск OCR на выбранном чертеже"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        if not OCR_AVAILABLE:
            messagebox.showerror("Ошибка", "Установите: pip install PyMuPDF Pillow opencv-python numpy easyocr")
            return
        
        item = self.data_tree.item(selected[0])
        drawing_id = item['values'][0]
        
        # Получаем путь к файлу
        try:
            self.cur.execute("SELECT FilePath FROM PRIMARY_DRAWINGS WHERE id = %s", (drawing_id,))
            result = self.cur.fetchone()
            if result:
                file_path = result[0]
            else:
                messagebox.showerror("Ошибка", "Путь к файлу не найден")
                return
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return
        
        # Открываем PDF
        try:
            self.pdf_doc = fitz.open(file_path)
            self.total_pages = len(self.pdf_doc)
            self.current_page = 0
            
            # Рендерим страницу
            self._render_pdf_page()
            
            messagebox.showinfo("OCR", "Страница отображена. Запускаю распознавание...")
            
            # Предобработка
            from preprocessing import preprocess_for_ocr
            processed = preprocess_for_ocr(self.page_image, page_num=1, save_files=False)
            
            # EasyOCR
            if not self.ocr_reader:
                import easyocr
                self.ocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)
            
            img_array = np.array(processed['processed'])
            results = self.ocr_reader.readtext(
                img_array, detail=1, paragraph=False,
                allowlist='АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789№-.,=абвгдежзийклмнопрстуфхцчшщъыьэюяКПЛИСТФм#',
                width_ths=0.8, height_ths=0.8, low_text=0.3, text_threshold=0.7
            )
            
            # Извлекаем текст
            extracted_text = '\n'.join([text.strip() for _, text, conf in results if conf > 0.4])
            
            # Показываем результат
            self.detail_text.delete("1.0", tk.END)
            self.detail_text.insert(tk.END, "РАСПОЗНАННЫЙ ТЕКСТ:\n")
            self.detail_text.insert(tk.END, "="*50 + "\n")
            self.detail_text.insert(tk.END, extracted_text)
            
            # Сохраняем в буфер
            self.root.clipboard_clear()
            self.root.clipboard_append(extracted_text)
            
            # Сохраняем в файл
            drawing_num = str(drawing_id)
            os.makedirs(f"drawing_{drawing_num}", exist_ok=True)
            with open(f"drawing_{drawing_num}/ocr_result.txt", "w", encoding="utf-8") as f:
                f.write(extracted_text)
            
            # Автоматически создаём запись в PRO
            self.cur.execute("""
                INSERT INTO PRO (
                    NameDrav, Designation, ProjectCode, Dev,
                    DateOriginalCreation, OriginalPaperFormat,
                    NumberOfSheets, Notes, NumDrav, idPrimaryDrawing
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING idPrmRes;
            """, (
                f"Чертёж №{drawing_id}",  # NameDrav
                "",  # Designation
                None,  # ProjectCode
                "",  # Dev
                datetime.now().date(),  # DateOriginalCreation
                "A4",  # OriginalPaperFormat
                1,  # NumberOfSheets
                extracted_text[:500],  # Notes (первые 500 символов)
                drawing_id,  # NumDrav
                drawing_id  # idPrimaryDrawing
            ))
            pro_id = self.cur.fetchone()[0]
            self.conn.commit()
            
            messagebox.showinfo("Успех", f"OCR завершено!\nЧертёж ID: {drawing_id}\nPRO ID: {pro_id}\n\nТекст сохранён в буфере обмена")
            
            # Обновляем список
            self._refresh_all()
            
        except Exception as e:
            self._safe_rollback()
            messagebox.showerror("Ошибка OCR", str(e))
    
    def _render_pdf_page(self):
        """Рендер страницы PDF"""
        if not self.pdf_doc:
            return
        
        page = self.pdf_doc.load_page(self.current_page)
        mat = fitz.Matrix(self.scale, self.scale)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("ppm")
        self.page_image = Image.open(io.BytesIO(img_data))
    
    def _save_ocr_result(self):
        """Сохранить результат OCR в БД"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        item = self.data_tree.item(selected[0])
        pro_id = item['values'][0]
        
        # Показываем форму для редактирования данных
        dialog = tk.Toplevel(self.root)
        dialog.title("Редактирование данных OCR")
        dialog.geometry("500x400")
        
        # Поля
        fields = {}
        labels = ["Наименование", "Обозначение", "Код проекта", "Разработчик",
                  "Формат", "Кол-во листов", "Примечания"]
        
        for i, label in enumerate(labels):
            tk.Label(dialog, text=label + ":").grid(row=i, column=0, sticky=tk.W, padx=5, pady=3)
            entry = tk.Entry(dialog, width=40)
            entry.grid(row=i, column=1, padx=5, pady=3)
            fields[label] = entry
        
        # Заполняем из текста
        text = self.detail_text.get("1.0", tk.END)
        
        def save():
            try:
                self.cur.execute("""
                    UPDATE PRO SET 
                        NameDrav = %s, Designation = %s, ProjectCode = %s, Dev = %s,
                        OriginalPaperFormat = %s, NumberOfSheets = %s, Notes = %s
                    WHERE idPrmRes = %s
                """, (
                    fields["Наименование"].get(),
                    fields["Обозначение"].get(),
                    int(fields["Код проекта"].get()) if fields["Код проекта"].get() else None,
                    fields["Разработчик"].get(),
                    fields["Формат"].get(),
                    int(fields["Кол-во листов"].get()) if fields["Кол-во листов"].get() else 1,
                    fields["Примечания"].get(),
                    pro_id
                ))
                
                self.conn.commit()
                dialog.destroy()
                
                # АВТООБНОВЛЕНИЕ
                self._refresh_all()
                messagebox.showinfo("Успех", "Данные сохранены в БД!")
                
            except Exception as e:
                self._safe_rollback()
                messagebox.showerror("Ошибка", str(e))
        
        tk.Button(dialog, text="Сохранить", command=save).grid(row=len(labels), column=0, columnspan=2, pady=10)
    
    def _create_pro_manual(self):
        """Создать PRO вручную (без OCR)"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите чертеж!")
            return
        
        item = self.data_tree.item(selected[0])
        drawing_id = item['values'][0]
        
        # Показываем форму для заполнения данных
        dialog = tk.Toplevel(self.root)
        dialog.title("Создание PRO вручную")
        dialog.geometry("500x450")
        
        # Поля
        fields = {}
        labels = ["Наименование", "Обозначение", "Код проекта", "Разработчик",
                  "Дата создания", "Формат", "Кол-во листов", "Примечания"]
        
        for i, label in enumerate(labels):
            tk.Label(dialog, text=label + ":").grid(row=i, column=0, sticky=tk.W, padx=5, pady=3)
            entry = tk.Entry(dialog, width=40)
            entry.grid(row=i, column=1, padx=5, pady=3)
            fields[label] = entry
        
        # Значения по умолчанию
        fields["Наименование"].insert(0, f"Чертёж №{drawing_id}")
        fields["Формат"].insert(0, "A4")
        fields["Кол-во листов"].insert(0, "1")
        fields["Дата создания"].insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        def save():
            try:
                self.cur.execute("""
                    INSERT INTO PRO (
                        NameDrav, Designation, ProjectCode, Dev,
                        DateOriginalCreation, OriginalPaperFormat,
                        NumberOfSheets, Notes, NumDrav, idPrimaryDrawing
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING idPrmRes;
                """, (
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
                self._refresh_all()
                messagebox.showinfo("Успех", f"PRO создан! ID: {pro_id}")
            except Exception as e:
                self._safe_rollback()
                messagebox.showerror("Ошибка", str(e))
        
        tk.Button(dialog, text="Сохранить", command=save).grid(row=len(labels), column=0, columnspan=2, pady=10)
    
    # =========================================================================
    # ЭТАП 3: ПРОВЕРКА КАЧЕСТВА
    # =========================================================================
    
    def _mark_quality_ok(self):
        """Качество ОК - подтверждаем PRO"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите PRO!")
            return
        
        pro_id = self.data_tree.item(selected[0])['values'][0]
        
        try:
            # Получаем idPrimaryDrawing
            self.cur.execute("SELECT idPrimaryDrawing FROM PRO WHERE idPrmRes = %s", (pro_id,))
            result = self.cur.fetchone()
            if result and result[0]:
                self.cur.execute(UPDATE_DRAWING_NEED_IMPROVE, (False, result[0]))
            
            self.conn.commit()
            self._refresh_all()
            messagebox.showinfo("Успех", "Качество подтверждено!")
        except Exception as e:
            self._safe_rollback()
            messagebox.showerror("Ошибка", str(e))
    
    def _mark_quality_bad(self):
        """Требует исправления - отправляем на доработку"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите PRO!")
            return
        
        pro_id = self.data_tree.item(selected[0])['values'][0]
        
        try:
            # Получаем idPrimaryDrawing
            self.cur.execute("SELECT idPrimaryDrawing FROM PRO WHERE idPrmRes = %s", (pro_id,))
            result = self.cur.fetchone()
            if result and result[0]:
                self.cur.execute(UPDATE_DRAWING_NEED_IMPROVE, (True, result[0]))
            
            self.conn.commit()
            self._refresh_all()
            messagebox.showinfo("Успех", "Чертеж помечен как требующий улучшения")
        except Exception as e:
            self._safe_rollback()
            messagebox.showerror("Ошибка", str(e))
    
    # =========================================================================
    # ЭТАП 4: ВАЛИДАЦИЯ
    # =========================================================================
    
    def _validate_pro(self):
        """Валидировать PRO"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите PRO!")
            return
        
        pro_id = self.data_tree.item(selected[0])['values'][0]
        
        try:
            # Получаем данные PRO
            self.cur.execute("SELECT * FROM PRO WHERE idPrmRes = %s", (pro_id,))
            pro_data = self.cur.fetchone()
            
            if not pro_data:
                messagebox.showerror("Ошибка", "PRO не найден")
                return
            
            # Создаём FRO
            self.cur.execute(INSERT_FRO_RESULT, (
                pro_data[1], pro_data[2], pro_data[3], pro_data[4],
                pro_data[5], pro_data[6], pro_data[7], pro_data[9], pro_id
            ))
            fro_id = self.cur.fetchone()[0]
            
            self.conn.commit()
            
            # АВТООБНОВЛЕНИЕ
            self._refresh_all()
            messagebox.showinfo("Успех", f"Создан FRO! ID: {fro_id}")
            
        except Exception as e:
            self._safe_rollback()
            messagebox.showerror("Ошибка", str(e))
    
    # =========================================================================
    # ЭТАП 5: АРХИВ
    # =========================================================================
    
    def _archive_fro(self):
        """Архивировать FRO"""
        selected = self.data_tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите FRO!")
            return
        
        fro_id = self.data_tree.item(selected[0])['values'][0]
        
        try:
            # Получаем данные FRO
            self.cur.execute("SELECT * FROM FRO WHERE idFnlRes = %s", (fro_id,))
            fro_data = self.cur.fetchone()
            
            if not fro_data:
                messagebox.showerror("Ошибка", "FRO не найден")
                return
            
            # Создаём архив (только необходимые поля)
            self.cur.execute(INSERT_ARCHIVE, (
                f"/archive/drawing_{fro_id}.pdf",  # FilePathPrmArch
                fro_data[8],  # NumDrav
                fro_data[1],  # NameDrav
                fro_data[2],  # Designation
                fro_data[3],  # ProjectCode
                fro_data[4],  # Dev
                datetime.now(),  # SaveDateArch
                self.current_employee_id  # id_employeePrmArch
            ))
            
            arch_id = self.cur.fetchone()[0]
            self.conn.commit()
            
            # АВТООБНОВЛЕНИЕ
            self._refresh_all()
            messagebox.showinfo("Успех", f"Чертеж архивирован! ID: {arch_id}")
            
        except Exception as e:
            self._safe_rollback()
            messagebox.showerror("Ошибка", str(e))
    
    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =========================================================================
    
    def _safe_rollback(self):
        """Безопасный rollback"""
        try:
            self.conn.rollback()
        except:
            pass


# ============================================================================
# ЗАПУСК
# ============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = DrawingApp(root)
    root.mainloop()
