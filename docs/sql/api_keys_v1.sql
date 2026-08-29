-- ============================================================
-- PROVIDER API-KEY MANAGEMENT  v1  —  SCHEMA MIGRATION (SQL Server)
-- Chay 1 lan tren database architecture_ai. An toan chay lai (IF NOT EXISTS).
--
-- Nguyen tac:
--   * Key API luu MA HOA (Fernet) o cot EncryptedKey — KHONG bao gio plaintext.
--   * Last4 chi de hien thi masked tren UI (****abcd).
--   * Nhieu key / 1 provider: resolver chon row IsActive co Priority NHO NHAT.
--   * ProviderConfigEpoch = counter 1 hang, bump moi lan doi key, de cac worker
--     (prod chay nhieu uvicorn worker) hoi tu key moi ma KHONG can restart.
-- ============================================================

SET XACT_ABORT ON;
GO

-- 1) Bang luu key API theo provider (key da ma hoa)
IF OBJECT_ID('dbo.ProviderApiKeys', 'U') IS NULL
BEGIN
    CREATE TABLE ProviderApiKeys (
        KeyId           UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        Provider        NVARCHAR(50)  NOT NULL,            -- 'gemini'|'openai'|'deepseek'|'xai'
        Label           NVARCHAR(100) NOT NULL,            -- ten goi nho do admin dat
        EncryptedKey    NVARCHAR(MAX) NOT NULL,            -- Fernet ciphertext (khong plaintext)
        Last4           NVARCHAR(8)   NULL,                -- hien thi masked
        ModelOverride   NVARCHAR(100) NULL,                -- NULL -> dung settings.X_MODEL
        BaseUrlOverride NVARCHAR(255) NULL,                -- NULL -> dung settings.X_BASE_URL
        Priority        INT           NOT NULL DEFAULT 100, -- nho hon = uu tien cao hon
        IsActive        BIT           NOT NULL DEFAULT 1,
        LastUsedAt      DATETIME2     NULL,
        CreatedAt       DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2     NULL
    );
END
GO

-- Index phuc vu truy van resolver: theo provider, chi key dang bat, sap theo uu tien
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ProviderApiKeys_Lookup')
    CREATE INDEX IX_ProviderApiKeys_Lookup
        ON ProviderApiKeys (Provider, IsActive, Priority);
GO

-- 2) Counter epoch (1 hang) — bump moi lan ghi key de cac worker rebuild service
IF OBJECT_ID('dbo.ProviderConfigEpoch', 'U') IS NULL
BEGIN
    CREATE TABLE ProviderConfigEpoch (
        Id        INT       NOT NULL PRIMARY KEY,
        Epoch     BIGINT    NOT NULL DEFAULT 0,
        UpdatedAt DATETIME2 NULL
    );
END
GO

-- Seed hang epoch duy nhat (Id = 1) neu chua co
IF NOT EXISTS (SELECT 1 FROM ProviderConfigEpoch WHERE Id = 1)
    INSERT INTO ProviderConfigEpoch (Id, Epoch, UpdatedAt) VALUES (1, 0, SYSUTCDATETIME());
GO
