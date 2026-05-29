-- swarm/schema.sql
-- Crypto Sniper Platform Schema v1.0
-- Supabase project: hwgkgkhvbqaqotskcovb
-- Run once in Supabase SQL Editor
-- Last updated: 2026-05-29
--
-- Tables:
--   signals         - every fired signal + outcome tracking
--   agent_writes    - swarm blackboard (latest state per agent)
--   platform_events - cross-department event bus
--   partners        - referral partner registry
--   referral_events - every click/signup/payment tracked
--   partner_payouts - monthly payout records
--   subscribers     - TON subscriber lifecycle
--   ton_payments    - payment audit trail
--   agent_health    - swarm agent health monitoring

-- ============================================
-- SIGNAL INTELLIGENCE
-- ============================================

CREATE TABLE IF NOT EXISTS signals (
      id              BIGSERIAL PRIMARY KEY,
      fired_at        BIGINT,
      source          TEXT DEFAULT 'cex',
      chain           TEXT,
      symbol          TEXT NOT NULL,
      address         TEXT,
      pool            TEXT,
      dex_id          TEXT,
      interval        TEXT DEFAULT '1h',
      signal_label    TEXT NOT NULL,
      score           INTEGER DEFAULT 0,
      entry_price     REAL NOT NULL,
      stop_price      REAL NOT NULL,
      target_price    REAL NOT NULL,
      v_confirmed     INTEGER DEFAULT 0,
      t_confirmed     INTEGER DEFAULT 0,
      adx_confirmed   INTEGER DEFAULT 0,
      p_confirmed     INTEGER DEFAULT 0,
      r_confirmed     INTEGER DEFAULT 0,
      rel_vol         REAL DEFAULT 0,
      z_price         REAL DEFAULT 0,
      price_4h        REAL,
      price_24h       REAL,
      price_48h       REAL,
      price_72h       REAL,
      pct_4h          REAL,
      pct_24h         REAL,
      pct_48h         REAL,
      pct_72h         REAL,
      outcome         TEXT,
      resolved_at     BIGINT,
      resolved_pct    REAL,
      resolved_hrs    REAL,
      notes           TEXT DEFAULT '',
      exchange        TEXT DEFAULT 'binance',
      conviction      INTEGER DEFAULT 0,
      department      TEXT DEFAULT 'signal',
      referral_code   TEXT,
      partner_id      BIGINT,
      created_at      TIMESTAMPTZ DEFAULT NOW()
  );

CREATE INDEX IF NOT EXISTS idx_signals_pending
    ON signals(outcome, fired_at)
    WHERE outcome IS NULL;

CREATE INDEX IF NOT EXISTS idx_signals_symbol
    ON signals(symbol, created_at DESC);

-- ============================================
-- SWARM BLACKBOARD
-- ============================================

CREATE TABLE IF NOT EXISTS agent_writes (
      id          BIGSERIAL PRIMARY KEY,
      department  TEXT NOT NULL,
      agent       TEXT NOT NULL,
      namespace   TEXT NOT NULL,
      data        JSONB NOT NULL DEFAULT '{}',
      written_at  TIMESTAMPTZ DEFAULT NOW(),
      run_ms      INT,
      error       TEXT,
      UNIQUE(department, agent, namespace)
  );

CREATE INDEX IF NOT EXISTS idx_agent_writes_lookup
    ON agent_writes(department, namespace);

-- ============================================
-- PLATFORM EVENT BUS
-- ============================================

CREATE TABLE IF NOT EXISTS platform_events (
      id          BIGSERIAL PRIMARY KEY,
      event_type  TEXT NOT NULL,
      source_dept TEXT NOT NULL,
      payload     JSONB NOT NULL DEFAULT '{}',
      created_at  TIMESTAMPTZ DEFAULT NOW(),
      processed   BOOL DEFAULT FALSE
  );

CREATE INDEX IF NOT EXISTS idx_events_unprocessed
    ON platform_events(processed, created_at)
    WHERE processed = FALSE;

-- ============================================
-- PARTNERS AND REFERRALS
-- ============================================

CREATE TABLE IF NOT EXISTS partners (
      id                  BIGSERIAL PRIMARY KEY,
      name                TEXT NOT NULL,
      handle              TEXT,
      telegram_id         TEXT,
      referral_code       TEXT UNIQUE NOT NULL,
      ton_wallet          TEXT,
      revenue_share_pct   REAL DEFAULT 30.0,
      status              TEXT DEFAULT 'ACTIVE',
      revoked_at          TIMESTAMPTZ,
      revoked_reason      TEXT,
      total_referrals     INTEGER DEFAULT 0,
      active_subs         INTEGER DEFAULT 0,
      total_earned_ton    REAL DEFAULT 0,
      community_name      TEXT,
      community_size      INTEGER,
      community_url       TEXT,
      notes               TEXT,
      created_at          TIMESTAMPTZ DEFAULT NOW()
  );

CREATE UNIQUE INDEX IF NOT EXISTS idx_partners_active_code
    ON partners(referral_code)
    WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS referral_events (
      id              BIGSERIAL PRIMARY KEY,
      referral_code   TEXT NOT NULL,
      partner_id      BIGINT REFERENCES partners(id),
      telegram_id     TEXT NOT NULL,
      event_type      TEXT NOT NULL,
      ton_amount      REAL DEFAULT 0,
      share_amount    REAL DEFAULT 0,
      share_paid      BOOL DEFAULT FALSE,
      created_at      TIMESTAMPTZ DEFAULT NOW()
  );

CREATE INDEX IF NOT EXISTS idx_referral_events_partner
    ON referral_events(partner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS partner_payouts (
      id              BIGSERIAL PRIMARY KEY,
      partner_id      BIGINT REFERENCES partners(id),
      period_start    TIMESTAMPTZ,
      period_end      TIMESTAMPTZ,
      total_subs      INTEGER DEFAULT 0,
      total_ton       REAL DEFAULT 0,
      share_pct       REAL DEFAULT 30.0,
      payout_ton      REAL DEFAULT 0,
      tx_hash         TEXT,
      status          TEXT DEFAULT 'PENDING',
      paid_at         TIMESTAMPTZ,
      created_at      TIMESTAMPTZ DEFAULT NOW()
  );

-- ============================================
-- SUBSCRIBERS AND TON PAYMENTS
-- ============================================

CREATE TABLE IF NOT EXISTS subscribers (
      id                  BIGSERIAL PRIMARY KEY,
      telegram_id         TEXT UNIQUE NOT NULL,
      telegram_handle     TEXT,
      plan                TEXT DEFAULT 'FREE',
      ton_wallet          TEXT,
      payment_memo        TEXT UNIQUE,
      subscribed_at       TIMESTAMPTZ,
      expires_at          TIMESTAMPTZ,
      last_payment_at     TIMESTAMPTZ,
      last_ton_amount     REAL,
      total_paid_ton      REAL DEFAULT 0,
      payment_count       INTEGER DEFAULT 0,
      status              TEXT DEFAULT 'ACTIVE',
      group_access        BOOL DEFAULT FALSE,
      churn_risk          FLOAT DEFAULT 0.0,
      referral_code       TEXT,
      partner_id          BIGINT REFERENCES partners(id),
      joined_via          TEXT,
      created_at          TIMESTAMPTZ DEFAULT NOW()
  );

CREATE INDEX IF NOT EXISTS idx_subscribers_expires
    ON subscribers(expires_at)
    WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS ton_payments (
      id              BIGSERIAL PRIMARY KEY,
      telegram_id     TEXT NOT NULL,
      ton_tx_hash     TEXT UNIQUE,
      ton_amount      REAL NOT NULL,
      usd_value       REAL,
      memo            TEXT,
      confirmed_at    TIMESTAMPTZ,
      plan_granted    TEXT,
      period_days     INTEGER DEFAULT 30,
      referral_code   TEXT,
      partner_id      BIGINT REFERENCES partners(id),
      created_at      TIMESTAMPTZ DEFAULT NOW()
  );

-- ============================================
-- AGENT HEALTH MONITORING
-- ============================================

CREATE TABLE IF NOT EXISTS agent_health (
      id          BIGSERIAL PRIMARY KEY,
      department  TEXT NOT NULL,
      agent       TEXT NOT NULL,
      status      TEXT NOT NULL,
      checked_at  TIMESTAMPTZ DEFAULT NOW(),
      details     JSONB DEFAULT '{}'
  );

CREATE INDEX IF NOT EXISTS idx_agent_health_recent
    ON agent_health(department, agent, checked_at DESC);
