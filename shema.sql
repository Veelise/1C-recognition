-- ============================================================================
-- БАЗА ДАННЫХ: shuvi_test
-- ПРИЛОЖЕНИЕ: Распознавание чертежей (OCR)
-- ============================================================================

-- Удаление существующих таблиц (в правильном порядке из-за FK)
DROP TABLE IF EXISTS TEMPLATE_AREA CASCADE;
DROP TABLE IF EXISTS ARCH_OF_DRAWS CASCADE;
DROP TABLE IF EXISTS FRO CASCADE;
DROP TABLE IF EXISTS PRO CASCADE;
DROP TABLE IF EXISTS PRIMARY_DRAWINGS CASCADE;
DROP TABLE IF EXISTS SKETCH_DRAWINGS CASCADE;
DROP TABLE IF EXISTS DRAWING_TAMPLATES CASCADE;
DROP TABLE IF EXISTS EMPLOYEES CASCADE;

-- ============================================================================
-- 1. EMPLOYEES — Сотрудники
-- ============================================================================
CREATE TABLE EMPLOYEES (
    idEmployee BIGSERIAL PRIMARY KEY,
    Post VARCHAR(100),
    FullName VARCHAR(255) NOT NULL,
    Role VARCHAR(50) DEFAULT 'operator' CHECK (Role IN ('admin', 'operator', 'validator'))
);

-- Индекс для поиска по роли
CREATE INDEX idx_employees_role ON EMPLOYEES(Role);

-- ============================================================================
-- 2. SKETCH_DRAWINGS — Эскизы чертежей (скан/фото)
-- ============================================================================
CREATE TABLE SKETCH_DRAWINGS (
    idSkDrav BIGSERIAL PRIMARY KEY,
    SFilePath VARCHAR(500),
    DateAdded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    NumName VARCHAR(255),
    idEmployee BIGINT REFERENCES EMPLOYEES(idEmployee) ON DELETE SET NULL
);

-- Индексы
CREATE INDEX idx_sketch_date ON SKETCH_DRAWINGS(DateAdded DESC);
CREATE INDEX idx_sketch_employee ON SKETCH_DRAWINGS(idEmployee);

-- ============================================================================
-- 3. PRIMARY_DRAWINGS — Первичные чертежи (обработанные)
-- ============================================================================
CREATE TABLE PRIMARY_DRAWINGS (
    id BIGSERIAL PRIMARY KEY,
    FilePath VARCHAR(500),
    AssociatedWith VARCHAR(100),
    NeedToImprove BOOLEAN DEFAULT FALSE,
    idEmployee BIGINT REFERENCES EMPLOYEES(idEmployee) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX idx_primary_employee ON PRIMARY_DRAWINGS(idEmployee);
CREATE INDEX idx_primary_need_improve ON PRIMARY_DRAWINGS(NeedToImprove);

-- ============================================================================
-- 4. PRO — Результаты OCR распознавания
-- ============================================================================
CREATE TABLE PRO (
    idPrmRes BIGSERIAL PRIMARY KEY,
    NameDrav VARCHAR(255),
    Designation VARCHAR(100),
    ProjectCode BIGINT,
    Dev VARCHAR(255),
    DateOriginalCreation DATE,
    OriginalPaperFormat VARCHAR(20),
    NumberOfSheets BIGINT DEFAULT 1,
    Notes TEXT,
    NumDrav BIGINT,
    idPrimaryDrawing BIGINT REFERENCES PRIMARY_DRAWINGS(id) ON DELETE SET NULL,
    validated BOOLEAN DEFAULT FALSE,
    validated_by BIGINT REFERENCES EMPLOYEES(idEmployee) ON DELETE SET NULL,
    validation_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX idx_pro_drawing ON PRO(idPrimaryDrawing);
CREATE INDEX idx_pro_validated ON PRO(validated);
CREATE INDEX idx_pro_numdrav ON PRO(NumDrav);

-- ============================================================================
-- 5. FRO — Финальные результаты (после валидации)
-- ============================================================================
CREATE TABLE FRO (
    idFnlRes BIGSERIAL PRIMARY KEY,
    NameDrav VARCHAR(255),
    Designation VARCHAR(100),
    ProjectCode BIGINT,
    Dev VARCHAR(255),
    DateOriginalCreation DATE,
    OriginalPaperFormat VARCHAR(20),
    NumberOfSheets BIGINT DEFAULT 1,
    NumDrav BIGINT,
    pro_id BIGINT REFERENCES PRO(idPrmRes) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX idx_fro_pro ON FRO(pro_id);
CREATE INDEX idx_fro_numdrav ON FRO(NumDrav);

-- ============================================================================
-- 6. ARCH_OF_DRAWS — Архив чертежей
-- ============================================================================
CREATE TABLE ARCH_OF_DRAWS (
    idPrmArch BIGSERIAL PRIMARY KEY,
    FilePathPrmArch VARCHAR(500),
    AssociatedWithPrmArch VARCHAR(100),
    NumDravFROArch BIGINT,
    NameDravFROArch VARCHAR(255),
    DesignationFROArch VARCHAR(100),
    ProjectCodeFROArch BIGINT,
    DevFROArch VARCHAR(255),
    DateOriginalCreationFROArch DATE,
    OriginalPaperFormatFROArch VARCHAR(20),
    NumberOfSheetsFROArch BIGINT DEFAULT 1,
    SaveDateArch TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    MonthCheckArch BOOLEAN DEFAULT FALSE,
    SFilePathArch VARCHAR(500),
    DateAddedArch TIMESTAMP,
    NumNameArch VARCHAR(255),
    UploadedEdmployeeIDArch VARCHAR(100),
    id_employeePrmArch BIGINT REFERENCES EMPLOYEES(idEmployee) ON DELETE SET NULL
);

-- Индексы
CREATE INDEX idx_archive_employee ON ARCH_OF_DRAWS(id_employeePrmArch);
CREATE INDEX idx_archive_numdrav ON ARCH_OF_DRAWS(NumDravFROArch);
CREATE INDEX idx_archive_date ON ARCH_OF_DRAWS(SaveDateArch DESC);

-- ============================================================================
-- 7. DRAWING_TAMPLATES — Шаблоны (ГОСТ)
-- ============================================================================
CREATE TABLE DRAWING_TAMPLATES (
    idGOST BIGSERIAL PRIMARY KEY,
    GOSTName VARCHAR(255),
    DateGOST DATE,
    Relevance BOOLEAN DEFAULT TRUE,
    TemplatesPhotoPath VARCHAR(500),
    DravingTemplatesPath VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индекс
CREATE INDEX idx_templates_relevance ON DRAWING_TAMPLATES(Relevance);

-- ============================================================================
-- 8. TEMPLATE_AREA — Области на шаблоне
-- ============================================================================
CREATE TABLE TEMPLATE_AREA (
    idArea BIGSERIAL PRIMARY KEY,
    CoordsX1 BIGINT,
    CoordsY1 BIGINT,
    CoordsX2 BIGINT,
    CoordsY2 BIGINT,
    idGOST BIGINT REFERENCES DRAWING_TAMPLATES(idGOST) ON DELETE CASCADE,
    AreaName VARCHAR(100)
);

-- Индекс
CREATE INDEX idx_template_area_gost ON TEMPLATE_AREA(idGOST);

-- ============================================================================
-- ТЕСТОВЫЕ ДАННЫЕ
-- ============================================================================

-- Сотрудники
INSERT INTO EMPLOYEES (Post, FullName, Role) VALUES 
    ('Оператор', 'Иванов Иван Иванович', 'operator'),
    ('Валидатор', 'Петров Петр Петрович', 'validator'),
    ('Администратор', 'Сидоров Сидор Сидорович', 'admin')
ON CONFLICT DO NOTHING;

-- Проверка
SELECT 'EMPLOYEES' as tbl, COUNT(*) as cnt FROM EMPLOYEES
UNION ALL SELECT 'SKETCH_DRAWINGS', COUNT(*) FROM SKETCH_DRAWINGS
UNION ALL SELECT 'PRIMARY_DRAWINGS', COUNT(*) FROM PRIMARY_DRAWINGS
UNION ALL SELECT 'PRO', COUNT(*) FROM PRO
UNION ALL SELECT 'FRO', COUNT(*) FROM FRO
UNION ALL SELECT 'ARCH_OF_DRAWS', COUNT(*) FROM ARCH_OF_DRAWS
UNION ALL SELECT 'DRAWING_TAMPLATES', COUNT(*) FROM DRAWING_TAMPLATES
UNION ALL SELECT 'TEMPLATE_AREA', COUNT(*) FROM TEMPLATE_AREA;
