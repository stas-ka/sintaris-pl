# KB Quality Comparison — Taris Remote KB vs Worksafety N8N Bot

**Version:** 2026.4  
**When to read:** Before improving the KB RAG pipeline, planning embedding upgrades, or evaluating KB answer quality for regulatory/legal documents.

---

## 1. System Overview

| Dimension | Taris Remote KB | Worksafety N8N Bot |
|---|---|---|
| **Architecture** | FastAPI MCP server + pgvector + LLM synthesis | N8N workflow + PostgreSQL + pgvector + direct answer |
| **DB** | PostgreSQL 14, schema `taris_kb` | PostgreSQL 15+, 31 tables `safetywork_*` |
| **Embedding model** | `all-MiniLM-L6-v2` (fastembed, 384-dim) | `text-embedding-3-small` (OpenAI, 1536-dim) |
| **Embedding dim** | 384 | 1536 |
| **Embedding source** | Local (CPU, no cost) | OpenAI API (cost per token) |
| **Retrieval** | cosine similarity on `vec_embeddings` + FTS5 BM25 hybrid (RRF k=60) | vector similarity ×0.50 + metadata match ×0.50 + chunk type bonus (0.05–0.30) + LDA topic bonus (0.10) |
| **Query classification** | 3 types: simple / factual / contextual | 5 types: definition / procedure / regulation / example / general |
| **Result ordering** | By score (descending) | By `chunk_index` (document order) |
| **Chunks per query** | top_k=5 (default `MCP_REMOTE_TOP_K`) | 5–10 (adaptive) |
| **Chapter metadata** | None | Cyrillic regex extracts Roman numeral chapters (I–XX) from query for SQL filter |
| **Topic modeling** | None | LDA (16 topics) for scoring signal |
| **LLM synthesis** | ✅ `ask_llm_with_history`, system prompt + context | ❌ Returns raw top chunk text (no LLM synthesis) |
| **Language support** | ru / en / de (auto via `_lang(chat_id)`) | ru only |
| **User isolation (RBAC)** | ✅ per `owner_chat_id` in SQL | ❌ shared corpus |
| **Document formats** | RTF, PDF, DOCX, .doc | RTF, PDF, DOCX |
| **Max file size** | Telegram limit (20MB) | 50MB |
| **Source attribution** | ✅ Sources footer (i18n key `remote_kb_sources`) | ❌ No source citation |
| **Circuit breaker** | ✅ `_CB` opens after 3 failures, 60s cooldown | ❌ No circuit breaker |
| **Deployment** | VPS Docker + MCP server sidecar | N8N webhook at `automata.dev2null.de` |

---

## 2. Scoring Formula Comparison

### Worksafety hybrid score (per chunk)

```
score = (cosine_similarity × 0.50)
      + (metadata_match    × 0.50)   ← doc number in query (e.g. "883Н")
      + chunk_type_bonus              ← 0.30 heading, 0.15 numbered list, 0.05 paragraph
      + lda_topic_bonus               ← 0.10 if top LDA topic matches query topic
```

Key feature: **Chapter metadata filter** — regex `[IVXLC]+\.` extracts Roman numeral chapter from
query → SQL `WHERE section LIKE '%IV%'` boosts recall for chapter-specific queries.

### Taris RRF score (per chunk)

```
score = RRF(vector_rank, bm25_rank, k=60)
      = 1/(k + r_vector) + 1/(k + r_bm25)
```

Simple and robust, but no domain-specific signals for regulatory documents.

---

## 3. Gap Analysis

| Gap | Impact | Difficulty | Priority |
|---|---|---|---|
| **384-dim vs 1536-dim embeddings** | Semantic precision: shorter vectors miss nuanced queries in regulatory language | High (requires re-indexing all docs) | P2 |
| **No chapter/article metadata extraction** | Can't filter "requirements under Section IV" type queries | Medium | P1 |
| **No doc-order result sorting** | Breaking up logical sequences in regulatory text (§1→§2→§3) | Low | P1 — easy fix |
| **3 vs 5 query types** | Definition queries treated same as procedure queries → wrong context selection | Medium | P2 |
| **No topic coherence scoring** | Off-topic chunks included if they pass cosine threshold | Medium | P3 |
| **No BM25 weight for regulatory terms** | Technical terms (номер приказа, ГОСТ, СНиП) not boosted | Low | P2 |

---

## 4. Taris Strengths Over Worksafety Bot

| Strength | Benefit |
|---|---|
| **LLM synthesis** | Answers are fluent summaries, not raw chunk text — better UX for non-experts |
| **Multilanguage** | Russian, German, English — Worksafety is Russian-only |
| **User isolation (RBAC)** | Each user's documents are private — critical for corporate KB use |
| **Source attribution footer** | Cites document sections in every reply — regulatory traceability |
| **Circuit breaker** | Graceful degradation when MCP server is unavailable |
| **Cyrillic filename restoration** | `_fix_doc_meta` restores original Russian filenames mangled by N8N |

---

## 5. Test Evaluation Methodology (Fuzzy Match)

Based on `Worksafety-superassistant/tests/rag_testing/test_rag.py`:

```python
from difflib import SequenceMatcher

def similarity(a: str, b: str) -> float:
    """Returns 0.0–1.0 similarity between expected and actual answer."""
    try:
        from fuzzywuzzy import fuzz
        return max(
            fuzz.partial_ratio(a, b),
            fuzz.token_sort_ratio(a, b),
            fuzz.token_set_ratio(a, b),
        ) / 100.0
    except ImportError:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
```

**Thresholds:**
- ≥ 0.90 → **PASS** (answer contains expected content)
- ≥ 0.70 → **WARNING** (partial match — answer covers topic but misses specific text)
- < 0.70 → **FAIL** (answer does not cover the expected content)

**Adjusted Taris threshold:** Taris uses 384-dim embeddings vs 1536-dim. Initial benchmark target is **0.60** (not 0.70) to account for lower embedding precision. Raise to 0.70 after P1 improvements are implemented.

---

## 6. Benchmark Test Queries (from Worksafety test_cases.csv)

These 10 queries target document `883Н` (Приказ Минтруда РФ от 11.12.2020 N 883Н — construction safety rules).
Upload `883Н_Охрана_труда_при_строительных_работах.rtf` from `Knowledges/+СТРОИТЕЛЬСТВО 6/Input/` to Taris KB before running live benchmark tests T240–T241.

| # | Query | Expected text fragment | Domain |
|---|---|---|---|
| 1 | Требования при работе на высоте | не менее двух | 883Н |
| 2 | Организация рабочего места | не менее 0,6 м | 883Н |
| 3 | Организационно-технологическая документация | проект производства работ | 883Н |
| 4 | Средства подмащивания | нагрузок, указанных | 883Н |
| 5 | Требования безопасности при буровых работах | пробурить контрольную | 883Н |
| 6 | СИЗ при строительных работах | специальная одежда | 883Н |
| 7 | Нарушения при строительных работах | необходимо немедленно | 883Н |
| 8 | Работа на высоте ограждения | не менее 1,1 м | 883Н |
| 9 | Требования к строительным машинам | о количестве | 883Н |
| 10 | Монтаж металлических конструкций | не применять | 883Н |

---

## 7. Document Upload Instructions (Worksafety RTF set)

### Relevant files to upload for benchmark testing

| File | Location | Size | Domain |
|---|---|---|---|
| `883Н_*.rtf` | `+СТРОИТЕЛЬСТВО 6/Input/` | ~1MB | Construction safety ← **primary benchmark** |
| `882Н_*.rtf` | `+СТРОИТЕЛЬСТВО 6/Input/` | ~300KB | Construction equipment safety |
| `872Н_*.rtf` | `+СТРОИТЕЛЬСТВО 6/Input/` | ~400KB | Construction equipment (telescoping lifts) |
| `66Н_ОБЩИЕ_ТРЕБОВАНИЯ_ОТ.rtf` | `Общие требования 6/` | ~800KB | General labor safety requirements |

### Upload procedure (via Telegram bot on VPS)

1. Start Telegram conversation with the bot on VPS (`agents.sintaris.net`)
2. Navigate: **KB → Upload files**
3. Send each RTF file directly as a Telegram document
4. Wait for "✅ Uploaded: \<filename\>" confirmation per file
5. Verify: **KB → My documents** should list all uploaded files with Cyrillic names

### Verify striprtf is installed in Docker container

```bash
docker exec taris-vps-telegram pip show striprtf
# Expected: Name: striprtf, Version: 0.0.26+
```

---

## 8. Improvement Roadmap

### P1 — Short-term (document-order sorting, easy wins)

| Improvement | File to change | Effort |
|---|---|---|
| Sort results by `chunk_idx` after vector search (preserve regulatory document flow) | `src/core/bot_mcp_client.py` `_kb_search_direct()` | 2h |
| Add `doc_num_filter` in `_kb_search_direct`: extract `XXX[НН]` pattern from query → SQL `WHERE metadata->>'doc_num' = ?` | `src/core/bot_mcp_client.py` | 4h |
| Increase `MCP_REMOTE_TOP_K` default from 5 to 8 for regulatory document profiles | `src/core/bot_config.py` | 30m |

### P2 — Medium-term (metadata enrichment)

| Improvement | File to change | Effort |
|---|---|---|
| Add `doc_num` to chunk `metadata` JSONB during ingest (regex from filename: `883Н`, `ГОСТ 12.0.001`) | `src/core/bot_mcp_client.py` `ingest_file()` | 3h |
| Add query type classification (5-class: definition / procedure / regulation / example / general) | `src/core/bot_mcp_client.py` or `bot_remote_kb.py` | 6h |
| Section-header weighting: chunks that ARE section headers get 0.2 score bonus | `src/core/bot_mcp_client.py` `_kb_search_direct()` | 2h |

### P3 — Long-term (embedding upgrade)

| Improvement | Impact | Effort |
|---|---|---|
| Switch to `text-embedding-3-small` (1536-dim) for OpenAI-tier quality | +15–25% precision on regulatory queries | Requires re-indexing all docs; DB schema change `vector(384)` → `vector(1536)` |
| Add `multilingual-e5-large` (1024-dim) for multilingual regulatory docs | Better DE/EN support | Same re-indexing effort, no API cost |

---

## 9. References

- Worksafety N8N bot source: `D:\Projects\workspace\Worksafety-superassistant\`
- Worksafety RAG test evaluator: `tests/rag_testing/test_rag.py`
- Worksafety benchmark queries: `tests/rag_testing/test_cases.csv`
- Taris KB architecture: `doc/architecture/knowledge-base.md`
- Taris KB tests: `src/tests/test_remote_kb.py` (T200–T241)
- Taris test strategy: `doc/test-strategy.md` §KB
