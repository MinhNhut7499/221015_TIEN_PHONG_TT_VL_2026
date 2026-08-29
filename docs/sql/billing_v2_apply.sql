-- ============================================================
-- BILLING v2 — APPLY (reset any earlier billing tables, then create v2)
-- Chay 1 lan. AN TOAN: cac bang billing moi tao, chua co du lieu that
-- (BILLING_ENABLED van dang False, chua co thanh toan nao).
--
-- Script nay:
--   1) Go cac bang/cot billing cu (neu co) — vi schema cu khong khop v2.
--   2) Tao lai day du schema v2 (6 bang + 4 cot Users).
-- Sau khi chay xong, restart server de ensure_plans_seeded() nap lai cac goi.
-- ============================================================

SET XACT_ABORT ON;
GO

-- ── 1) RESET: go FK + cot Users + 3 bang billing cu (idempotent) ─────────────
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Users_CurrentPlan')
    ALTER TABLE Users DROP CONSTRAINT FK_Users_CurrentPlan;
GO

-- Go default-constraint roi go cot (ten default do SQL Server tu sinh).
DECLARE @sql NVARCHAR(MAX) = N'';
SELECT @sql = @sql + N'ALTER TABLE Users DROP CONSTRAINT ' + QUOTENAME(dc.name) + N';'
FROM sys.default_constraints dc
JOIN sys.columns c ON c.object_id = dc.parent_object_id AND c.column_id = dc.parent_column_id
WHERE dc.parent_object_id = OBJECT_ID('dbo.Users')
  AND c.name IN ('TokenBalance', 'CurrentPlanId', 'PlanActivatedAt', 'PlanExpiresAt');
IF @sql <> N'' EXEC sp_executesql @sql;
GO

IF COL_LENGTH('dbo.Users', 'TokenBalance')   IS NOT NULL ALTER TABLE Users DROP COLUMN TokenBalance;
GO
IF COL_LENGTH('dbo.Users', 'CurrentPlanId')  IS NOT NULL ALTER TABLE Users DROP COLUMN CurrentPlanId;
GO
IF COL_LENGTH('dbo.Users', 'PlanActivatedAt') IS NOT NULL ALTER TABLE Users DROP COLUMN PlanActivatedAt;
GO
IF COL_LENGTH('dbo.Users', 'PlanExpiresAt')  IS NOT NULL ALTER TABLE Users DROP COLUMN PlanExpiresAt;
GO

-- Drop child-first (FK order). These are brand-new + empty.
IF OBJECT_ID('dbo.Refunds', 'U')             IS NOT NULL DROP TABLE Refunds;
IF OBJECT_ID('dbo.PaymentCallbacks', 'U')    IS NOT NULL DROP TABLE PaymentCallbacks;
IF OBJECT_ID('dbo.TokenLedger', 'U')         IS NOT NULL DROP TABLE TokenLedger;
IF OBJECT_ID('dbo.PaymentTransactions', 'U') IS NOT NULL DROP TABLE PaymentTransactions;
IF OBJECT_ID('dbo.RevenueDaily', 'U')        IS NOT NULL DROP TABLE RevenueDaily;
IF OBJECT_ID('dbo.Plans', 'U')               IS NOT NULL DROP TABLE Plans;
GO

-- ── 2) CREATE v2 schema ──────────────────────────────────────────────────────
CREATE TABLE Plans (
    PlanId        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    PlanCode      NVARCHAR(50)  NOT NULL UNIQUE,
    PlanName      NVARCHAR(255) NOT NULL,
    PlanType      NVARCHAR(20)  NOT NULL,               -- 'token_pack' | 'subscription'
    PriceAmount   BIGINT        NOT NULL DEFAULT 0,
    Currency      NVARCHAR(3)   NOT NULL DEFAULT 'VND',
    TokenAmount   BIGINT        NOT NULL DEFAULT 0,
    DurationDays  INT           NULL,
    BenefitsJson  NVARCHAR(MAX) NULL,
    SortOrder     INT           NOT NULL DEFAULT 0,
    IsActive      BIT           NOT NULL DEFAULT 1,
    CreatedAt     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt     DATETIME2     NULL
);
GO

ALTER TABLE Users ADD
    TokenBalance     BIGINT           NOT NULL DEFAULT 0,
    CurrentPlanId    UNIQUEIDENTIFIER NULL,
    PlanActivatedAt  DATETIME2        NULL,
    PlanExpiresAt    DATETIME2        NULL;
GO
ALTER TABLE Users ADD CONSTRAINT FK_Users_CurrentPlan
    FOREIGN KEY (CurrentPlanId) REFERENCES Plans(PlanId);
GO

CREATE TABLE TokenLedger (
    LedgerId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    UserId         UNIQUEIDENTIFIER NOT NULL,
    Delta          BIGINT           NOT NULL,
    BalanceAfter   BIGINT           NOT NULL,
    Reason         NVARCHAR(50)     NOT NULL,
    RefType        NVARCHAR(30)     NULL,
    RefId          NVARCHAR(100)    NULL,
    IdempotencyKey NVARCHAR(150)    NOT NULL UNIQUE,
    Note           NVARCHAR(255)    NULL,
    CreatedBy      NVARCHAR(100)    NULL,
    CreatedAt      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_Ledger_User FOREIGN KEY (UserId) REFERENCES Users(UserId)
);
CREATE INDEX IX_Ledger_User_CreatedAt ON TokenLedger(UserId, CreatedAt DESC);
GO

CREATE TABLE PaymentTransactions (
    TransactionId    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    UserId           UNIQUEIDENTIFIER NOT NULL,
    PlanId           UNIQUEIDENTIFIER NULL,
    Provider         NVARCHAR(20)     NOT NULL,
    OrderRef         NVARCHAR(100)    NOT NULL UNIQUE,
    ProviderTxnId    NVARCHAR(100)    NULL,
    Amount           BIGINT           NOT NULL,
    Currency         NVARCHAR(3)      NOT NULL DEFAULT 'VND',
    TokenAmount      BIGINT           NOT NULL DEFAULT 0,
    PlanSnapshotJson NVARCHAR(MAX)    NULL,
    Status           NVARCHAR(20)     NOT NULL DEFAULT 'pending',
    FailureReason    NVARCHAR(255)    NULL,
    ProviderRespCode NVARCHAR(20)     NULL,
    IdempotencyKey   NVARCHAR(100)    NULL UNIQUE,
    ClientIp         NVARCHAR(64)     NULL,
    CreatedAt        DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    ExpiresAt        DATETIME2        NULL,
    PaidAt           DATETIME2        NULL,
    UpdatedAt        DATETIME2        NULL,
    CONSTRAINT FK_PayTxn_User FOREIGN KEY (UserId) REFERENCES Users(UserId),
    CONSTRAINT FK_PayTxn_Plan FOREIGN KEY (PlanId) REFERENCES Plans(PlanId)
);
CREATE INDEX IX_PayTxn_Status_CreatedAt ON PaymentTransactions(Status, CreatedAt);
CREATE INDEX IX_PayTxn_User_CreatedAt   ON PaymentTransactions(UserId, CreatedAt DESC);
CREATE INDEX IX_PayTxn_PaidAt           ON PaymentTransactions(PaidAt) WHERE PaidAt IS NOT NULL;
GO

CREATE TABLE PaymentCallbacks (
    CallbackId     UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    TransactionId  UNIQUEIDENTIFIER NULL,
    Provider       NVARCHAR(20)     NOT NULL,
    Source         NVARCHAR(20)     NOT NULL,
    RawPayload     NVARCHAR(MAX)    NOT NULL,
    SignatureValid BIT              NOT NULL,
    ResultNote     NVARCHAR(255)    NULL,
    ReceivedAt     DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_Callback_Txn ON PaymentCallbacks(TransactionId);
GO

CREATE TABLE Refunds (
    RefundId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    TransactionId  UNIQUEIDENTIFIER NOT NULL,
    Amount         BIGINT           NOT NULL,
    TokenClawback  BIGINT           NOT NULL DEFAULT 0,
    Status         NVARCHAR(20)     NOT NULL DEFAULT 'pending',
    Provider       NVARCHAR(20)     NOT NULL,
    ProviderRefId  NVARCHAR(100)    NULL,
    Reason         NVARCHAR(255)    NULL,
    CreatedBy      NVARCHAR(100)    NOT NULL,
    CreatedAt      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt      DATETIME2        NULL,
    CONSTRAINT FK_Refund_Txn FOREIGN KEY (TransactionId) REFERENCES PaymentTransactions(TransactionId)
);
CREATE INDEX IX_Refund_Txn ON Refunds(TransactionId);
GO

CREATE TABLE RevenueDaily (
    RevenueDate    DATE        NOT NULL,
    Currency       NVARCHAR(3) NOT NULL,
    GrossAmount    BIGINT      NOT NULL DEFAULT 0,
    RefundAmount   BIGINT      NOT NULL DEFAULT 0,
    NetAmount      BIGINT      NOT NULL DEFAULT 0,
    TxnCount       INT         NOT NULL DEFAULT 0,
    TokensSold     BIGINT      NOT NULL DEFAULT 0,
    UpdatedAt      DATETIME2   NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_RevenueDaily PRIMARY KEY (RevenueDate, Currency)
);
GO
