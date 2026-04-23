-- init_taris_kb.sql — Phase 1 schema for the taris_kb database
-- Run once on the VPS Postgres cluster (as superuser or taris_kb_writer owner).
-- All statements are idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Phase 1:  kb_documents, kb_chunks, kb_memory, kb_conversations, kb_messages, kb_query_cache
-- Run with:
--   psql -U postgres -c "CREATE DATABASE taris_kb;" 2>/dev/null || true
--   psql -U postgres -d taris_kb -f init_taris_kb.sql

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector

-- ── Role (safe to re-run) ─────────────────────────────────────────────────────
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taris_kb_writer') THEN
    -- Password is set via ALTER ROLE after creation; placeholder here
    CREATE ROLE taris_kb_writer LOGIN;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE taris_kb TO taris_kb_writer;
GRANT USAGE ON SCHEMA public TO taris_kb_writer;

-- ── Documents ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id        UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_chat_id BIGINT       NOT NULL,
    title         TEXT         NOT NULL,
    mime          TEXT,
    sha256        TEXT         UNIQUE,
    source        TEXT         DEFAULT 'taris_upload',   -- taris_upload | web_crawl | manual
    structure     JSONB,                                  -- docling outline: chapters/sections
    created_at    TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_doc_owner ON kb_documents(owner_chat_id);

-- ── Structure-aware chunks ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id    BIGSERIAL    PRIMARY KEY,
    doc_id      UUID         REFERENCES kb_documents(doc_id) ON DELETE CASCADE,
    chunk_idx   INT          NOT NULL,
    section     TEXT,
    text        TEXT         NOT NULL,
    tokens      INT,
    embedding   vector(384),                              -- multilingual-e5-small, 384-dim
    fts         tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    metadata    JSONB,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(doc_id, chunk_idx);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_fts ON kb_chunks USING gin(fts);
-- HNSW index for vector search (created after data exists for better build quality)
-- CREATE INDEX CONCURRENTLY idx_kb_chunks_vec ON kb_chunks USING hnsw (embedding vector_cosine_ops);

-- ── Memory (3-tier per user per agent) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_memory (
    chat_id     BIGINT       NOT NULL,
    tier        TEXT         NOT NULL CHECK (tier IN ('short', 'middle', 'long')),
    seq         BIGSERIAL,
    role        TEXT         NOT NULL,   -- user | assistant | system | summary
    content     TEXT         NOT NULL,
    source_ids  BIGINT[],               -- parent rows (middle/long compaction)
    tokens      INT,
    created_at  TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (chat_id, tier, seq)
);
CREATE INDEX IF NOT EXISTS idx_kb_memory_lookup ON kb_memory(chat_id, tier, created_at DESC);

-- ── Conversation log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_conversations (
    conv_id     UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id     BIGINT       NOT NULL,
    started_at  TIMESTAMPTZ  DEFAULT NOW(),
    last_at     TIMESTAMPTZ  DEFAULT NOW(),
    meta        JSONB
);
CREATE INDEX IF NOT EXISTS idx_kb_conv_chat ON kb_conversations(chat_id, last_at DESC);

CREATE TABLE IF NOT EXISTS kb_messages (
    msg_id      BIGSERIAL    PRIMARY KEY,
    conv_id     UUID         REFERENCES kb_conversations(conv_id) ON DELETE CASCADE,
    role        TEXT,
    content     TEXT,
    chunks_used BIGINT[],               -- → kb_chunks.chunk_id
    grounding   JSONB,                  -- Variant 2: Google citations
    latency_ms  INT,
    mode        TEXT,                   -- n8n | google
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_msg_conv ON kb_messages(conv_id, created_at);

-- ── Query cache (Worksafety pattern) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_query_cache (
    query_sha256 TEXT         PRIMARY KEY,
    mode         TEXT,
    response     JSONB,
    ttl_sec      INT          DEFAULT 1800,
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    expires_at   TIMESTAMPTZ  DEFAULT NOW() + INTERVAL '1800 seconds'
);
CREATE INDEX IF NOT EXISTS idx_kb_cache_expiry ON kb_query_cache(expires_at);

-- ── Grants ────────────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO taris_kb_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO taris_kb_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO taris_kb_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO taris_kb_writer;

-- ── Sanity check ─────────────────────────────────────────────────────────────
SELECT
    table_name,
    pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS size
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
