# RAG & Memory Architecture — Extended Research (April 2026)

**Companion to:** [`concept/rag-memory-architecture.md`](rag-memory-architecture.md)  
**Focus:** Additional memory concepts, vector DB comparison, document processing, server-side RAG, edge LLM training, reference architecture analysis  
**Status:** Research complete — findings integrated into architecture recommendations

---

## 1. Research Scope

This document extends the original concept paper (Variant C: Hybrid Tiered RAG, score 4.15/5.0) with targeted research on:

1. **Memory architecture concepts** beyond the original survey — MemGPT/Letta, Mem0, RAPTOR
2. **Vector database deep comparison** — LanceDB vs ChromaDB vs Qdrant vs hnswlib vs sqlite-vec
3. **Advanced document processing** — Docling (IBM) for multi-format local parsing
4. **Server-side RAG** — Google Grounding with Google Search API
5. **Edge LLM fine-tuning** — Karpathy nanochat for domain-specific models
6. **Autonomous research** — Karpathy AutoResearch for agent-driven architecture evaluation
7. **Reference architecture** — Worksafety-superassistant project (patterns to adopt/avoid)
8. **Impact assessment** on the recommended Variant C architecture

### Guiding Principle

> **Die Umsetzung soll nicht proprietär sein.**  
> All components must be open-source, vendor-neutral, and replaceable. No vendor lock-in on cloud APIs, embedding providers, or orchestration tools.

---

## 2. Memory Architecture Concepts

### 2.1 MemGPT / Letta — Virtual Context Management

| Property | Value |
|----------|-------|
| Repository | `cpacker/MemGPT` → renamed `letta-ai/letta` |
| Stars | 21.7K |
| License | Apache-2.0 |
| Version | v0.16.6 |
| Core Concept | OS-inspired hierarchical memory with virtual context management |

**Architecture:** MemGPT treats LLM context like a computer's memory hierarchy:

```
┌─────────────────────────┐
│  Main Context (fast)    │  ← LLM's working context window
│  - System prompt        │
│  - Recent messages      │
│  - Active memory blocks │
├─────────────────────────┤
│  Archival Memory (slow) │  ← External storage (DB, files)
│  - Conversation history │
│  - Documents            │
│  - Long-term facts      │
├─────────────────────────┤
│  Recall Memory          │  ← Searchable message history
│  - Full conversation log│
│  - Queryable by LLM     │
└─────────────────────────┘
```

**Key Mechanisms:**
- **Self-editing memory:** LLM can explicitly call `memory.edit()` to update its own context blocks
- **Interrupt-driven control:** When context overflows, system triggers a "heartbeat" that lets LLM decide what to page in/out
- **`memory_blocks` API**: Typed memory sections (persona, human, system) that persist across sessions
- **Model-agnostic**: Works with any LLM backend (OpenAI, local, Anthropic, etc.)

**Relevance for Taris:**

| Concept | Adopt? | Rationale |
|---------|--------|-----------|
| Virtual context with page-in/page-out | ✅ Partially | Our 3-tier memory (short→middle→long) is analogous, but simpler. MemGPT's approach is more dynamic (LLM decides what to load), ours is time-based. Consider adding query-relevant fact retrieval from long-term. |
| Self-editing memory blocks | ⚠️ Future | Powerful but requires LLM tool-use capability. Current `ask_llm()` pipe doesn't support tool calls. Wait for Phase D (MCP). |
| Interrupt mechanism | ❌ Too complex | Over-engineered for a single-user assistant. Our batch compaction is simpler and predictable. |
| Archival memory search | ✅ Yes | Aligns with our FTS5 search over `memory_summaries`. Enhance with semantic search when vectors are available. |

**Conclusion:** MemGPT validates our 3-tier memory design but suggests one enhancement: **query-relevant fact retrieval from long-term memory** (search long-term for facts related to current query before injecting into context). Add this to Phase A task A4.

---

### 2.2 Mem0 — Multi-Level Memory Platform

| Property | Value |
|----------|-------|
| Repository | `mem0ai/mem0` |
| Stars | 50.8K |
| License | Apache-2.0 |
| Version | v1.0.7 |
| Funding | Y Combinator S24 |
| Core Concept | Automatic multi-level memory extraction and retrieval |

**Architecture:**

```
User message → Mem0 API
  ├── Extract memories (LLM call)
  │     - key facts
  │     - preferences
  │     - relationships
  │     - temporal context
  ├── Update memory store
  │     - vector DB (Qdrant/ChromaDB)
  │     - graph store (Neo4j, optional)
  │     - telemetry
  └── Return relevant memories for context injection
```

**Three Memory Levels:**
1. **User Memory** — persists across all sessions: preferences, facts, history
2. **Session Memory** — current conversation context: active topics, recent decisions
3. **Agent Memory** — agent's own learned behaviors and instructions

**Benchmark Results (LOCOMO):**
- +26% accuracy vs OpenAI Memory
- 91% faster retrieval
- 90% fewer tokens consumed

**Key Features:**
- Self-hosted: `pip install mem0ai` + local vector DB
- Automatic memory extraction (no explicit `save()` calls needed)
- Graph memory (Neo4j) for relationship tracking
- REST API + Python SDK

**Relevance for Taris:**

| Concept | Adopt? | Rationale |
|---------|--------|-----------|
| 3-level memory (User/Session/Agent) | ✅ Maps perfectly | Our short-term ≈ Session, middle-term bridges, long-term ≈ User. Agent memory is new — consider for system prompt evolution. |
| Automatic memory extraction | ✅ Key insight | Instead of summarizing entire conversation batches, extract **specific facts/preferences** separately. Improves long-term memory quality. |
| Graph memory for relationships | ❌ Too heavy | Neo4j is multi-GB. Not viable on Pi. Graph relationships can be approximated with JSON `facts` field in `memory_long`. |
| Vector memory search | ✅ Already planned | Aligns with our hybrid search (FTS5 + vector). |
| Token efficiency | ✅ Validate | Mem0's 90% fewer tokens claim suggests aggressive fact extraction is better than full conversation summaries. |

**Proposed Enhancement for Variant C:**

Update compaction algorithm: instead of only summarizing, also **extract structured facts**:

```python
async def compact_short_to_middle(chat_id: int):
    # ... existing summary logic ...
    
    # NEW: Also extract structured facts
    facts = await ask_llm(
        f"From this conversation, extract key facts about the user as a JSON list:\n"
        f"- preferences (language, timezone, topics of interest)\n"
        f"- decisions made\n"
        f"- named entities mentioned (people, projects, dates)\n"
        f"- recurring patterns\n\n{messages_text}",
        timeout=30
    )
    store.save_memory_facts(chat_id, facts, source_ids=[...])
```

This gives us Mem0-style fact extraction without the dependency.

---

### 2.3 RAPTOR — Recursive Abstractive Processing for Tree-Organized Retrieval

| Property | Value |
|----------|-------|
| Paper | arXiv:2401.18059 (Stanford, January 2024) |
| Core Concept | Recursively cluster and summarize text into a tree for multi-level retrieval |
| Benchmark | +20% on QuALITY (long-document QA) with GPT-4 |

**Architecture:**

```
Level 3 (most abstract):    [Root summary]
                             /           \
Level 2 (cluster sums):  [Summary A]   [Summary B]
                          /    \          /    \
Level 1 (leaf clusters): [C1]  [C2]    [C3]  [C4]
                          ||    ||      ||    ||
Level 0 (raw chunks):   [chunks]     [chunks]
```

**Process:**
1. Chunk document into leaf nodes
2. Embed all chunks, cluster with UMAP + GMM
3. Summarize each cluster → new node (LLM call)
4. Recursively repeat: embed summaries → cluster → summarize
5. At query time: traverse tree top-down or retrieve from all levels

**Why It Matters:**
Standard chunking loses document-level context. A question about the "overall theme" of a 100-page document won't find answers in any single 512-char chunk. RAPTOR's tree structure preserves both detail (leaves) and abstraction (summaries).

**Relevance for Taris:**

| Aspect | Assessment |
|--------|-----------|
| Pi 3 viability | ❌ — Requires many LLM calls per document (1 per cluster per level). Too expensive for edge. |
| Pi 5 / Server viability | ⚠️ — Viable if using local LLM for summarization. Building the tree for a 50-page document might take 10–30 LLM calls. |
| Quality improvement | ✅ — Significant for long documents. Less impactful for short texts. |
| Integration path | Phase E (future) — After basic RAG is working, add tree indexing for documents > 20 pages. |

**Proposed adaptation for Variant C (future):**
- At document upload: if doc > 5000 chars, build 2-level RAPTOR tree (chunks → cluster summaries → doc summary)
- Store doc summary in `documents.doc_summary` (new column)
- At query time: first check doc summaries (fast, few entries), then search within matching docs' chunks
- This gives RAPTOR benefits without the full recursive tree cost

---

### 2.4 Memory Concept Comparison Matrix

| Concept | MemGPT/Letta | Mem0 | RAPTOR | Taris Variant C (current) | Taris Variant C (enhanced) |
|---------|:------------:|:----:|:------:|:-------------------------:|:--------------------------:|
| Time-based compaction | ❌ | ❌ | N/A | ✅ | ✅ |
| Query-relevant retrieval | ✅ | ✅ | ✅ | ⚠️ FTS5 only | ✅ FTS5 + vector |
| Fact extraction | Via tools | ✅ Automatic | N/A | ❌ | ✅ Add to compaction |
| Hierarchical abstraction | ❌ | ❌ | ✅ Tree | 3-tier flat | 3-tier + doc summaries |
| Self-editing memory | ✅ | ❌ | N/A | ❌ | Future (MCP tools) |
| Pi 3 compatible | ❌ | ❌ | ❌ | ✅ | ✅ |
| Pi 5 compatible | ⚠️ | ✅ (self-hosted) | ⚠️ | ✅ | ✅ |
| Vendor-neutral | ✅ Apache-2.0 | ✅ Apache-2.0 | ✅ (concept) | ✅ | ✅ |

**Key takeaways:**
1. **Fact extraction** (from Mem0) should be added to our compaction algorithm — improves long-term memory quality at minimal cost
2. **Document summaries** (from RAPTOR) should be generated at upload time — enables coarse-grained document selection before chunk search
3. **Query-relevant fact retrieval** (from MemGPT) should be added to context assembly — search long-term facts by relevance, not just inject last summary

---

## 3. Vector Database Deep Comparison

### 3.1 Candidate Analysis

#### sqlite-vec (Current baseline)

| Property | Value |
|----------|-------|
| Version | v0.1.6 |
| Type | SQLite extension |
| Search | Brute-force vector similarity (no index) |
| Dimensions | Any (FLOAT[N]) |
| Hybrid search | With FTS5 (separate query, manual fusion) |
| Size | ~2 MB wheel |
| Pi 3 viable | ✅ (if brute-force < 10K vectors is acceptable) |
| License | MIT |

**Strengths:** Zero additional dependencies — extends existing SQLite. Single-file DB. Perfectly matches DataStore adapter pattern.
**Weaknesses:** No ANN index (brute-force only). At 10K+ vectors, search latency grows linearly. No built-in hybrid search — requires manual RRF fusion with FTS5.

#### LanceDB — Embedded Hybrid Search

| Property | Value |
|----------|-------|
| Repository | `lancedb/lancedb` |
| Stars | 9.6K |
| License | Apache-2.0 |
| Version | v0.27.1 |
| Type | **Embedded** (serverless, like SQLite) |
| Search | Vector similarity + **full-text search** + SQL — all in one |
| Format | Lance columnar (Apache Arrow-based) |
| Dimensions | Any |
| Index | IVF_PQ, HNSW (disk-based) |
| Hybrid search | ✅ **Native** — single query combines vector + FTS + filter |
| Multimodal | ✅ |
| Size | ~50 MB (Python + Rust core) |
| Pi 3 viable | ⚠️ 50 MB install, but Rust binary needs ARM build |
| Pi 5 viable | ✅ |

**Key differentiator:** LanceDB is the **only embedded DB** that offers native hybrid search (vector + full-text + SQL) in a single query. This eliminates the need for separate FTS5 + sqlite-vec queries and manual RRF fusion.

```python
# LanceDB hybrid search example
import lancedb
db = lancedb.connect("~/.taris/lance_db")
table = db.open_table("doc_chunks")

# Single query: vector + FTS + filter
results = (table.search("climate change effects", query_type="hybrid")
    .limit(10)
    .where("owner_id = 12345 OR shared = 1")
    .to_list())
```

**Impact on Variant C:** If LanceDB has reliable ARM builds, it could **replace both sqlite-vec AND FTS5** for retrieval, significantly simplifying the architecture. The RRF fusion code becomes unnecessary.

#### ChromaDB — Popular Vector Store

| Property | Value |
|----------|-------|
| Repository | `chroma-core/chroma` |
| Stars | 26.8K |
| License | Apache-2.0 |
| Version | v1.5.5 |
| Type | Client/server OR embedded (in-process) |
| Search | Vector similarity (HNSW) |
| Hybrid search | ⚠️ Metadata filtering only — no full-text search |
| API | `add()`, `query()`, `update()`, `delete()` — 4 functions |
| Embedding | Built-in auto-embedding (or bring your own) |
| Size | ~100 MB (Python + dependencies) |
| Pi 3 viable | ❌ Too heavy (100 MB + HNSW memory) |
| Pi 5 viable | ✅ |

**Strengths:** Extremely simple API. Auto-handles tokenization and embedding. Popular community. Good documentation.
**Weaknesses:** No native full-text search — only vector + metadata filter. Heavier than needed for edge. In-memory HNSW index grows with collection size.

#### Qdrant — Production Vector Engine

| Property | Value |
|----------|-------|
| Repository | `qdrant/qdrant` |
| Stars | 29.8K |
| License | Apache-2.0 |
| Version | v1.17.0 |
| Language | Rust |
| Type | Client/server (binary) OR in-memory Python |
| Search | Vector + **sparse vectors** (BM25 generalization) |
| Hybrid search | ✅ **Native** via sparse + dense vector fusion |
| Index | HNSW + quantization (97% RAM reduction) |
| API | REST + gRPC (+Python client) |
| Size | ~200 MB (server binary) |
| Pi 3 viable | ❌ Too heavy |
| Pi 5 viable | ⚠️ Server binary, ~200 MB RAM minimum |

**Strengths:** Most feature-rich. Sparse vectors enable BM25-equivalent search in the same engine. Production-proven at scale. Vector quantization dramatically reduces memory.
**Weaknesses:** Heavy server binary. Overkill for edge deployment with < 100K vectors. Rust dependency.

**Sparse vector hybrid search (unique to Qdrant):**
```python
from qdrant_client import QdrantClient, models

client = QdrantClient(path="path/to/db")  # local, no server needed

# Hybrid: dense + sparse in single query
results = client.query_points(
    collection_name="doc_chunks",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=20),
        models.Prefetch(query=sparse_vector, using="sparse", limit=20),  # BM25-equivalent
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),  # Built-in RRF!
    limit=10,
)
```

#### hnswlib — Ultra-Lightweight HNSW

| Property | Value |
|----------|-------|
| Repository | `nmslib/hnswlib` |
| Stars | 5.1K |
| License | Apache-2.0 |
| Version | v0.8.0 (last update: 2024) |
| Language | C++ header-only + Python bindings |
| Type | In-process library (not a database) |
| Search | Approximate Nearest Neighbor (HNSW algorithm) |
| Hybrid search | ❌ — vector only, no text search |
| Index | HNSW (in-memory, serializable to disk) |
| Size | ~5 MB |
| Pi 3 viable | ✅ **Most lightweight option** |
| Pi 5 viable | ✅ |

**Strengths:** Minimal footprint. Pure vector search with excellent speed. C++ header-only means easy ARM compilation. Used by 8.4K+ projects.
**Weaknesses:** Not a database — no persistence management, no filtering, no text search. Must be paired with SQLite FTS5. Last updated 2024 (stable but not actively developed).

**Pairing with SQLite FTS5:**
```python
import hnswlib
import sqlite3

# Vector search with hnswlib
index = hnswlib.Index(space='cosine', dim=384)
index.load_index("~/.taris/hnsw_index.bin")
labels, distances = index.knn_query(query_vector, k=10)

# FTS5 search with SQLite
conn = sqlite3.connect("~/.taris/taris.db")
fts_results = conn.execute(
    "SELECT doc_id, rank FROM doc_chunks_fts WHERE doc_chunks_fts MATCH ?",
    (query_text,)
).fetchall()

# Manual RRF fusion
combined = reciprocal_rank_fusion(fts_results, zip(labels[0], distances[0]))
```

---

### 3.2 Comparative Decision Matrix

| Criterion (weight) | sqlite-vec | LanceDB | ChromaDB | Qdrant | hnswlib + FTS5 |
|--------------------|:----------:|:-------:|:--------:|:------:|:--------------:|
| **Pi 3 viable** (20%) | ✅ 5 | ⚠️ 2 | ❌ 1 | ❌ 1 | ✅ 5 |
| **Pi 5 viable** (15%) | ✅ 5 | ✅ 5 | ✅ 4 | ⚠️ 3 | ✅ 5 |
| **Hybrid search** (20%) | ⚠️ 2 | ✅ 5 | ❌ 1 | ✅ 5 | ⚠️ 3 |
| **Simplicity** (15%) | ✅ 5 | ✅ 4 | ✅ 5 | ⚠️ 2 | ⚠️ 3 |
| **Footprint** (15%) | ✅ 5 | ⚠️ 3 | ❌ 1 | ❌ 1 | ✅ 5 |
| **Ecosystem** (10%) | ⚠️ 2 | ✅ 4 | ✅ 5 | ✅ 5 | ⚠️ 2 |
| **ARM aarch64** (5%) | ✅ 5 | ⚠️ 3 | ✅ 4 | ⚠️ 3 | ✅ 5 |
| **Weighted Score** | **3.90** | **3.65** | **2.65** | **2.65** | **4.00** |

### 3.3 Recommendation: Tiered Vector Strategy

**PicoClaw (Pi 3, 1 GB):** `hnswlib + SQLite FTS5` — best combined score (4.00). Ultra-lightweight vector ANN + proven FTS5. Manual RRF fusion needed but already coded in Variant C.

**OpenClaw (Pi 5, 4-8 GB):** `LanceDB` — native hybrid search eliminates manual RRF. Embedded (no server). 50 MB footprint acceptable on 4+ GB RAM. *Alternative:* keep `hnswlib + FTS5` for consistency.

**Server (16+ GB):** `Qdrant` (in-process mode) or `LanceDB` — both offer native hybrid search. Qdrant's sparse vectors + quantization excel at scale. *Alternative:* PostgreSQL + pgvector (already in DataStore adapter plan).

**Updated DataStore adapter:**

```python
# store_base.py — extend Protocol
class DataStore(Protocol):
    def search_hybrid(self, query_text: str, query_vector: list[float] | None,
                      chat_id: int, top_k: int = 5) -> list[dict]:
        """Hybrid search: combines FTS + vector when available."""
        ...
    
    def upsert_vector(self, doc_id: str, chunk_idx: int, 
                      vector: list[float], text: str) -> None:
        """Store embedding vector for a text chunk."""
        ...

# Implementations:
# store_sqlite.py  → FTS5 + hnswlib (load index on demand)
# store_lance.py   → LanceDB native hybrid (new adapter)
# store_postgres.py → pgvector + tsvector
# store_qdrant.py  → Qdrant sparse+dense (new adapter, server tier)
```

**Impact on Variant C:** The core architecture stays almost identical. The DataStore adapter pattern already isolates the vector backend. Adding `hnswlib` for Pi 3 and `LanceDB` for Pi 5 are implementation details within `store_sqlite.py` and a new `store_lance.py`.

---

## 4. Document Processing — Docling (IBM)

### 4.1 Overview

| Property | Value |
|----------|-------|
| Repository | `docling-project/docling` |
| Stars | 56.3K |
| License | MIT |
| Foundation | LF AI & Data Foundation |
| Version | v2.81.0 |
| Core | Advanced multi-format document parsing with layout understanding |

### 4.2 Format Support

| Format | Parser | Notes |
|--------|--------|-------|
| PDF | DoclingParser (layout-aware) | Preserves reading order, tables, formulas, code blocks |
| DOCX | python-docx backend | Structure-aware (headings, lists, tables) |
| PPTX | python-pptx backend | Slide-by-slide with notes |
| XLSX | openpyxl backend | Sheet extraction with headers |
| HTML | BeautifulSoup backend | Semantic content extraction |
| Images | OCR (RapidOCR, SuryaOCR, Tesseract) | Text extraction from images |
| Audio (WAV, MP3) | Whisper ASR | Transcription with timestamps |
| LaTeX | Direct parsing | Math formula extraction |
| Markdown | Direct parsing | Structure preservation |

### 4.3 Key Capabilities

**Layout understanding:** Docling's PDF parser (DoclingParser) goes beyond text extraction. It understands:
- Reading order (multi-column layouts)
- Table structure (rows, columns, merged cells)
- Figures and captions
- Code blocks
- Mathematical formulas (LaTeX)
- Section hierarchy (headings → subheadings → paragraphs)

**VLM integration:** GraniteDocling 258M — a 258M-parameter vision-language model specifically trained for document understanding. Runs locally, no API needed.

**Hybrid chunking:** Structure-aware chunking that respects document boundaries (don't split a table, keep a heading with its paragraph).

**MCP server:** Docling provides an MCP server for integration with LLM tools — aligns with our Phase D (MCP) plan.

### 4.4 Comparison with Current Stack

| Capability | Current (pdfminer.six + python-docx) | Docling |
|-----------|--------------------------------------|---------|
| PDF text extraction | ✅ Basic | ✅ Layout-aware |
| PDF table extraction | ❌ | ✅ Structure-preserving |
| PDF image extraction | ❌ (planned: PyMuPDF) | ✅ OCR + VLM |
| DOCX | ✅ Basic | ✅ Structure-aware |
| PPTX / XLSX / HTML | ❌ | ✅ |
| Audio transcription | Via our Vosk/Whisper | ✅ Via Whisper |
| Chunking strategy | Manual fixed-size | ✅ Hybrid (respects structure) |
| Install size | ~10 MB | ~200 MB+ (with VLM) |
| Pi 3 viable | ✅ | ❌ (VLM too heavy) |
| Pi 5 viable | ✅ | ⚠️ (without VLM: ✅) |

### 4.5 Recommendation

**Phase B Enhancement:** Replace `pdfminer.six` + `python-docx` with Docling as the document parser:
- Use Docling's structure-aware chunking (eliminates our manual chunker)
- On Pi 3: use Docling without VLM (text extraction only, ~50 MB)
- On Pi 5+: enable VLM for OCR and complex PDF layout understanding
- Docling's MCP server aligns with Phase D — can expose document parsing as a tool

**Proposed config:**
```bash
# bot.env
DOC_PARSER=docling          # docling | legacy (pdfminer+python-docx)
DOC_PARSER_VLM=0            # 1=enable GraniteDocling VLM (Pi 5+ only)
DOC_PARSER_OCR=rapidocr     # rapidocr | surya | tesseract | off
```

**Structure-aware chunking example (from Worksafety patterns):**

```python
# Docling provides document structure; we use it for intelligent chunking
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("document.pdf")

# Docling returns structured content with hierarchy
for section in result.document.sections:
    # Each section has: title, level, paragraphs, tables, figures
    chunk_text = f"## {section.title}\n\n"
    for paragraph in section.paragraphs:
        chunk_text += paragraph.text + "\n"
    
    # Chunk respects section boundaries
    # Tables are serialized as markdown
    for table in section.tables:
        chunk_text += table.to_markdown() + "\n"
    
    yield ChunkResult(
        text=chunk_text,
        metadata={
            "section": section.title,
            "level": section.level,
            "page": section.start_page,
        }
    )
```

---

## 5. Server-Side RAG — Google Grounding with Google Search

### 5.1 Overview

Google provides **Grounding with Google Search** as part of the Gemini API. It's not a traditional RAG system — instead, it augments LLM responses with real-time web search results.

**How it works:**

```
User query → Gemini API
  ├── Model generates search queries automatically
  ├── Google Search executes queries
  ├── Search results injected into LLM context
  └── Response includes:
       - Answer text with inline citations
       - groundingMetadata:
         - webSearchQueries (what was searched)
         - groundingChunks (source URIs + titles)
         - groundingSupports (which claims map to which sources)
```

### 5.2 API Integration

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="GEMINI_API_KEY")

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="What are the latest advances in edge AI?",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    ),
)

# Access grounding metadata
metadata = response.candidates[0].grounding_metadata
print(metadata.search_entry_point)  # Rendered search widget
for chunk in metadata.grounding_chunks:
    print(f"Source: {chunk.web.title} — {chunk.web.uri}")
```

### 5.3 Relevance for Taris

| Aspect | Assessment |
|--------|-----------|
| Offline use | ❌ Requires internet + Gemini API |
| Cost | Per-query billing (free tier available for Gemini Flash) |
| Quality | ✅ Excellent — real-time web information with source verification |
| Privacy | ⚠️ Queries sent to Google |
| Integration | Via existing `_ask_gemini()` in `bot_llm.py` — add `google_search` tool |
| Vendor lock-in | ⚠️ Gemini-specific API |

**Recommendation:** Add as an **optional mode**, not a primary RAG path:

```python
# bot_llm.py — extend _ask_gemini() with grounding option
def _ask_gemini_grounded(prompt: str, timeout: int = 60) -> str:
    """Gemini with Google Search grounding — for factual/current queries."""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    # Format response with source citations
    text = response.text
    if response.candidates[0].grounding_metadata:
        sources = response.candidates[0].grounding_metadata.grounding_chunks
        if sources:
            text += "\n\n📎 Sources:\n"
            for s in sources[:5]:
                text += f"• [{s.web.title}]({s.web.uri})\n"
    return text
```

**User-facing toggle:**
- Admin panel: Enable/disable "Web Search" mode
- User can activate via: `/search <query>` or a "🌐 Search" button
- Clearly labeled as cloud feature (privacy notice)

---

## 6. Edge LLM Fine-Tuning — Karpathy nanochat

### 6.1 Overview

| Property | Value |
|----------|-------|
| Repository (predecessor) | `karpathy/nanoGPT` — 55.4K stars, **DEPRECATED Nov 2025** |
| Repository (successor) | `karpathy/nanochat` — 50K stars |
| License | MIT |
| Core | Complete LLM training harness: tokenization → pretraining → finetuning (SFT + RL) → evaluation → inference → chat UI |

**nanochat** is Andrej Karpathy's production successor to nanoGPT. It's a complete, minimal LLM training framework designed for reproducibility and education.

### 6.2 Capabilities

```
nanochat pipeline:
  1. Tokenization   — train custom tokenizer on domain corpus
  2. Pretraining    — GPT-2 architecture, any size
  3. SFT            — supervised fine-tuning on instruction pairs
  4. RL (RLHF)      — reinforcement learning from human feedback
  5. Evaluation     — benchmark suite
  6. Inference      — optimized serving
  7. Chat UI        — interactive chat interface
```

**Key feature: `--depth` dial** — single parameter controls training intensity:
- `depth=1`: Quick prototype (~minutes on GPU)
- `depth=10`: Full training run (~hours on 8×H100)

### 6.3 Relevance for Taris

| Use Case | Viability |
|----------|-----------|
| Fine-tune domain-specific model for edge | ⚠️ Training requires GPU (not on Pi). Can be run on laptop/server, then deploy quantized model to Pi 5. |
| Train custom Russian language model | ⚠️ Possible but needs significant Russian corpus. Qwen2 already exists and is multilingual. |
| Fine-tune for Taris-specific responses | ✅ Collect user interactions → SFT on conversation pairs → quantize → deploy to Pi 5 via llama.cpp |
| Replace OpenRouter for specific tasks | ✅ A fine-tuned 0.5-3B model could handle calendar commands, note operations, system commands locally without cloud |

**Proposed workflow (OpenClaw laptop deployment):**

```
1. Collect training data:
   rag_log + chat_history → extract (prompt, response) pairs
   Filter for high-quality interactions (admin-approved)

2. Fine-tune on laptop with nanochat:
   nanochat train --data taris_sft_pairs.jsonl \
                  --model gpt2-small \
                  --depth 5

3. Convert to GGUF:
   llama.cpp/convert.py → quantize Q4_K_M

4. Deploy to Pi 5:
   Copy .gguf to /mnt/ssd/models/
   Update taris-llm.service model path

5. Use as specialized local fallback:
   Intent classification, calendar parsing, system command generation
   — these are repetitive tasks where a small fine-tuned model excels
```

**Evaluation:** nanochat is a medium-term project (requires setting up training infrastructure on the OpenClaw laptop). Most immediately relevant for training intent classifiers and calendar NL parsers that currently use expensive cloud LLM calls.

---

## 6b. Autonomous Research — Karpathy AutoResearch

### 6b.1 Overview

| Property | Value |
|----------|-------|
| Repository | `karpathy/autoresearch` — 51.1K ⭐, 7.1K forks |
| License | MIT |
| Language | Python 83.5% |
| Core concept | AI agents iteratively run experiments to optimize a single metric, autonomously |
| GPU requirement | Single NVIDIA GPU (community forks for macOS, Windows, AMD) |

**AutoResearch** is Karpathy's framework for autonomous AI-driven experimentation. An AI agent (Claude) reads a research agenda (`program.md`), modifies a training file (`train.py`), runs a 5-minute experiment, evaluates the result against a metric (`val_bpb`), and decides whether to keep or discard the change — all fully automatically.

### 6b.2 Architecture — 3-File Paradigm

```
autoresearch/
  prepare.py    ← FIXED: data preparation + utility functions (never modified by agent)
  train.py      ← AGENT-MODIFIED: the file the AI agent experiments with
  program.md    ← HUMAN-WRITTEN: research agenda + evaluation rules for the agent
```

**Workflow loop:**
```
1. Agent reads program.md (research agenda)
2. Agent reads current train.py
3. Agent proposes a modification to train.py
4. Modified train.py runs (5-minute wall-clock budget)
5. Metric evaluated (val_bpb — validation bits per byte)
6. If improved → keep change. If not → revert.
7. Repeat (~12 experiments/hour, ~100 overnight)
```

**Key design choices:**
- **Single file scope:** Agent only modifies `train.py` — simplicity prevents cascade failures
- **Fixed time budget:** Every experiment takes exactly 5 minutes — predictable resource usage
- **Self-contained:** No external dependencies beyond GPU, model weights, and dataset
- **Metric-driven:** `val_bpb` is vocabulary-size-independent, enabling fair cross-model comparison

### 6b.3 Adaptation for Taris RAG Evaluation

AutoResearch's original target is LLM **training** optimization. For Taris, the **paradigm** is transferable to RAG pipeline architecture evaluation across hardware tiers:

| AutoResearch Original | Taris RAG Adaptation |
|----------------------|---------------------|
| `program.md` → LLM training research agenda | `program.md` → RAG architecture evaluation agenda |
| `train.py` → model training script | `evaluate.py` → RAG pipeline configuration + benchmark |
| `prepare.py` → tokenizer + dataset prep | `prepare.py` → test corpus + ground truth preparation |
| `val_bpb` metric | Composite metric: precision, recall, F1, latency, memory, cost |
| 5-min training budget | 5-min evaluation budget per configuration |
| Single NVIDIA GPU | Target-specific: Pi 3, Pi 5, AI X1, VPS |

**Adapted research loop:**
```
1. Agent reads program.md (RAG evaluation agenda)
2. Agent reads current evaluate.py (RAG pipeline config)
3. Agent proposes a configuration change:
   - Chunk size (256 / 512 / 1024 chars)
   - Retrieval method (FTS5 only / vector only / hybrid)
   - Embedding model (MiniLM-L6-v2 / all-MiniLM-L12 / none)
   - Reranking strategy (none / LLM-as-judge / cross-encoder)
   - Top-k value (3 / 5 / 10)
   - Memory tier (short-only / short+middle / full 3-tier)
4. evaluate.py runs against test corpus (5-min budget)
5. Composite metric calculated:
   rag_score = 0.35×precision + 0.25×recall + 0.20×(1/latency_norm) + 0.10×(1/memory_norm) + 0.10×(1/cost_norm)
6. If rag_score improved → keep. If not → revert.
7. Repeat (~12 configs/hour)
```

### 6b.4 Per-Architecture AutoResearch Configuration

AutoResearch requires adaptation for each hardware tier. The README explicitly provides smaller-platform tuning knobs:

#### Raspberry Pi (PicoClaw / OpenClaw Pi 5)

AutoResearch cannot run *on* a Pi (no NVIDIA GPU for training), but evaluation experiments can target the Pi remotely:

```
program.md for Pi evaluation:
  - Target: Pi 3 (1 GB RAM) or Pi 5 (8 GB RAM)
  - Constraints: max 500 MB RAM for RAG, max 5s latency
  - evaluate.py SSH → Pi → run benchmark → collect metrics
  - Metric: rag_score with heavy latency/memory weighting

evaluate.py execution:
  1. SSH to target Pi
  2. Apply RAG configuration (chunk size, retrieval method, top-k)
  3. Run 20 test queries from ground truth
  4. Measure: precision, recall, latency_p95, peak_ram_mb
  5. Report composite rag_score back to agent
```

#### AI X1 (OpenClaw with GPU)

If the AI X1 has an NVIDIA GPU, AutoResearch runs natively for both LLM training (nanochat) AND RAG evaluation:

```
program.md for AI X1:
  - Full autoresearch capabilities (training + evaluation)
  - Can evaluate local LLM quality as part of RAG pipeline
  - Larger parameter space: embedding models up to 768-dim, 7B local LLM
  - Metric: rag_score with balanced weighting (quality > latency)
```

#### VPS (Server deployment)

Full AutoResearch with maximum parameter space:

```
program.md for VPS:
  - Full compute budget, no memory constraints
  - Evaluate pgvector vs Qdrant vs LanceDB
  - Evaluate GPT-4o vs Claude vs Gemini as RAG generator
  - Evaluate full RAPTOR tree vs flat chunks
  - Metric: rag_score with heavy quality weighting (cost acceptable)
```

### 6b.5 Smaller Platform Adaptations (from AutoResearch README)

For running AutoResearch itself (the agent loop) on resource-constrained hardware:

| Knob | Default | Smaller Value | Effect |
|------|---------|---------------|--------|
| Dataset | FineWeb-Edu 10B | TinyStories | 10× smaller, faster iteration |
| `vocab_size` | 32768 | 256 (byte-level) | Much smaller embedding layer |
| `MAX_SEQ_LEN` | 1024 | 256 | 4× less memory per sample |
| `DEPTH` | 8 (layers) | 4 | 2× faster training |
| `WINDOW_PATTERN` | `"LSL"` | `"L"` (local only) | No sliding window overhead |
| `TOTAL_BATCH_SIZE` | 2^18 | 2^14 | 16× less memory |
| Experiment budget | 5 min | 3 min | More experiments per hour |

These knobs are applicable when running AutoResearch on the AI X1 for nanochat training experiments (§6 above).

### 6b.6 Notable Community Forks

| Fork | Platform | Maintainer |
|------|----------|------------|
| macOS (Apple Silicon) | MPS backend | @miolini, @trevin-creator |
| Windows | CUDA on Windows | @jsegov |
| AMD | ROCm | @andyluo7 |

### 6b.7 Integration with Taris Evaluation Pipeline

**Proposed directory structure on OpenClaw:**

```
~/.taris/autoresearch/
  program.md              ← Research agenda (per-architecture variant)
  prepare.py              ← Test corpus preparation + ground truth
  evaluate.py             ← RAG pipeline configuration (agent-modified)
  results/
    pi3/                  ← Results for Pi 3 target
    pi5/                  ← Results for Pi 5 target
    x1/                   ← Results for AI X1 target
    vps/                  ← Results for VPS target
  baselines/
    variant_c_default.json ← Baseline metrics for current Variant C implementation
```

**Evaluation flow:**
```
OpenClaw (with GPU, runs AutoResearch agent)
    │
    ├── SSH → Pi 3 (OpenClawPI): evaluate RAG on 1 GB RAM
    │     └── rag_score for Pi 3 config → results/pi3/
    │
    ├── SSH → Pi 5 (OpenClawPI2): evaluate RAG on 8 GB RAM
    │     └── rag_score for Pi 5 config → results/pi5/
    │
    ├── Local: evaluate RAG on AI X1
    │     └── rag_score for X1 config → results/x1/
    │
    └── SSH → VPS: evaluate RAG on server
          └── rag_score for VPS config → results/vps/
```

**Cross-architecture comparison:** After N experiments per target, the agent produces a Pareto frontier of configurations per platform — showing the optimal tradeoff between quality, latency, memory, and cost for each hardware tier.

**Evaluation:** AutoResearch provides the missing **automated experimentation methodology** for the §23 research agenda. Instead of manually testing RAG configurations, an AI agent systematically explores the configuration space overnight. The 3-file paradigm (`program.md` / `evaluate.py` / `prepare.py`) maps cleanly onto the RAG evaluation use case. Main effort: writing the initial `program.md` per architecture and implementing `evaluate.py` with SSH-based remote benchmarking.

---

## 7. Reference Architecture — Worksafety-superassistant

### 7.1 Project Overview

The Worksafety-superassistant is a production RAG system with:
- **~100K text chunks** from ~200 documents
- **PostgreSQL 15 + pgvector** (IVFFLAT index)
- **OpenAI text-embedding-3-small** (1536-dim)
- **GPT-4o-mini** for response generation
- **n8n 1.113.3** workflow orchestration (11 workflows)
- **Docker** containerized deployment
- **31 database tables**
- **Telegram bot** interface

### 7.2 Patterns to Adopt

| Pattern | Description | How to Adopt in Taris |
|---------|-------------|----------------------|
| **Structure-aware chunking** | Documents chunked by chapter/section, not fixed-size. Preserves document hierarchy. | Use Docling's structure output. Store `section_title`, `chapter`, `page_num` in chunk metadata. |
| **Chapter-level context assembly** | When chunks are retrieved, also include the parent chapter summary for context. | Add `doc_summary` column to `documents` table. Include in context when relevant chunks are found. |
| **3-signal hybrid scoring** | `combined = (vector × 0.50) + structure_bonus + lda_bonus + chapter_match_bonus` | Extend our RRF: add document-structure signal alongside FTS5 + vector scores. |
| **Query caching (SHA256)** | Hash queries → cache responses. Highly effective for repeated questions in domain-specific corpus. | Add `rag_cache` table: `query_hash TEXT PK, response TEXT, created_at, ttl`. Check before LLM call. |
| **LDA topic modeling** | scikit-learn LDA extracts topics per chunk. Used as additional ranking signal. | Lightweight alternative to embeddings on Pi 3. `sklearn.decomposition.LatentDirichletAllocation` — ~10 MB, fast inference. |
| **Multi-format document support** | PDF, DOCX, HTML, CSV, XLSX, TXT | Align with Docling format support. Already partially implemented. |
| **Activation code access control** | Users receive activation codes to access specific document sets. | Map to our `doc_sharing` table — share documents via codes or user IDs. |
| **Metadata filtering** | Chapter regex matching for domain-specific queries | Add `metadata JSONB` column to chunks. Filter by metadata before vector search. |

### 7.3 Patterns to Avoid (Proprietary Aspects)

| Anti-Pattern | Why to Avoid | Taris Alternative |
|-------------|-------------|-------------------|
| **OpenAI-only embeddings** | Vendor lock, no offline, 1536-dim too large for Pi 3 | MiniLM-L6-v2 ONNX (384-dim, local, 22 MB) |
| **n8n workflow orchestration** | Heavy dependency (1+ GB), separate service, JSON-based "code" | Python-native pipeline in `bot_retrieval.py` — no orchestrator needed |
| **Telegram-only UI** | No web interface | Already have both Telegram + Web UI via Screen DSL |
| **Docker-only deployment** | Pi 3 can't run Docker efficiently (cgroup overhead on 1 GB RAM) | Native systemd services (already implemented) |
| **Cloud-only LLM** | No offline capability, API cost, latency | Multi-provider dispatch + local llama.cpp fallback (already implemented) |
| **Fixed embedding provider** | Can't swap models | Pluggable `EmbeddingService` class with model config |
| **No memory compaction** | Conversation context not summarized or tiered | 3-tier memory system (Variant C) |

### 7.4 Scoring System Adaptation

Worksafety uses a weighted multi-signal score:

```
combined_score = (vector_similarity × 0.50)
               + structure_bonus(0.05–0.30)      # section/chapter match
               + lda_bonus(+0.10)                 # topic relevance
               + chapter_match_bonus(+0.50)        # exact chapter regex
```

**Adapted for Taris (5-signal hybrid):**

```python
def compute_chunk_score(chunk: dict, query: str, query_vector: list[float] | None) -> float:
    """Multi-signal scoring adapted from Worksafety patterns."""
    score = 0.0
    
    # Signal 1: FTS5 BM25 (always available)
    if chunk.get("fts_rank"):
        score += normalize_bm25(chunk["fts_rank"]) * 0.30
    
    # Signal 2: Vector similarity (when available)
    if query_vector and chunk.get("vector_score"):
        score += chunk["vector_score"] * 0.35
    elif not query_vector:
        # No vectors: increase FTS weight
        score += normalize_bm25(chunk["fts_rank"]) * 0.15  # +15% to FTS
    
    # Signal 3: Section match bonus (from Worksafety)
    if chunk.get("section_title") and query_terms_in(query, chunk["section_title"]):
        score += 0.15
    
    # Signal 4: Recency bonus (newer documents rank higher for ambiguous queries)
    age_days = (now() - chunk["created_at"]).days
    score += max(0, 0.10 - age_days * 0.001)  # Max 0.10, decays over 100 days
    
    # Signal 5: User document priority (user's own docs rank higher than shared)
    if chunk.get("owner_id") == current_user_id:
        score += 0.10
    
    return score
```

---

## 8. Impact on Architecture Variants

### 8.1 Variant C Enhancement Summary

The extended research confirms Variant C as the correct choice and suggests these enhancements:

| Enhancement | Source | Phase | Effort |
|-------------|--------|-------|--------|
| Fact extraction in memory compaction | Mem0 | A (memory) | +0.5d |
| Query-relevant fact retrieval from long-term | MemGPT | A (memory) | +0.5d |
| Document-level summaries at upload | RAPTOR | B (RAG) | +0.5d |
| hnswlib for vector search on Pi 3 | hnswlib research | B (RAG) | +1d (replaces sqlite-vec in retrieval) |
| LanceDB option for Pi 5+ | LanceDB research | B (RAG) | +1d (new adapter) |
| Docling document parser | Docling research | B (RAG) | +1d (replaces pdfminer) |
| Query caching (SHA256) | Worksafety | B (RAG) | +0.5d |
| Multi-signal scoring | Worksafety | B (RAG) | +0.5d (extend RRF) |
| Google Search grounding mode | Google API | D (remote) | +0.5d |
| nanochat fine-tuning pipeline | Karpathy | E+ (future) | +3d (laptop setup) |
| AutoResearch evaluation framework | Karpathy | B–D (evaluation) | +2d (program.md + evaluate.py per target) |

### 8.2 Updated Variant C Score

| Criterion (weight) | Original 4.15 | Enhanced |
|--------------------|:-------------:|:--------:|
| Pi 3 compatibility (20%) | 5 | 5 (hnswlib confirmed) |
| Quality (25%) | 4 | **4.5** (fact extraction + multi-signal + doc summaries) |
| Offline capability (15%) | 5 | 5 |
| Scalability (15%) | 3 | **3.5** (LanceDB path for Pi 5, Qdrant path for server) |
| Simplicity (15%) | 4 | 4 (same adapter pattern) |
| Future-proofing (10%) | 4 | **4.5** (nanochat pipeline, AutoResearch eval, MCP, Google Search) |
| **Weighted Score** | **4.15** | **4.45** |

### 8.3 Updated System Architecture

```
User query
    │
    ▼
┌──────────────────────────────────────────────────────┐
│               Adaptive Query Router                   │
│  simple → direct LLM  │  factual → RAG  │  web → Google │
└───────────┬──────────────────┬────────────────┬──────┘
            │                  │                │
     ┌──────┘                  │                │
     │                         ▼                ▼
     │         ┌─────────────────────┐   Google Search
     │         │   Hybrid Retrieval   │   Grounding
     │         │  ┌───────────────┐  │   (optional)
     │         │  │    FTS5       │  │
     │         │  │  (always on)  │  │
     │         │  └───────┬───────┘  │
     │         │          │          │
     │         │  ┌───────┴───────┐  │
     │         │  │  Vector ANN   │  │
     │         │  │  (if capable) │  │
     │         │  │ hnswlib/Lance │  │
     │         │  └───────┬───────┘  │
     │         │          │          │
     │         │  ┌───────┴───────┐  │
     │         │  │ Multi-Signal  │  │
     │         │  │   Scoring     │  │
     │         │  │ (5 signals)   │  │
     │         │  └───────┬───────┘  │
     │         │          │          │
     │         │  ┌───────┴───────┐  │
     │         │  │ Query Cache   │  │
     │         │  │ (SHA256 hash) │  │
     │         │  └───────────────┘  │
     │         └──────────┬──────────┘
     │                    │
     ▼                    ▼
┌──────────────────────────────────────────────────────┐
│              Context Assembly (ordered)                │
│  1. System prompt + SECURITY_PREAMBLE                 │
│  2. Long-term facts (query-relevant, from MemGPT)     │
│  3. Middle-term summaries (recent, relevant)           │
│  4. RAG chunks (top-k from hybrid retrieval)           │
│  5. Conversation history (short-term window)           │
│  6. User query                                         │
└───────────────────────────┬──────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   ask_llm()   │
                    │  (6 providers │
                    │  + fallback)  │
                    └───────────────┘
```

---

## 9. Updated Recommendations

### 9.1 Immediate (Phase A — Memory, updated)

1. Add **fact extraction** to compaction algorithm (Mem0 pattern)
2. Add **query-relevant fact retrieval** from long-term memory (MemGPT pattern)
3. Store extracted facts as structured JSON, searchable via FTS5

### 9.2 Near-term (Phase B — Enhanced RAG, updated)

1. Replace `sqlite-vec` brute-force with **hnswlib** for Pi 3 vector search (5× faster at 10K+ chunks)
2. Add **LanceDB adapter** as Pi 5+ alternative (native hybrid search, no RRF needed)
3. Replace `pdfminer.six` with **Docling** parser (structure-aware chunking, multi-format)
4. Add **query cache** (SHA256 hash → response, from Worksafety patterns)
5. Implement **5-signal scoring** (FTS5 + vector + section match + recency + ownership)
6. Generate **document summaries** at upload (RAPTOR-lite: single-level, not full tree)

### 9.3 Medium-term (Phase D — Remote RAG, updated)

1. Add **Google Search grounding** as optional mode via Gemini API
2. Expose local knowledge as **MCP tools** (aligns with Docling MCP server capability)

### 9.4 Long-term (Future phases)

1. Set up **AutoResearch evaluation framework** on OpenClaw (GPU): write `program.md` per architecture (Pi 3, Pi 5, AI X1, VPS), implement `evaluate.py` with SSH-based remote benchmarking
2. Run **automated RAG architecture experiments** overnight: ~100 configurations per target, agent-driven optimization of chunk size, retrieval method, embedding model, reranking, top-k
3. Set up **nanochat training pipeline** on OpenClaw laptop
4. Fine-tune domain-specific models for: calendar NL parsing, intent classification, system command generation
5. Deploy quantized fine-tuned models to Pi 5 via llama.cpp
6. Use **AutoResearch for nanochat training optimization**: `program.md` → training agenda, `train.py` → model config, `val_bpb` metric, automated hyperparameter search
7. Evaluate **LDA topic modeling** from Worksafety as lightweight alternative to embeddings on Pi 3

### 9.5 Technology Selection Summary

| Component | PicoClaw (Pi 3) | OpenClaw (Pi 5) | Server | Laptop / AI X1 (Training + Eval) |
|-----------|:--------------:|:---------------:|:------:|:-------------------------------:|
| FTS5 | ✅ Primary | ✅ Baseline | ✅ Baseline | ✅ |
| Vector search | hnswlib (5 MB) | LanceDB (50 MB) | Qdrant / pgvector | LanceDB |
| Embeddings | MiniLM-L6-v2 ONNX | MiniLM-L6-v2 ONNX | MiniLM or larger | OpenAI / local |
| Doc parser | Docling (no VLM) | Docling (+ VLM) | Docling (full) | Docling (full) |
| Memory | 3-tier + facts | 3-tier + facts | 3-tier + facts | N/A |
| LLM | Cloud + local fallback | Cloud + local 3B | Cloud + local 7B | nanochat training |
| Google Search | Via cloud LLM | ✅ Gemini API | ✅ Gemini API | Dev/test |
| AutoResearch | Target (via SSH) | Target (via SSH) | Target (via SSH) | ✅ Agent host |

---

## Appendix: Research Sources

| Source | URL / Reference | Key Insight |
|--------|----------------|-------------|
| MemGPT/Letta | `github.com/letta-ai/letta` (21.7K ⭐) | Virtual context management, self-editing memory blocks |
| Mem0 | `github.com/mem0ai/mem0` (50.8K ⭐) | Multi-level memory, automatic fact extraction, +26% accuracy |
| RAPTOR | arXiv:2401.18059 (Stanford) | Recursive tree-organized retrieval, +20% on QuALITY |
| LanceDB | `github.com/lancedb/lancedb` (9.6K ⭐) | Embedded hybrid search (vector + FTS + SQL) |
| ChromaDB | `github.com/chroma-core/chroma` (26.8K ⭐) | Simple API, auto-embedding, popular |
| Qdrant | `github.com/qdrant/qdrant` (29.8K ⭐) | Sparse vectors, built-in RRF, quantization |
| hnswlib | `github.com/nmslib/hnswlib` (5.1K ⭐) | Ultra-lightweight HNSW, header-only C++ |
| Docling | `github.com/docling-project/docling` (56.3K ⭐) | Multi-format document parsing, layout understanding |
| Google Grounding | Gemini API `google_search` tool | Real-time web search integration with citations |
| nanochat | `github.com/karpathy/nanochat` (50K ⭐) | Complete LLM training harness, single `--depth` dial |
| Worksafety-superassistant | Local project analysis | Structure-aware chunking, 3-signal scoring, query caching |
| AutoResearch | `github.com/karpathy/autoresearch` (51.1K ⭐) | Autonomous AI-driven experimentation, 3-file paradigm for iterative optimization |

---

*This document supplements `concept/rag-memory-architecture.md` with extended research findings from April 2026. All recommendations are integrated into the Variant C enhancement plan.*
