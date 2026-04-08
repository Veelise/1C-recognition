-- ============================================================================
-- СОЗДАНИЕ ТАБЛИЦ ДЛЯ ПРИЛОЖЕНИЯ РАСПОЗНАВАНИЯ ЧЕРТЕЖЕЙ
-- База данных: shuvi (PostgreSQL)
-- ============================================================================

-- 1. СОТРУДНИКИ
CREATE TABLE IF NOT EXISTS EMPLOYEES (
    idEmployee BIGSERIAL PRIMARY KEY,
    Post CHAR(100),
    FullName CHAR(255) NOT NULL,
    Role CHAR(50) DEFAULT 'operator'
);

-- 2. ЭСКИЗЫ (скан/фото чертежа)
CREATE TABLE IF NOT EXISTS SKETCH_DRAWINGS (
    idSkDrav BIGSERIAL PRIMARY KEY,
    SFilePath CHAR(500),
    DateAdded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    NumName CHAR(255),
    idEmployee BIGINT REFERENCES EMPLOYEES(idEmployee)
);

-- 3. ПЕРВИЧНЫЕ ЧЕРТЕЖИ
CREATE TABLE IF NOT EXISTS PRIMARY_DRAWINGS (
    id BIGSERIAL PRIMARY KEY,
    FilePath CHAR(500),
    AssociatedWith CHAR(100),
    NeedToImprove BOOLEAN DEFAULT FALSE,
    idEmployee BIGINT REFERENCES EMPLOYEES(idEmployee)
);

-- 4. РЕЗУЛЬТАТЫ OCR (PRO)
CREATE TABLE IF NOT EXISTS PRO (
    idPrmRes BIGSERIAL PRIMARY KEY,
    NameDrav CHAR(255),
    Designation CHAR(100),
    ProjectCode BIGINT,
    Dev CHAR(255),
    DateOriginalCreation DATE,
    OriginalPaperFormat CHAR(20),
    NumberOfSheets BIGINT DEFAULT 1,
    Notes TEXT,
    NumDrav BIGINT,
    idPrimaryDrawing BIGINT REFERENCES PRIMARY_DRAWINGS(id),
    validated BOOLEAN DEFAULT FALSE,
    validated_by BIGINT REFERENCES EMPLOYEES(idEmployee),
    validation_date TIMESTAMP
);

-- 5. ФИНАЛЬНЫЕ РЕЗУЛЬТАТЫ (FRO)
CREATE TABLE IF NOT EXISTS FRO (
    idFnlRes BIGSERIAL PRIMARY KEY,
    NameDrav CHAR(255),
    Designation CHAR(100),
    ProjectCode BIGINT,
    Dev CHAR(255),
    DateOriginalCreation DATE,
    OriginalPaperFormat CHAR(20),
    NumberOfSheets BIGINT DEFAULT 1,
    NumDrav BIGINT,
    pro_id BIGINT REFERENCES PRO(idPrmRes)
);

-- 6. АРХИВ ЧЕРТЕЖЕЙ
CREATE TABLE IF NOT EXISTS ARCH_OF_DRAWS (
    idPrmArch BIGSERIAL PRIMARY KEY,
    FilePathPrmArch CHAR(500),
    AssociatedWithPrmArch CHAR(100),
    NumDravFROArch BIGINT,
    NameDravFROArch CHAR(255),
    DesignationFROArch CHAR(100),
    ProjectCodeFROArch BIGINT,
    DevFROArch CHAR(255),
    DateOriginalCreationFROArch DATE,
    OriginalPaperFormatFROArch CHAR(20),
    NumberOfSheetsFROArch BIGINT DEFAULT 1,
    SaveDateArch TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    MonthCheckArch BOOLEAN DEFAULT FALSE,
    SFilePathArch CHAR(500),
    DateAddedArch TIMESTAMP,
    NumNameArch CHAR(255),
    UploadedEdmployeeIDArch CHAR(100),
    id_employeePrmArch BIGINT REFERENCES EMPLOYEES(idEmployee)
);

-- 7. ШАБЛОНЫ (ГОСТ)
CREATE TABLE IF NOT EXISTS DRAWING_TAMPLATES (
    idGOST BIGSERIAL PRIMARY KEY,
    GOSTName CHAR(255),
    DateGOST DATE,
    Relevance BOOLEAN DEFAULT TRUE,
    TemplatesPhotoPath CHAR(500),
    DravingTemplatesPath CHAR(500)
);

-- 8. ОБЛАСТИ ШАБЛОНА
CREATE TABLE IF NOT EXISTS TEMPLATE_AREA (
    idArea BIGSERIAL PRIMARY KEY,
    CoordsX1 BIGINT,
    CoordsY1 BIGINT,
    CoordsX2 BIGINT,
    CoordsY2 BIGINT,
    idGOST BIGINT REFERENCES DRAWING_TAMPLATES(idGOST)
);

-- ============================================================================
-- ТЕСТОВЫЕ ДАННЫЕ (опционально)
-- ============================================================================

-- Добавить тестового сотрудника
INSERT INTO EMPLOYEES (Post, FullName, Role) 
VALUES ('Оператор', 'Иванов Иван Иванович', 'operator')
ON CONFLICT DO NOTHING;

-- Добавить админа
INSERT INTO EMPLOYEES (Post, FullName, Role) 
VALUES ('Администратор', 'Петров Петр Петрович', 'admin')
ON CONFLICT DO NOTHING;

-- Добавить валидатора
INSERT INTO EMPLOYEES (Post, FullName, Role) 
VALUES ('Валидатор', 'Сидоров Сидор Сидорович', 'validator')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- ПРОВЕРКА
-- ============================================================================

SELECT 'EMPLOYEES' as table_name, COUNT(*) as rows FROM EMPLOYEES
UNION ALL
SELECT 'SKETCH_DRAWINGS', COUNT(*) FROM SKETCH_DRAWINGS
UNION ALL
SELECT 'PRIMARY_DRAWINGS', COUNT(*) FROM PRIMARY_DRAWINGS
UNION ALL
SELECT 'PRO', COUNT(*) FROM PRO
UNION ALL
SELECT 'FRO', COUNT(*) FROM FRO
UNION ALL
SELECT 'ARCH_OF_DRAWS', COUNT(*) FROM ARCH_OF_DRAWS
UNION ALL
SELECT 'DRAWING_TAMPLATES', COUNT(*) FROM DRAWING_TAMPLATES
UNION ALL
SELECT 'TEMPLATE_AREA', COUNT(*) FROM TEMPLATE_AREA;
