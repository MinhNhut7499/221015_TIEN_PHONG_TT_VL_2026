-- ============================================================
-- HYBRID APP LOGIN (Cloud-Sync Polling)  v1  —  SCHEMA MIGRATION (SQL Server)
-- Chay 1 lan tren database architecture_ai. An toan chay lai (IF NOT EXISTS).
--
-- Muc dich:
--   Dang nhap Google OAuth tren mobile app (Android/iOS) khong dung deep link.
--   App mo Chrome Custom Tab -> Google -> backend ghi JWT vao bang nay theo
--   SessionId -> web (chay trong WebView) polling lay token.
--
-- Nguyen tac:
--   * SessionId = UUID v4 do WEB tao (khong co default server-side).
--   * One-time use: row bi XOA ngay khi token duoc claim (poll lan dau).
--   * TTL: ExpiresAt (mac dinh 10 phut, cau hinh qua LOGIN_SESSION_TTL_MIN).
--   * KHONG dat FK cung toi Users (UserId chi de audit) — tranh rang buoc xoa.
-- ============================================================

SET XACT_ABORT ON;
GO

IF OBJECT_ID('dbo.LoginSessions', 'U') IS NULL
BEGIN
    CREATE TABLE LoginSessions (
        SessionId     NVARCHAR(36)  NOT NULL PRIMARY KEY,   -- UUID v4 do web tao
        Status        NVARCHAR(20)  NOT NULL
                          CONSTRAINT DF_LoginSessions_Status DEFAULT 'pending',  -- 'pending' | 'completed'
        AccessToken   NVARCHAR(MAX) NULL,
        RefreshToken  NVARCHAR(MAX) NULL,
        UserId        NVARCHAR(36)  NULL,                    -- user hoan tat login (tham chieu Users.UserId)
        CreatedAt     DATETIME2     NOT NULL
                          CONSTRAINT DF_LoginSessions_CreatedAt DEFAULT SYSUTCDATETIME(),
        ExpiresAt     DATETIME2     NOT NULL,
        CompletedAt   DATETIME2     NULL
    );
END
GO

-- Phuc vu cleanup theo han su dung (DELETE WHERE ExpiresAt < utcnow)
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LoginSessions_ExpiresAt')
    CREATE INDEX IX_LoginSessions_ExpiresAt ON LoginSessions (ExpiresAt);
GO
