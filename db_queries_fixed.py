# ============================================================
# SQL-ЗАПРОСЫ ДЛЯ ПРИЛОЖЕНИЯ РАСПОЗНАВАНИЯ ЧЕРТЕЖЕЙ
# База данных: shuvi (PostgreSQL)
# Версия: исправленная под реальную структуру БД
# ============================================================

# ============================================================
# ЭТАП 1: ЗАГРУЗКА (Сотрудник загружает эскиз)
# Таблицы: SKETCH_DRAWINGS → PRIMARY_DRAWINGS
# ============================================================

# 1.1. Добавление эскиза (скан/фото чертежа)
# Примечание: в текущей структуре нет поля idEmployee в SKETCH_DRAWINGS
INSERT_SKETCH_DRAWING = """
INSERT INTO SKETCH_DRAWINGS (SFilePath, DateAdded, NumName)
VALUES (%s, %s, %s)
RETURNING idSkDrav;
"""
# Параметры: (путь_к_файлу, дата_добавления, номер_название)

# 1.2. Получить все эскизы (без фильтра по сотруднику, т.к. нет поля)
GET_ALL_SKETCHES = """
SELECT idSkDrav, SFilePath, DateAdded, NumName
FROM SKETCH_DRAWINGS
ORDER BY DateAdded DESC;
"""

# 1.3. Создание первичного чертежа (связь с эскизом)
INSERT_PRIMARY_DRAWING = """
INSERT INTO PRIMARY_DRAWINGS (FilePath, AssociatedWith, NeedToImprove, idEmployee)
VALUES (%s, %s, %s, %s)
RETURNING id;
"""
# Параметры: (путь_к_файлу, связь_с_эскизом, требует_улучшения, id_сотрудника)

# 1.4. Получить первичные чертежи (все или по сотруднику)
GET_PRIMARY_DRAWINGS_BY_EMPLOYEE = """
SELECT id, FilePath, AssociatedWith, NeedToImprove, idEmployee
FROM PRIMARY_DRAWINGS
WHERE idEmployee = %s
ORDER BY id DESC;
"""
# Параметры: (id_сотрудника,)

GET_ALL_PRIMARY_DRAWINGS = """
SELECT id, FilePath, AssociatedWith, NeedToImprove, idEmployee
FROM PRIMARY_DRAWINGS
ORDER BY id DESC;
"""

# 1.5. Получить первичный чертеж по ID
GET_PRIMARY_DRAWING_BY_ID = """
SELECT id, FilePath, AssociatedWith, NeedToImprove, idEmployee
FROM PRIMARY_DRAWINGS
WHERE id = %s;
"""
# Параметры: (id_чертежа,)


# ============================================================================
# ЭТАП 2: OCR РАСПОЗНАВАНИЕ (Первичный чертеж → PRO)
# ============================================================================

# 2.1 Создание результата распознавания (PRO)
# Примечание: DateOriginalCreation - TIMESTAMP (не DATE как было)
INSERT_PRO_RESULT = """
INSERT INTO PRO (
    NameDrav, Designation, ProjectCode, Dev,
    DateOriginalCreation, OriginalPaperFormat,
    NumberOfSheets, Notes, NumDrav
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING idPrmRes;
"""
# Параметры: (наименование, обозначение, код_проекта, разработчик,
#             дата_создания, формат, кол-во_листов, примечания, номер_чертежа)

# 2.2 Получить все результаты PRO
GET_ALL_PRO = """
SELECT idPrmRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, Notes, NumDrav
FROM PRO
ORDER BY idPrmRes DESC;
"""

# 2.3 Получить результаты OCR для чертежа
GET_PRO_BY_DRAWING = """
SELECT idPrmRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, Notes, NumDrav
FROM PRO
WHERE NumDrav = %s
ORDER BY idPrmRes DESC;
"""
# Параметры: (номер_чертежа,)

# 2.4 Получить PRO по ID
GET_PRO_BY_ID = """
SELECT idPrmRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, Notes, NumDrav
FROM PRO
WHERE idPrmRes = %s;
"""
# Параметры: (id_pro,)


# ============================================================================
# ЭТАП 3: ПРОВЕРКА КАЧЕСТВА (Исправления → DRAWING_VERSIONS)
# ============================================================================

# 3.1 Создание связи версий (оригинал → исправленный)
INSERT_DRAWING_VERSION = """
INSERT INTO DRAWING_VERSIONS (original_drawing_id, corrected_drawing_id, correction_date, idEmployee)
VALUES (%s, %s, %s, %s)
RETURNING id_version;
"""
# Параметры: (id_оригинала, id_исправленного, дата_исправления, id_сотрудника)

# 3.2 Пометить чертеж как требующий улучшения
UPDATE_DRAWING_NEED_IMPROVE = """
UPDATE PRIMARY_DRAWINGS
SET NeedToImprove = %s
WHERE id = %s;
"""
# Параметры: (True/False, id_чертежа)

# 3.3 Получить чертежи требующие улучшения
GET_DRAWINGS_NEED_IMPROVE = """
SELECT id, FilePath, AssociatedWith, NeedToImprove, idEmployee
FROM PRIMARY_DRAWINGS
WHERE NeedToImprove = TRUE
ORDER BY id DESC;
"""

# 3.4 Получить историю версий чертежа
GET_DRAWING_VERSIONS = """
SELECT id_version, original_drawing_id, corrected_drawing_id,
       correction_date, idEmployee
FROM DRAWING_VERSIONS
WHERE original_drawing_id = %s OR corrected_drawing_id = %s
ORDER BY correction_date DESC;
"""
# Параметры: (id_чертежа, id_чертежа)


# ============================================================================
# ЭТАП 4: ВАЛИДАЦИЯ (PRO → FRO)
# ============================================================================

# 4.1 Создание финального результата (FRO)
# Примечание: DateOriginalCreation - TIMESTAMP (не DATE)
INSERT_FRO_RESULT = """
INSERT INTO FRO (
    NameDrav, Designation, ProjectCode, Dev,
    DateOriginalCreation, OriginalPaperFormat,
    NumberOfSheets, NumDrav, pro_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING idFnlRes;
"""
# Параметры: (наименование, обозначение, код_проекта, разработчик,
#             дата_создания, формат, кол-во_листов, номер_чертежа, id_pro)

# 4.2 Получить FRO по PRO
GET_FRO_BY_PRO = """
SELECT idFnlRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, NumDrav, pro_id
FROM FRO
WHERE pro_id = %s;
"""
# Параметры: (id_pro,)

# 4.3 Получить все FRO
GET_ALL_FRO = """
SELECT idFnlRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, NumDrav, pro_id
FROM FRO
ORDER BY idFnlRes DESC;
"""

# 4.4 Получить FRO по ID
GET_FRO_BY_ID = """
SELECT idFnlRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, NumDrav, pro_id
FROM FRO
WHERE idFnlRes = %s;
"""
# Параметры: (id_fro,)

# 4.5 Получить FRO по номеру чертежа
GET_FRO_BY_DRAWING_NUM = """
SELECT idFnlRes, NameDrav, Designation, ProjectCode, Dev,
       DateOriginalCreation, OriginalPaperFormat,
       NumberOfSheets, NumDrav, pro_id
FROM FRO
WHERE NumDrav = %s;
"""
# Параметры: (номер_чертежа,)


# ============================================================================
# ЭТАП 5: АРХИВАЦИЯ (FRO → ARCH_OF_DRAWS)
# ============================================================================

# 5.1 Архивировать финальный результат
# Используем только основные поля из структуры
INSERT_ARCHIVE = """
INSERT INTO ARCH_OF_DRAWS (
    FilePathPrmArch, NumDravFROArch,
    NameDravFROArch, DesignationFROArch, ProjectCodeFROArch,
    DevFROArch, SaveDateArch, id_employeePrmArch
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
RETURNING idPrmArch;
"""
# Параметры: (путь_к_файлу, номер_чертежа, наименование, обозначение,
#             код_проекта, разработчик, дата_архивации, id_сотрудника)

# 5.2 Удалить FRO после архивации (опционально)
DELETE_FRO = """
DELETE FROM FRO
WHERE idFnlRes = %s;
"""
# Параметры: (id_fro,)

# 5.3 Получить все архивы
GET_ALL_ARCHIVES = """
SELECT idPrmArch, FilePathPrmArch, NumDravFROArch,
       NameDravFROArch, DesignationFROArch, SaveDateArch
FROM ARCH_OF_DRAWS
ORDER BY SaveDateArch DESC;
"""

# 5.4 Поиск архива по номеру чертежа
GET_ARCHIVE_BY_DRAWING_NUM = """
SELECT idPrmArch, FilePathPrmArch, NumDravFROArch,
       NameDravFROArch, DesignationFROArch, SaveDateArch
FROM ARCH_OF_DRAWS
WHERE NumDravFROArch = %s;
"""
# Параметры: (номер_чертежа,)

# 5.5 Получить архивы по сотруднику
GET_ARCHIVES_BY_EMPLOYEE = """
SELECT idPrmArch, FilePathPrmArch, NumDravFROArch,
       NameDravFROArch, SaveDateArch
FROM ARCH_OF_DRAWS
WHERE id_employeePrmArch = %s
ORDER BY SaveDateArch DESC;
"""
# Параметры: (id_сотрудника,)


# ============================================================================
# СПРАВОЧНИКИ И ШАБЛОНЫ
# ============================================================================

# 6.1 Получить всех сотрудников
GET_ALL_EMPLOYEES = """
SELECT idEmployee, Post, FullName, Role
FROM EMPLOYEES
ORDER BY FullName;
"""

# 6.2 Получить сотрудника по ID
GET_EMPLOYEE_BY_ID = """
SELECT idEmployee, Post, FullName, Role
FROM EMPLOYEES
WHERE idEmployee = %s;
"""
# Параметры: (id_сотрудника,)

# 6.3 Создать сотрудника
INSERT_EMPLOYEE = """
INSERT INTO EMPLOYEES (Post, FullName, Role)
VALUES (%s, %s, %s)
RETURNING idEmployee;
"""
# Параметры: (должность, ФИО, роль)

# 6.4 Получить все шаблоны
GET_ALL_TEMPLATES = """
SELECT idGOST, GOSTName, DateGOST, Relevance,
       TemplatesPhotoPath, DravingTemplatesPath
FROM DRAWING_TAMPLATES
ORDER BY DateGOST DESC;
"""

# 6.5 Получить актуальные шаблоны
GET_ACTIVE_TEMPLATES = """
SELECT idGOST, GOSTName, DateGOST, TemplatesPhotoPath, DravingTemplatesPath
FROM DRAWING_TAMPLATES
WHERE Relevance = TRUE
ORDER BY DateGOST DESC;
"""

# 6.6 Получить области шаблона
GET_TEMPLATE_AREAS = """
SELECT idArea, CoordsX1, CoordsY1, CoordsX2, CoordsY2, idGOST
FROM TEMPLATE_AREA
WHERE idGOST = %s;
"""
# Параметры: (id_шаблона,)

# 6.7 Создать шаблон
INSERT_TEMPLATE = """
INSERT INTO DRAWING_TAMPLATES (GOSTName, DateGOST, Relevance, TemplatesPhotoPath, DravingTemplatesPath)
VALUES (%s, %s, %s, %s, %s)
RETURNING idGOST;
"""
# Параметры: (название_гост, дата, актуальность, путь_к_фото, путь_к_шаблону)

# 6.8 Создать область шаблона
INSERT_TEMPLATE_AREA = """
INSERT INTO TEMPLATE_AREA (CoordsX1, CoordsY1, CoordsX2, CoordsY2, idGOST)
VALUES (%s, %s, %s, %s, %s)
RETURNING idArea;
"""
# Параметры: (x1, y1, x2, y2, id_шаблона)


# ============================================================================
# ОТЧЕТЫ И СТАТИСТИКА
# ============================================================================

# 7.1 Количество чертежей по статусам
GET_DRAWINGS_STATISTICS = """
SELECT
    COUNT(DISTINCT pd.id) AS total_primary,
    COUNT(DISTINCT CASE WHEN pd.NeedToImprove = TRUE THEN pd.id END) AS need_improve,
    COUNT(DISTINCT p.idPrmRes) AS total_pro,
    COUNT(DISTINCT f.idFnlRes) AS total_fro,
    COUNT(DISTINCT a.idPrmArch) AS total_archived
FROM PRIMARY_DRAWINGS pd
LEFT JOIN PRO p ON p.NumDrav = pd.id
LEFT JOIN FRO f ON f.pro_id = p.idPrmRes
LEFT JOIN ARCH_OF_DRAWS a ON a.NumDravFROArch = f.NumDrav;
"""

# 7.2 Статистика по сотрудникам
GET_EMPLOYEE_STATISTICS = """
SELECT
    e.idEmployee,
    e.FullName,
    COALESCE(COUNT(DISTINCT pd.id), 0) AS primary_drawings_count,
    COALESCE(COUNT(DISTINCT a.idPrmArch), 0) AS archived_count
FROM EMPLOYEES e
LEFT JOIN PRIMARY_DRAWINGS pd ON pd.idEmployee = e.idEmployee
LEFT JOIN ARCH_OF_DRAWS a ON a.id_employeePrmArch = e.idEmployee
GROUP BY e.idEmployee, e.FullName
ORDER BY archived_count DESC;
"""

# 7.3 Чертежи без валидации (в PRO но не в FRO)
GET_UNVALIDATED_PRO = """
SELECT p.idPrmRes, p.NameDrav, p.Designation, p.NumDrav
FROM PRO p
LEFT JOIN FRO f ON f.pro_id = p.idPrmRes
WHERE f.idFnlRes IS NULL
ORDER BY p.idPrmRes DESC;
"""
