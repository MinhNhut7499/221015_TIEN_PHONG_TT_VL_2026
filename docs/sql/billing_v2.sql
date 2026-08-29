-- ============================================================
-- BILLING / TOKEN  v2  —  SCHEMA MIGRATION (SQL Server)
-- Chay 1 lan tren database architecture_ai.
-- An toan chay lai: moi khoi boc trong IF NOT EXISTS / cot kiem tra truoc.
--
-- Nguyen tac:
--   * TokenLedger la nguon su that; Users.TokenBalance chi la cache.
--   * Moi cot tien la BIGINT + co Currency (chong SUM(INT) overflow, da-tien-te).
--   * KHONG ON DELETE CASCADE tren bang tien (giu audit/ke toan).
--   * IdempotencyKey UNIQUE tren TokenLedger = la chan cuoi chong double-spend.
--   * KHONG dat trigger len cac bang nay (xung dot OUTPUT clause).
-- ============================================================

SET XACT_ABORT ON;
GO

-- 1) Plans: token_pack | subscription. Benefit cua tier nam o BenefitsJson.
IF OBJECT_ID('dbo.Plans', 'U') IS NULL
BEGIN
    CREATE TABLE Plans (
        PlanId        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        PlanCode      NVARCHAR(50)  NOT NULL UNIQUE,        -- 'free','pro','premium','pack_100',...
        PlanName      NVARCHAR(255) NOT NULL,
        PlanType      NVARCHAR(20)  NOT NULL,               -- 'token_pack' | 'subscription'
        PriceAmount   BIGINT        NOT NULL DEFAULT 0,     -- don vi nho nhat cua Currency (VND = dong)
        Currency      NVARCHAR(3)   NOT NULL DEFAULT 'VND',
        TokenAmount   BIGINT        NOT NULL DEFAULT 0,     -- token cap khi mua
        DurationDays  INT           NULL,                   -- subscription length; NULL voi pack
        BenefitsJson  NVARCHAR(MAX) NULL,                   -- vd {"cost_per_analysis":0.5,"daily_quota":100}
        SortOrder     INT           NOT NULL DEFAULT 0,
        IsActive      BIT           NOT NULL DEFAULT 1,      -- soft-delete; KHONG hard-delete
        CreatedAt     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt     DATETIME2     NULL
    );
END
GO

-- 2) Vi token (cache) + subscription hien tai tren Users
IF COL_LENGTH('dbo.Users', 'TokenBalance') IS NULL
    ALTER TABLE Users ADD TokenBalance BIGINT NOT NULL DEFAULT 0;  -- CACHE; su that = TokenLedger
GO
IF COL_LENGTH('dbo.Users', 'CurrentPlanId') IS NULL
    ALTER TABLE Users ADD CurrentPlanId UNIQUEIDENTIFIER NULL;
GO
IF COL_LENGTH('dbo.Users', 'PlanActivatedAt') IS NULL
    ALTER TABLE Users ADD PlanActivatedAt DATETIME2 NULL;
GO
IF COL_LENGTH('dbo.Users', 'PlanExpiresAt') IS NULL
    ALTER TABLE Users ADD PlanExpiresAt DATETIME2 NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_Users_CurrentPlan')
    ALTER TABLE Users ADD CONSTRAINT FK_Users_CurrentPlan
        FOREIGN KEY (CurrentPlanId) REFERENCES Plans(PlanId);  -- NO ACTION
GO

-- 3) TokenLedger: APPEND-ONLY, nguon su that. IdempotencyKey = la chan double-spend.
IF OBJECT_ID('dbo.TokenLedger', 'U') IS NULL
BEGIN
    CREATE TABLE TokenLedger (
        LedgerId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        UserId         UNIQUEIDENTIFIER NOT NULL,
        Delta          BIGINT           NOT NULL,            -- +cong / -tru
        BalanceAfter   BIGINT           NOT NULL,            -- lay nguyen tu qua OUTPUT
        Reason         NVARCHAR(50)     NOT NULL,            -- purchase|analysis_hold|analysis_refund|
                                                            -- signup_bonus|admin_grant|admin_revoke|
                                                            -- subscription_grant|refund_clawback
        RefType        NVARCHAR(30)     NULL,                -- 'payment'|'analysis'|'refund'|'admin'
        RefId          NVARCHAR(100)    NULL,
        IdempotencyKey NVARCHAR(150)    NOT NULL UNIQUE,     -- vd 'purchase:<txnId>','hold:<requestId>'
        Note           NVARCHAR(255)    NULL,
        CreatedBy      NVARCHAR(100)    NULL,                -- 'system'|'gateway:vnpay'|admin userId
        CreatedAt      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_Ledger_User FOREIGN KEY (UserId) REFERENCES Users(UserId)  -- NO ACTION
    );
    CREATE INDEX IX_Ledger_User_CreatedAt ON TokenLedger(UserId, CreatedAt DESC);
END
GO

-- 4) PaymentTransactions: state machine cua 1 don thanh toan
IF OBJECT_ID('dbo.PaymentTransactions', 'U') IS NULL
BEGIN
    CREATE TABLE PaymentTransactions (
        TransactionId    UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        UserId           UNIQUEIDENTIFIER NOT NULL,
        PlanId           UNIQUEIDENTIFIER NULL,
        Provider         NVARCHAR(20)     NOT NULL,           -- 'vnpay'|'momo'|'stripe'
        OrderRef         NVARCHAR(100)    NOT NULL UNIQUE,    -- ma cua minh gui gateway (vnp_TxnRef)
        ProviderTxnId    NVARCHAR(100)    NULL,               -- id ben gateway (vnp_TransactionNo)
        Amount           BIGINT           NOT NULL,
        Currency         NVARCHAR(3)      NOT NULL DEFAULT 'VND',
        TokenAmount      BIGINT           NOT NULL DEFAULT 0, -- snapshot token se cap
        PlanSnapshotJson NVARCHAR(MAX)    NULL,               -- snapshot plan luc mua
        Status           NVARCHAR(20)     NOT NULL DEFAULT 'pending',
            -- pending|succeeded|failed|expired|cancelled|refunded|partially_refunded
        FailureReason    NVARCHAR(255)    NULL,
        ProviderRespCode NVARCHAR(20)     NULL,
        IdempotencyKey   NVARCHAR(100)    NULL UNIQUE,        -- client-supplied: chong tao don trung
        ClientIp         NVARCHAR(64)     NULL,
        CreatedAt        DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
        ExpiresAt        DATETIME2        NULL,               -- han thanh toan (vd +15 phut)
        PaidAt           DATETIME2        NULL,
        UpdatedAt        DATETIME2        NULL,
        CONSTRAINT FK_PayTxn_User FOREIGN KEY (UserId) REFERENCES Users(UserId),  -- NO ACTION
        CONSTRAINT FK_PayTxn_Plan FOREIGN KEY (PlanId) REFERENCES Plans(PlanId)
    );
    CREATE INDEX IX_PayTxn_Status_CreatedAt ON PaymentTransactions(Status, CreatedAt);
    CREATE INDEX IX_PayTxn_User_CreatedAt   ON PaymentTransactions(UserId, CreatedAt DESC);
    CREATE INDEX IX_PayTxn_PaidAt           ON PaymentTransactions(PaidAt) WHERE PaidAt IS NOT NULL;
END
GO

-- 5) PaymentCallbacks: luu NGUYEN moi callback/IPN/querydr de forensic + replay
IF OBJECT_ID('dbo.PaymentCallbacks', 'U') IS NULL
BEGIN
    CREATE TABLE PaymentCallbacks (
        CallbackId     UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        TransactionId  UNIQUEIDENTIFIER NULL,
        Provider       NVARCHAR(20)     NOT NULL,
        Source         NVARCHAR(20)     NOT NULL,            -- 'ipn'|'return'|'querydr'
        RawPayload     NVARCHAR(MAX)    NOT NULL,            -- query/body day du (KHONG chua secret)
        SignatureValid BIT              NOT NULL,
        ResultNote     NVARCHAR(255)    NULL,                -- 'credited'|'duplicate'|'amount_mismatch'...
        ReceivedAt     DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX IX_Callback_Txn ON PaymentCallbacks(TransactionId);
END
GO

-- 6) Refunds: ho tro full/partial refund + clawback token
IF OBJECT_ID('dbo.Refunds', 'U') IS NULL
BEGIN
    CREATE TABLE Refunds (
        RefundId       UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        TransactionId  UNIQUEIDENTIFIER NOT NULL,
        Amount         BIGINT           NOT NULL,            -- so tien hoan
        TokenClawback  BIGINT           NOT NULL DEFAULT 0,  -- so token thu hoi
        Status         NVARCHAR(20)     NOT NULL DEFAULT 'pending', -- pending|succeeded|failed
        Provider       NVARCHAR(20)     NOT NULL,
        ProviderRefId  NVARCHAR(100)    NULL,
        Reason         NVARCHAR(255)    NULL,
        CreatedBy      NVARCHAR(100)    NOT NULL,            -- admin userId
        CreatedAt      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt      DATETIME2        NULL,
        CONSTRAINT FK_Refund_Txn FOREIGN KEY (TransactionId) REFERENCES PaymentTransactions(TransactionId)
    );
    CREATE INDEX IX_Refund_Txn ON Refunds(TransactionId);
END
GO

-- 7) RevenueDaily: rollup doanh thu (chong overflow + bao cao nhanh o 100k+)
IF OBJECT_ID('dbo.RevenueDaily', 'U') IS NULL
BEGIN
    CREATE TABLE RevenueDaily (
        RevenueDate    DATE        NOT NULL,
        Currency       NVARCHAR(3) NOT NULL,
        GrossAmount    BIGINT      NOT NULL DEFAULT 0,       -- tong succeeded
        RefundAmount   BIGINT      NOT NULL DEFAULT 0,
        NetAmount      BIGINT      NOT NULL DEFAULT 0,
        TxnCount       INT         NOT NULL DEFAULT 0,
        TokensSold     BIGINT      NOT NULL DEFAULT 0,
        UpdatedAt      DATETIME2   NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_RevenueDaily PRIMARY KEY (RevenueDate, Currency)
    );
END
GO
