-- ============================================================
-- WEBSITE CONTENT MANAGEMENT (CMS)  v1  —  SCHEMA MIGRATION (SQL Server)
-- Chay 1 lan tren database architecture_ai. An toan chay lai (IF NOT EXISTS).
--
-- Nguyen tac:
--   * ContentJson = override phang {"en":{...},"vi":{...}} merge DE LEN default
--     hard-code o frontend (thieu key -> fallback default => khong vo layout).
--   * Status = 'draft' (toi da 1/page, upsert) | 'published'.
--   * Filtered unique index dam bao DUNG 1 ban IsCurrent=1 / PageKey (ban dang
--     phuc vu). Restore = publish lai ban clone tu revision cu.
-- ============================================================

SET XACT_ABORT ON;
GO

-- 1) Bang revision noi dung trang
IF OBJECT_ID('dbo.CmsRevisions', 'U') IS NULL
BEGIN
    CREATE TABLE CmsRevisions (
        RevisionId   UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        PageKey      NVARCHAR(50)  NOT NULL,            -- 'landing' | 'user'
        ContentJson  NVARCHAR(MAX) NOT NULL,            -- {"en":{...},"vi":{...}}
        Status       NVARCHAR(20)  NOT NULL,            -- 'draft' | 'published'
        RevisionNo   INT           NOT NULL DEFAULT 0,
        IsCurrent    BIT           NOT NULL DEFAULT 0,  -- ban published dang phuc vu
        CreatedBy    UNIQUEIDENTIFIER NULL,             -- UserId cua admin
        CreatedAt    DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt    DATETIME2     NULL
    );
END
GO

-- Truy van nhanh theo trang + trang thai
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CmsRevisions_Page')
    CREATE INDEX IX_CmsRevisions_Page
        ON CmsRevisions (PageKey, Status, RevisionNo);
GO

-- Bat bien: DUNG 1 ban current / page (DB-level, khong phu thuoc code dung)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UQ_CmsRevisions_Current')
    CREATE UNIQUE INDEX UQ_CmsRevisions_Current
        ON CmsRevisions (PageKey)
        WHERE IsCurrent = 1;
GO
