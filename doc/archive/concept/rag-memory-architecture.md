# RAG, Memory & Conversational Context — Architecture Proposal

**Version:** 1.0 · **Date:** 2026-03-23  
**Author:** AI Architecture Analysis · **Status:** Proposal  
**Scope:** Taris personal assistant — PicoClaw (Pi 3), OpenClaw (Pi 5+), Server-class

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Requirements Consolidation](#3-requirements-consolidation)
4. [State-of-the-Art Research](#4-state-of-the-art-research)
5. [Architecture Variants Comparison](#5-architecture-variants-comparison)
6. [Proposed Architecture — Hybrid Tiered RAG + Multi-Level Memory](#6-proposed-architecture)
7. [Implementation Plan](#7-implementation-plan)
8. [Consolidated TODO List](#8-consolidated-todo-list)
9. [Risk Analysis](#9-risk-analysis)

---

## 1. Executive Summary

Taris requires an integrated **RAG (Retrieval-Augmented Generation) + Multi-Level Memory** system that:

- Provides conversational context across sessions (short/middle/long-term memory)
- Enables document-grounded Q&A (personal knowledge base per user)
- Scales from Pi 3 (1 GB RAM) to server-class hardware (16+ GB RAM)
- Supports future multimodal RAG (text + images + tables)
- Combines local and remote knowledge sources
- Remains testable, debuggable, and maintainable on edge hardware

**Recommended approach:** **Variant C — Hybrid Tiered RAG** with adaptive retrieval pipeline, FTS5 as universal baseline, optional vector search on capable hardware, and a 3-tier memory compaction system using LLM summarization.

> 📖 **Extended Research:** See [rag-memory-extended-research.md](rag-memory-extended-research.md) for detailed analysis of advanced memory concepts (MemGPT/Letta, Mem0, RAPTOR), vector database comparison (LanceDB, ChromaDB, Qdrant, hnswlib), document processing (Docling), Google Grounding, edge LLM fine-tuning (nanochat), autonomous experimentation (Karpathy AutoResearch), and Worksafety-superassistant reference patterns. The extended research raises the Variant C score from 4.15 → 4.45.

### Key Decision: Why Not a Single Off-the-Shelf Framework?

Existing RAG frameworks (LangChain, LlamaIndex, Haystack) are designed for server environments with 8+ GB RAM and Python 3.10+. On a Raspberry Pi 3 with 1 GB RAM, their dependency trees alone (torch, transformers, numpy, etc.) would exhaust memory. The taris project already has a working storage adapter pattern (`store_base.py` → `store_sqlite.py`) that is purpose-built for edge deployment. **Extending it is cheaper and safer than replacing it.**

---

## 2. Current State Analysis

### 2.1 What Is Already Built

| Component | Status | Technology | Location |
|-----------|--------|------------|----------|
| **Document upload** | ✅ Active | PDF/DOCX/TXT/MD → 512-char chunks | `src/features/bot_documents.py` |
| **FTS5 keyword search** | ✅ Active | SQLite FTS5 (BM25 ranking) | `src/core/store_sqlite.py` |
| **RAG context injection** | ✅ Active | Top-3 FTS5 chunks → LLM prompt | `src/telegram/bot_handlers.py:722` |
| **Conversation history** | ✅ Active | Sliding window (50 msgs, configurable) | `store_sqlite.py` / `chat_history` table |
| **Vector search schema** | ✅ Schema ready | `sqlite-vec` FLOAT[384] | `store_sqlite.py` (opt-in) |
| **PostgreSQL adapter** | ✅ Written | pgvector HNSW indexes | `src/core/store_postgres.py` |
| **LLM multi-provider** | ✅ Active | 6 providers + local fallback | `src/core/bot_llm.py` |
| **Storage adapter pattern** | ✅ Active | Protocol-based, SQLite/Postgres | `store_base.py` / `store.py` |

### 2.2 What Is Missing

| Component | Priority | Complexity |
|-----------|----------|------------|
| **Vector embeddings pipeline** (generate + store) | High | Medium |
| **Multi-tier memory** (short→middle→long compaction) | High | High |
| **Hybrid retrieval** (FTS5 + vector fusion) | Medium | Medium |
| **Document sharing** (per-user, group, all) | Medium | Low |
| **Admin RAG dashboard** (chunks, logs, settings) | Medium | Medium |
| **Semantic reranking** (cross-encoder or LLM-as-judge) | Low | Medium |
| **Multimodal RAG** (images, tables from PDFs) | Low | High |
| **Remote RAG service** (MCP server connection) | Low | High |
| **Memory management UI** (view, delete, configure) | Medium | Low |

### 2.3 Hardware Constraints

| Tier | RAM | Max Chunks | Vector Search | Local LLM | Memory Compaction |
|------|-----|------------|---------------|-----------|-------------------|
| **PicoClaw** (Pi 3) | 1 GB | ~50k | ⚠️ 10k vectors | ❌ (cloud only) | Via cloud LLM |
| **OpenClaw CPU** (Pi 5) | 8 GB | 500k+ | ✅ sqlite-vec | ✅ Phi-3-mini | ✅ Local or cloud |
| **OpenClaw NPU** (Jetson/RK3588) | 8-16 GB | Millions | ✅ pgvector HNSW | ✅ 7B models | ✅ Local |
| **Server** (x86/ARM64) | 16+ GB | Unlimited | ✅ pgvector | ✅ Any model | ✅ Full pipeline |

---

## 3. Requirements Consolidation

All RAG/memory/knowledge-related items from `TODO.md` §2, §3, §4, §9, §10, §11, consolidated:

### 3.1 Core RAG Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| R1 | Upload documents (PDF, DOCX, TXT, MD) as knowledge base | TODO §10 |
| R2 | Use documents in multimodal RAG for chat | TODO §10 |
| R3 | Documents contain text, images, tables | TODO §10 |
| R4 | Documents assigned to user or shared to all | TODO §10 |
| R5 | Duplicate detection by hash/name/size | TODO §10 |
| R6 | Quality check of chunks after upload | TODO §10 |
| R7 | Admin can view/delete all documents, manage sharing | TODO §3 |
| R8 | Documents downloadable in original format | TODO §3 |
| R9 | View txt/pdf/rtf/docx/md documents inline | TODO §3 |
| R10 | RAG settings configurable (temperature, chunks, system prompt) | TODO §4 |
| R11 | Timeout monitoring for RAG services | TODO §4 |
| R12 | RAG activity logging (chunks found, prompt, LLM response) | TODO §4 |
| R13 | Upload restrictions and DB size info to user | TODO §4 |
| R14 | Parsing statistics after upload | TODO §4 |

### 3.2 Memory Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| M1 | Short-term memory (current conversation context) | TODO §10.1 |
| M2 | Middle-term memory (compressed recent conversations) | TODO §10.1 |
| M3 | Long-term memory (summarized/compacted, merged) | TODO §10.1 |
| M4 | Delete personal context (memory) via Profile menu | TODO §2.1 |
| M5 | Memory parameters configurable in Admin panel | TODO §10.1 |
| M6 | User can switch off using memories in conversations | TODO §10.1 |
| M7 | All memories stored in database | TODO §9.1 |

### 3.3 Context & Control Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| C1 | Activities stored as text for LLM context | TODO §11 |
| C2 | Context-dependent activity execution | TODO §11 |
| C3 | Voice-controlled switching between UI functions | TODO §11, §12 |
| C4 | Local + remote RAG combination | TODO §4.1, §4.2 |
| C5 | MCP server connection for remote RAG | TODO §4.2 |
| C6 | Local LLM for RAG optional, configurable | TODO §4.1 |
| C7 | Settings via Admin panel for local and remote RAG | TODO §4.1, §4.2 |

---

## 4. State-of-the-Art Research

### 4.1 Libraries & Frameworks Comparison

#### A. Full RAG Frameworks

| Framework | RAM Footprint | Pi 3 Viable? | Strengths | Weaknesses |
|-----------|---------------|--------------|-----------|------------|
| **LangChain** | 200–500 MB + deps | ❌ (torch required) | Huge ecosystem, chains/agents, 200+ integrations | Heavy, unstable API, over-abstracted |
| **LlamaIndex** | 300–600 MB + deps | ❌ (torch required) | Best for document indexing, tree/graph RAG | Heavy, Python-only, slow on ARM |
| **Haystack 2.x** | 200–400 MB + deps | ❌ | Pipeline-first design, easy testing | Requires transformers/sentence-transformers |
| **Canopy (Pinecone)** | 100–200 MB | ⚠️ (cloud-only vectors) | Managed vector DB, simple API | Vendor lock-in, no local vectors |
| **RAGFlow** | 500+ MB | ❌ | Best document parsing (OCR, tables) | Requires Docker, Elasticsearch |
| **Custom (current taris)** | **<10 MB** overhead | **✅** | Minimal deps, edge-first, full control | Must build retrieval pipeline manually |

**Verdict:** No full framework fits Pi 3. The custom approach is correct. We extend it.

#### B. Embedding Models (Edge-Compatible)

| Model | Dims | Size (ONNX) | RAM (inference) | Pi 3 Viable? | Quality (MTEB avg) |
|-------|------|-------------|-----------------|--------------|---------------------|
| **all-MiniLM-L6-v2** | 384 | 22 MB | 90 MB | ⚠️ (load-unload) | 0.630 |
| **all-MiniLM-L12-v2** | 384 | 33 MB | 120 MB | ⚠️ | 0.648 |
| **bge-small-en-v1.5** | 384 | 33 MB | 100 MB | ⚠️ | 0.632 |
| **gte-small** | 384 | 33 MB | 100 MB | ⚠️ | 0.631 |
| **nomic-embed-text-v1.5** | 768 | 137 MB | 300 MB | ❌ | 0.690 |
| **e5-small-v2** | 384 | 33 MB | 100 MB | ⚠️ | 0.619 |
| **ONNX-optimized MiniLM** | 384 | 22 MB | **60 MB** | **✅** (via onnxruntime) | 0.630 |

**Verdict:** `all-MiniLM-L6-v2` in ONNX format is the optimal choice. 22 MB model, 60 MB inference RAM via onnxruntime (no torch). On Pi 3: load on demand during document ingestion, unload after. On Pi 5+: keep resident.

#### C. Vector Storage Solutions

| Solution | Storage | ARM aarch64 | Dependencies | Features |
|----------|---------|-------------|--------------|----------|
| **sqlite-vec** | SQLite extension | ✅ | 0 (C extension) | FLOAT[N] columns, brute-force + ANN |
| **pgvector** | PostgreSQL ext | ✅ | PostgreSQL server | HNSW/IVFFlat, production-grade |
| **Chroma** | Client/server | ✅ | ~200 MB RAM | Easy API, in-process mode |
| **LanceDB** | Embedded | ✅ | ~50 MB RAM | Columnar, versioned, fast |
| **Qdrant** | Client/server | ✅ | ~300 MB RAM | HNSW, filtering, multi-tenancy |
| **FAISS** | In-process | ✅ | numpy | IVF/PQ, GPU support, Meta-backed |

**Verdict:** `sqlite-vec` (already integrated) for PicoClaw. `pgvector` (already written) for OpenClaw. No additional dependencies needed. Chroma or LanceDB considered only if dedicated vector operations prove insufficient.

#### D. Document Parsing Libraries

| Library | PDF | DOCX | Tables | Images | Size | Pi 3? |
|---------|-----|------|--------|--------|------|-------|
| **pdfminer.six** (current) | ✅ | ❌ | ⚠️ (text only) | ❌ | 5 MB | ✅ |
| **python-docx** (current) | ❌ | ✅ | ⚠️ (basic) | ❌ | 2 MB | ✅ |
| **PyMuPDF (fitz)** | ✅ | ❌ | ✅ (layout-aware) | ✅ (extract) | 15 MB | ✅ |
| **unstructured** | ✅ | ✅ | ✅ | ✅ | 500+ MB | ❌ |
| **docling** (IBM) | ✅ | ✅ | ✅ (excellent) | ✅ | 200+ MB | ❌ |
| **marker** | ✅ | ❌ | ✅ | ✅ | 300+ MB | ❌ |

**Verdict:** Keep pdfminer.six + python-docx for Pi 3. Add PyMuPDF optionally for table/image extraction on Pi 5+. `unstructured`/`docling` only on server-class hardware.

#### E. Memory Compaction Concepts (Academic & Industry)

| Concept | Source | Key Idea |
|---------|--------|----------|
| **MemGPT / Letta** | UC Berkeley, 2023 | OS-inspired memory hierarchy: main context (working) + archival (vector DB) + recall (recent). Self-editing memory via function calls. |
| **Generative Agents** (Stanford) | Park et al., 2023 | Reflection: periodic LLM summarization of observations → memory stream. Retrieval via recency + importance + relevance scoring. |
| **LangMem** | LangChain, 2025 | Background memory manager: extracts facts from conversations, stores as semantic triples, auto-consolidates. |
| **Zep** | Zep Inc., 2024 | Async memory extraction: entity graphs, temporal summaries, session-level summaries. Separate ingestion pipeline. |
| **Mem0** | Mem0 Inc., 2025 | User-level memory: extracts preferences, facts, relationships from conversations. Graph + vector hybrid. |
| **Sliding Window + Summary** | Common pattern | Simplest: when window full, LLM summarizes oldest N messages → compact into 1 "summary" message. |

**Verdict for taris:** The **Sliding Window + LLM Summary** pattern (inspired by MemGPT's tiered approach) is the right fit:
- Simple to implement (no graph DB, no entity extraction)
- Works with any LLM (cloud or local)
- Testable (summary quality measurable)
- Low RAM overhead (just additional DB rows)
- Extensible to entity extraction later

### 4.2 Key Research Papers & Concepts

| Paper / Project | Year | Relevance to Taris |
|----------------|------|-------------------|
| *"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"* (Lewis et al.) | 2020 | Foundation paper for RAG. Key insight: retrieve-then-generate beats fine-tuning for factual tasks. |
| *"RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval"* | 2024 | Hierarchical summarization of chunks into a tree. Enables retrieval at different granularity. Applicable to long-term memory compaction. |
| *"Self-RAG: Learning to Retrieve, Generate, and Critique"* | 2023 | LLM decides when to retrieve (not always). Reduces irrelevant context injection. Applicable to "smart retrieval" toggle. |
| *"Corrective RAG (CRAG)"* | 2024 | Add a retrieval evaluator: if chunks are irrelevant, try web search or skip RAG. Prevents hallucination from bad chunks. |
| *"MemGPT: Towards LLMs as Operating Systems"* | 2023 | OS-inspired memory hierarchy with paging. Most relevant architecture for multi-tier memory. |
| *"Adaptive RAG"* | 2024 | Route queries: simple → no RAG, factual → RAG, complex → iterative RAG. Reduces latency for simple queries. |
| *"ColBERT v2"* | 2022 | Late-interaction retrieval: token-level matching instead of single-vector comparison. Better accuracy, more expensive. Future consideration for OpenClaw. |

### 4.3 MCP (Model Context Protocol) for Remote RAG

MCP is Anthropic's open protocol for connecting LLMs to external tools and data sources. Relevant for `TODO §4.2 — Remote RAG via MCP`.

| Aspect | Detail |
|--------|--------|
| **Protocol** | JSON-RPC 2.0 over stdio or HTTP/SSE |
| **Python SDK** | `mcp` package (pip installable, ~5 MB) |
| **Server model** | taris would run an MCP server exposing `search_knowledge(query)` tool |
| **Client model** | taris would connect to external MCP servers for remote knowledge bases |
| **Edge viability** | ✅ — lightweight protocol, no heavy deps |
| **Implementation effort** | Medium — wrap existing `store.search_fts()` / `store.search_similar()` as MCP tools |

---

## 5. Architecture Variants Comparison

### Variant A: FTS5-Only (Minimal)

**Concept:** Keep current architecture. FTS5 keyword search only. No embeddings. No memory tiers.

```
User message → FTS5 search → top-3 chunks → LLM prompt → response
                                                ↑
                              conversation history (50 msgs, flat window)
```

| KPI | Score | Notes |
|-----|-------|-------|
| **Resource usage** | ⭐⭐⭐⭐⭐ | Zero additional RAM. FTS5 built into SQLite. |
| **Performance** | ⭐⭐⭐⭐ | BM25 search: <10 ms for 100k chunks |
| **Retrieval quality** | ⭐⭐ | Keyword-only, misses semantic matches ("car" ≠ "automobile") |
| **Complexity** | ⭐⭐⭐⭐⭐ | Already implemented. No new code needed. |
| **Implementation effort** | ⭐⭐⭐⭐⭐ | 0 days — already done |
| **Flexibility** | ⭐⭐ | Cannot do semantic search, no memory compaction |
| **Established** | ⭐⭐⭐⭐⭐ | SQLite FTS5 is battle-tested (15+ years) |
| **Testable/Debuggable** | ⭐⭐⭐⭐⭐ | SQL queries, deterministic results |
| **Extendable** | ⭐⭐ | Hard to add semantic without rewrite |
| **Multimodal future** | ⭐ | Text only, no image/table understanding |

**When to choose:** If resources are extremely constrained (Pi Zero) or if keyword search quality is sufficient.

---

### Variant B: Vector RAG (Embeddings-First)

**Concept:** Replace FTS5 with embedding-based retrieval. All documents embedded at upload time. Cosine similarity search.

```
Document upload → chunk → embed (MiniLM-L6) → store vectors (sqlite-vec)
User message → embed query → cosine search → top-5 chunks → LLM prompt
                                                    ↑
                                   conversation history (50 msgs, flat window)
```

| KPI | Score | Notes |
|-----|-------|-------|
| **Resource usage** | ⭐⭐⭐ | +90 MB for embedding model (load/unload on Pi 3), +15 MB per 10k vectors |
| **Performance** | ⭐⭐⭐ | Embedding: ~0.5 s/chunk (Pi 3), ~0.05 s/chunk (Pi 5). Search: <50 ms |
| **Retrieval quality** | ⭐⭐⭐⭐ | Semantic matching ("car" ≈ "automobile"). Better recall for paraphrased queries |
| **Complexity** | ⭐⭐⭐ | Moderate — embedding pipeline + vector storage + model management |
| **Implementation effort** | ⭐⭐⭐ | ~5-7 days — embedding pipeline, model management, batch processing |
| **Flexibility** | ⭐⭐⭐ | Supports semantic search, but loses exact keyword matching |
| **Established** | ⭐⭐⭐⭐ | sqlite-vec is newer but stable; pgvector is production-grade |
| **Testable/Debuggable** | ⭐⭐⭐ | Harder to debug ("why was this chunk ranked #1?"), requires similarity thresholds |
| **Extendable** | ⭐⭐⭐⭐ | Easy to add multimodal (CLIP embeddings use same pipeline) |
| **Multimodal future** | ⭐⭐⭐⭐ | Image embeddings use same vector store and search API |

**When to choose:** If semantic understanding is critical and hardware supports it (Pi 5+).

---

### Variant C: Hybrid Tiered RAG (Recommended) ⭐

**Concept:** Combine FTS5 (keyword) + vector search (semantic) with score fusion. Add 3-tier memory compaction. Adaptive retrieval (skip RAG for simple queries).

```
┌─────────────────────────────────────────────────────────────────┐
│                    RETRIEVAL PIPELINE                            │
│                                                                 │
│  User message                                                   │
│      │                                                          │
│      ├─→ [Query Classifier] ─→ simple? → skip RAG, use history  │
│      │                        complex? ↓                        │
│      ├─→ [FTS5 Search] ──────→ BM25 candidates (top-10)        │
│      │                              │                           │
│      ├─→ [Vector Search] ─────→ cosine candidates (top-10)      │
│      │   (if available)             │                           │
│      │                              ▼                           │
│      │                    [Reciprocal Rank Fusion]              │
│      │                              │                           │
│      │                              ▼                           │
│      │                    top-5 fused chunks                    │
│      │                              │                           │
│      └──────────────────────────────┤                           │
│                                     ▼                           │
│  ┌──────────────────────────────────────────────┐               │
│  │          CONTEXT ASSEMBLY                     │               │
│  │                                               │               │
│  │  1. System prompt (security preamble)         │               │
│  │  2. Long-term memory summary (if exists)      │               │
│  │  3. Middle-term summaries (last 3)            │               │
│  │  4. RAG chunks (top-5, fused)                 │               │
│  │  5. Short-term history (last 15 messages)     │               │
│  │  6. Current user message                      │               │
│  └──────────────────────────────────────────────┘               │
│                         │                                       │
│                         ▼                                       │
│                   [LLM Provider]                                │
│                         │                                       │
│                         ▼                                       │
│                   Response → user                               │
│                         │                                       │
│                   [Memory Writer]                               │
│                         │                                       │
│                   append to short-term                          │
│                   (trigger compaction if full)                   │
└─────────────────────────────────────────────────────────────────┘
```

#### Memory Compaction Flow

```
SHORT-TERM MEMORY (chat_history table)
  │   Sliding window: last N messages (default 15, configurable)
  │   Storage: full message text in DB
  │
  │   When window reaches max:
  ▼
MIDDLE-TERM MEMORY (memory_summaries table)
  │   LLM summarizes the oldest batch (e.g., 15 messages → 1 summary)
  │   Summary stored with timestamp + source message IDs
  │   Summaries: ~200-400 chars each, injected into LLM context
  │   Retention: last K summaries (default 10, configurable)
  │
  │   When middle-term count reaches max:
  ▼
LONG-TERM MEMORY (memory_long table)
  │   LLM compacts multiple middle-term summaries into one
  │   "User preferences, key facts, recurring topics"
  │   One entry per user, periodically refreshed
  │   Optional: embed and store in vector DB for semantic recall
  │
  │   User controls:
  ▼
  Profile → "🧠 Memory" → View / Delete / Configure / Toggle
```

#### Score Fusion: Reciprocal Rank Fusion (RRF)

```python
def reciprocal_rank_fusion(fts5_results, vector_results, k=60):
    """Combine FTS5 and vector search results using RRF scoring."""
    scores = {}
    for rank, chunk in enumerate(fts5_results):
        scores[chunk["doc_id"]] = scores.get(chunk["doc_id"], 0) + 1 / (k + rank + 1)
    for rank, chunk in enumerate(vector_results):
        scores[chunk["doc_id"]] = scores.get(chunk["doc_id"], 0) + 1 / (k + rank + 1)
    # Sort by fused score, return top-N
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

| KPI | Score | Notes |
|-----|-------|-------|
| **Resource usage** | ⭐⭐⭐ | FTS5 baseline free. Vectors optional. Memory compaction uses LLM (cloud or local). |
| **Performance** | ⭐⭐⭐⭐ | FTS5: <10 ms. Vector: <50 ms. Fusion: <5 ms. Total: <65 ms retrieval. |
| **Retrieval quality** | ⭐⭐⭐⭐⭐ | Best of both: exact keywords + semantic similarity. RRF proven to exceed either alone. |
| **Complexity** | ⭐⭐⭐ | Moderate — fusion logic, memory compaction, adaptive routing |
| **Implementation effort** | ⭐⭐⭐ | ~10-15 days total (phased: Phase A=3d, B=5d, C=5d, D=2d) |
| **Flexibility** | ⭐⭐⭐⭐⭐ | FTS5-only on Pi 3, hybrid on Pi 5, full pipeline on server. Graceful degradation. |
| **Established** | ⭐⭐⭐⭐ | RRF is standard (Cormack et al., 2009). Memory compaction proven by MemGPT/Zep. |
| **Testable/Debuggable** | ⭐⭐⭐⭐ | Each stage independently testable. RAG logging captures chunk selection rationale. |
| **Extendable** | ⭐⭐⭐⭐⭐ | Add new retrieval sources (MCP, web search) as additional rank lists in RRF. Multimodal via CLIP vectors. |
| **Multimodal future** | ⭐⭐⭐⭐⭐ | Image/table embeddings join same vector store + RRF pipeline. |

---

### Variant D: Graph RAG (Knowledge Graph)

**Concept:** Extract entities and relationships from documents. Build a knowledge graph. Traverse graph for context.

```
Document → NER/relation extraction → knowledge graph (nodes + edges)
User query → graph traversal → subgraph context → LLM prompt
```

| KPI | Score | Notes |
|-----|-------|-------|
| **Resource usage** | ⭐⭐ | Graph DB (Neo4j/NetworkX) + NER model (~200 MB). Too heavy for Pi 3. |
| **Performance** | ⭐⭐⭐ | Graph traversal fast, but NER extraction slow on ARM |
| **Retrieval quality** | ⭐⭐⭐⭐⭐ | Best for multi-hop reasoning ("Who is the CEO of the company that...") |
| **Complexity** | ⭐⭐ | Very high — NER pipeline, graph schema, traversal algorithms |
| **Implementation effort** | ⭐ | ~20-30 days. Requires NER model selection, graph schema design, query language. |
| **Flexibility** | ⭐⭐⭐ | Excellent for structured knowledge, poor for free-form text |
| **Established** | ⭐⭐⭐ | Microsoft GraphRAG (2024) is promising but resource-heavy |
| **Testable/Debuggable** | ⭐⭐⭐ | Graph visualizable, but NER errors cascade |
| **Extendable** | ⭐⭐⭐ | Good for CRM relationships, poor for general documents |
| **Multimodal future** | ⭐⭐ | OCR → NER → graph possible but complex |

**When to choose:** When knowledge has clear entity-relationship structure (CRM, medical records). Not recommended as primary approach for a personal assistant with diverse document types.

---

### Variant E: Cloud-First RAG Service

**Concept:** Offload all RAG to cloud services (Pinecone, Weaviate Cloud, OpenAI Assistants API).

| KPI | Score | Notes |
|-----|-------|-------|
| **Resource usage** | ⭐⭐⭐⭐⭐ | Zero local resources for RAG. LLM + vectors in cloud. |
| **Performance** | ⭐⭐⭐ | Network latency (100-500 ms per query). Unreliable offline. |
| **Retrieval quality** | ⭐⭐⭐⭐ | Managed services have excellent retrieval quality |
| **Complexity** | ⭐⭐⭐⭐ | Simple client code, complex vendor management |
| **Implementation effort** | ⭐⭐⭐⭐ | ~3-5 days. API integration only. |
| **Flexibility** | ⭐⭐ | Vendor lock-in. No offline. Monthly costs. |
| **Established** | ⭐⭐⭐⭐⭐ | Production services used by thousands of companies |
| **Testable/Debuggable** | ⭐⭐ | Black box. Vendor dashboard for debugging. |
| **Extendable** | ⭐⭐⭐ | Limited by vendor API surface |
| **Multimodal future** | ⭐⭐⭐⭐ | Vendors adding multimodal rapidly (OpenAI, Google) |

**When to choose:** For rapid prototyping or if offline operation is not required. Not recommended as sole approach for taris (edge-first design).

---

### KPI Comparison Matrix (All 5 Variants)

| KPI | Weight | A: FTS5-Only | B: Vector | C: Hybrid ⭐ | D: Graph | E: Cloud |
|-----|--------|:---:|:---:|:---:|:---:|:---:|
| Resource usage | 15% | 5 | 3 | 3 | 2 | 5 |
| Performance | 10% | 4 | 3 | 4 | 3 | 3 |
| Retrieval quality | 20% | 2 | 4 | **5** | 5 | 4 |
| Complexity | 10% | 5 | 3 | 3 | 2 | 4 |
| Implementation effort | 10% | 5 | 3 | 3 | 1 | 4 |
| Flexibility | 10% | 2 | 3 | **5** | 3 | 2 |
| Established | 5% | 5 | 4 | 4 | 3 | 5 |
| Testable/Debuggable | 5% | 5 | 3 | 4 | 3 | 2 |
| Extendable/Maintainable | 5% | 2 | 4 | **5** | 3 | 3 |
| Multimodal future | 10% | 1 | 4 | **5** | 2 | 4 |
| **Weighted Score** | 100% | **3.15** | **3.40** | **4.15** | **2.80** | **3.60** |

**Winner: Variant C (Hybrid Tiered RAG)** — best balance of quality, flexibility, and edge compatibility.

---

## 6. Proposed Architecture — Hybrid Tiered RAG + Multi-Level Memory

### 6.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            TARIS ASSISTANT                              │
│                                                                         │
│  ┌─────────────────────┐    ┌─────────────────────────────────────┐     │
│  │   INPUT CHANNELS     │    │         MEMORY SYSTEM                │     │
│  │                      │    │                                     │     │
│  │  Telegram  Web  Voice│    │  ┌─────────────┐  ┌──────────────┐ │     │
│  │     │       │    │   │    │  │ Short-term   │  │ Long-term    │ │     │
│  └─────┼───────┼────┼───┘    │  │ (15 msgs)    │  │ (1 summary)  │ │     │
│        │       │    │        │  └──────┬──────┘  └──────┬───────┘ │     │
│        ▼       ▼    ▼        │         │                │         │     │
│  ┌─────────────────────┐    │  ┌──────┴──────┐         │         │     │
│  │   QUERY ROUTER       │    │  │ Middle-term │         │         │     │
│  │                      │    │  │ (10 summaries)        │         │     │
│  │  simple → history    │    │  └─────────────┘         │         │     │
│  │  factual → RAG       │    └──────────────────────────┼─────────┘     │
│  │  complex → RAG+mem   │                               │               │
│  └──────────┬───────────┘                               │               │
│             │                                           │               │
│             ▼                                           │               │
│  ┌─────────────────────────────────────────┐           │               │
│  │         RETRIEVAL ENGINE                 │           │               │
│  │                                          │           │               │
│  │  ┌──────────┐  ┌────────────────────┐   │           │               │
│  │  │ FTS5     │  │ Vector Search      │   │           │               │
│  │  │ (always) │  │ (if available)     │   │           │               │
│  │  └────┬─────┘  └────────┬───────────┘   │           │               │
│  │       │                 │                │           │               │
│  │       └────────┬────────┘                │           │               │
│  │                ▼                         │           │               │
│  │   ┌────────────────────────┐            │           │               │
│  │   │ Reciprocal Rank Fusion │            │           │               │
│  │   │ (score combination)    │            │           │               │
│  │   └────────────┬───────────┘            │           │               │
│  │                │                         │           │               │
│  │   ┌────────────▼───────────┐            │           │               │
│  │   │ Optional: MCP Remote   │            │           │               │
│  │   │ (external knowledge)   │            │           │               │
│  │   └────────────┬───────────┘            │           │               │
│  └────────────────┼─────────────────────────┘           │               │
│                   │                                     │               │
│                   ▼                                     │               │
│  ┌─────────────────────────────────────────────────────┐│               │
│  │              CONTEXT ASSEMBLER                       ││               │
│  │                                                      ││               │
│  │  [security preamble]                                 ││               │
│  │  [long-term memory]  ◄───────────────────────────────┘│               │
│  │  [middle-term summaries]                              │               │
│  │  [RAG chunks (fused)]                                 │               │
│  │  [short-term history]                                 │               │
│  │  [language instruction]                               │               │
│  │  [user message]                                       │               │
│  └──────────────────────┬────────────────────────────────┘               │
│                         │                                                │
│                         ▼                                                │
│              ┌────────────────────┐                                      │
│              │   LLM PROVIDER     │                                      │
│              │   (6 backends)     │                                      │
│              └────────┬───────────┘                                      │
│                       │                                                  │
│                       ▼                                                  │
│              ┌────────────────────┐                                      │
│              │  RAG ACTIVITY LOG  │                                      │
│              │  (chunks, prompt,  │                                      │
│              │   response, timing)│                                      │
│              └────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Database Schema Extensions

```sql
-- New table: memory summaries (middle-term)
CREATE TABLE IF NOT EXISTS memory_summaries (
    id          TEXT PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    summary     TEXT NOT NULL,           -- LLM-generated summary
    source_ids  TEXT,                     -- JSON array of source chat_history IDs
    msg_count   INTEGER DEFAULT 0,       -- Number of messages summarized
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- New table: long-term memory (one per user)
CREATE TABLE IF NOT EXISTS memory_long (
    chat_id     INTEGER PRIMARY KEY,
    summary     TEXT NOT NULL,           -- Consolidated long-term summary
    facts       TEXT,                     -- JSON: extracted key facts
    preferences TEXT,                     -- JSON: user preferences
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- New table: RAG activity log
CREATE TABLE IF NOT EXISTS rag_log (
    id          TEXT PRIMARY KEY,
    chat_id     INTEGER NOT NULL,
    query       TEXT NOT NULL,
    chunks_used TEXT,                     -- JSON array of {doc_id, chunk_text, score}
    prompt_len  INTEGER,
    response_len INTEGER,
    retrieval_ms INTEGER,                -- Retrieval latency in ms
    llm_ms      INTEGER,                 -- LLM latency in ms
    provider    TEXT,                     -- LLM provider used
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- New table: document sharing
CREATE TABLE IF NOT EXISTS doc_sharing (
    doc_id      TEXT NOT NULL,
    owner_id    INTEGER NOT NULL,         -- original uploader
    shared_with INTEGER,                  -- NULL = shared with all
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (doc_id, shared_with)
);

-- New table: RAG settings (per-user overrides)
CREATE TABLE IF NOT EXISTS rag_settings (
    chat_id          INTEGER PRIMARY KEY,
    use_memory       INTEGER DEFAULT 1,   -- 0 = disable memory in context
    use_rag          INTEGER DEFAULT 1,   -- 0 = disable RAG in context
    rag_top_k        INTEGER DEFAULT 5,
    rag_max_chars    INTEGER DEFAULT 2000,
    temperature      REAL DEFAULT 0.7,
    system_prompt    TEXT,                 -- Custom system prompt override
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.3 Memory Compaction Algorithm

```python
# Constants (configurable via Admin panel)
SHORT_TERM_WINDOW = 15       # messages in active context
MIDDLE_TERM_MAX = 10         # summaries before long-term compaction
SUMMARY_BATCH_SIZE = 15      # messages per summary
LONG_TERM_REFRESH_INTERVAL = 7 * 24 * 3600  # 7 days

async def compact_short_to_middle(chat_id: int):
    """When short-term window is full, summarize oldest batch."""
    history = store.get_history(chat_id, last_n=SHORT_TERM_WINDOW + SUMMARY_BATCH_SIZE)
    
    if len(history) <= SHORT_TERM_WINDOW:
        return  # Nothing to compact
    
    # Take the oldest batch (messages that will be removed from short-term)
    oldest_batch = history[:SUMMARY_BATCH_SIZE]
    
    # LLM summarization
    messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in oldest_batch)
    summary = await ask_llm(
        f"Summarize this conversation concisely, preserving key facts, "
        f"decisions, and user preferences:\n\n{messages_text}",
        timeout=30
    )
    
    # Store in middle-term
    store.save_memory_summary(chat_id, summary, 
                               source_ids=[m['id'] for m in oldest_batch])
    
    # Trim short-term (keep only last SHORT_TERM_WINDOW)
    store.trim_history(chat_id, keep_last=SHORT_TERM_WINDOW)

async def compact_middle_to_long(chat_id: int):
    """When middle-term has too many summaries, merge into long-term."""
    summaries = store.get_memory_summaries(chat_id)
    
    if len(summaries) <= MIDDLE_TERM_MAX:
        return
    
    # Take oldest summaries to compact
    to_compact = summaries[:len(summaries) - MIDDLE_TERM_MAX // 2]
    existing_long = store.get_long_term_memory(chat_id)
    
    compact_text = "\n---\n".join(s['summary'] for s in to_compact)
    if existing_long:
        compact_text = f"Previous knowledge:\n{existing_long['summary']}\n\n" \
                       f"New information:\n{compact_text}"
    
    long_summary = await ask_llm(
        f"Merge and consolidate these conversation summaries into a single "
        f"concise profile of the user. Include: key preferences, important "
        f"facts discussed, recurring topics, and decisions made.\n\n{compact_text}",
        timeout=30
    )
    
    store.save_long_term_memory(chat_id, long_summary)
    store.delete_memory_summaries(chat_id, [s['id'] for s in to_compact])
```

### 6.4 Adaptive Query Routing

```python
def classify_query(user_text: str, has_documents: bool) -> str:
    """Decide retrieval strategy based on query type."""
    # Heuristic classification (no LLM call — fast)
    text_lower = user_text.lower().strip()
    
    # Greetings, simple commands — no RAG needed
    if len(text_lower) < 15 or text_lower in GREETING_PATTERNS:
        return "simple"
    
    # Questions with factual indicators — use RAG
    if any(kw in text_lower for kw in ["что", "как", "когда", "где", "почему",
                                         "what", "how", "when", "where", "why",
                                         "was", "wie", "wann", "wo", "warum"]):
        return "factual" if has_documents else "simple"
    
    # Default: use conversation history + optional RAG
    return "contextual"
```

### 6.5 Embedding Pipeline (Optional, Hardware-Dependent)

```python
class EmbeddingService:
    """Lazy-loaded embedding model. On Pi 3: load/unload per batch.
    On Pi 5+: keep resident."""
    
    def __init__(self):
        self._model = None
        self._keep_resident = os.environ.get("EMBED_KEEP_RESIDENT", "0") == "1"
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of 384-dim vectors."""
        if self._model is None:
            self._load_model()
        
        vectors = self._model.encode(texts)  # onnxruntime inference
        
        if not self._keep_resident:
            self._unload_model()  # Free 90 MB on Pi 3
        
        return vectors.tolist()
    
    def _load_model(self):
        # Use ONNX Runtime for minimal footprint (no torch)
        from onnxruntime import InferenceSession
        self._model = SentenceEmbedder("all-MiniLM-L6-v2", backend="onnxruntime")
    
    def _unload_model(self):
        del self._model
        self._model = None
        import gc; gc.collect()
```

### 6.6 Hardware Tier Adaptation

```python
# Determined at startup based on available resources
class RAGCapability:
    FTS5_ONLY = "fts5"           # Pi 3, Pi Zero — keyword search only
    HYBRID = "hybrid"             # Pi 5 — FTS5 + vector search
    FULL = "full"                 # Server — hybrid + semantic reranking + MCP

def detect_rag_capability() -> RAGCapability:
    """Auto-detect hardware tier for RAG configuration."""
    has_vectors = store.has_vector_search()
    ram_gb = psutil.virtual_memory().total / (1024**3)
    
    if ram_gb >= 8 and has_vectors:
        return RAGCapability.FULL
    elif ram_gb >= 4 and has_vectors:
        return RAGCapability.HYBRID
    else:
        return RAGCapability.FTS5_ONLY
```

---

## 7. Implementation Plan

> **Status update — 2026-04-23** (verified against current `src/`):
> - **Phase A (Memory):** ❌ not started. `bot_memory.py`, `memory_summaries`, `memory_long` do not exist.
> - **Phase B (Enhanced RAG):** 🟡 partial. ✅ `EmbeddingService` (`bot_embeddings.py`), `rag_log` table (SQLite + Postgres), `vec_embeddings` (sqlite-vec / pgvector HNSW), document upload uses embeddings when available. ❌ `bot_retrieval.py` (RRF + adaptive router + context assembler) still missing — embeddings are generated but not fused into retrieval.
> - **Phase C (Document Management):** ❌ `doc_sharing` table missing; duplicate-detection by SHA-256 present in `bot_documents.py`; download + share UI not built.
> - **Phase D (Remote RAG & MCP):** 🟡 partial. ✅ `bot_mcp_client.py` exists (HTTP + circuit breaker) but **not wired into any handler**. ❌ `bot_mcp_server.py` missing. Detailed re-scope in [doc/todo/4.3-remote-mcp-rag.md](../../todo/4.3-remote-mcp-rag.md) — moves Phase D to a VPS/N8N service with a dedicated Skill+Agent on OpenClaw and a separate Postgres DB. That concept is **pending user review** before implementation starts.

### Phase A: Memory System (3-5 days)

**Goal:** 3-tier memory compaction (short → middle → long) with user controls.

| Task | Effort | Files |
|------|--------|-------|
| A1. Add `memory_summaries`, `memory_long`, `rag_settings` tables to `bot_db.py` | 0.5d | `bot_db.py` |
| A2. Add storage methods: `save_memory_summary()`, `get_memory_summaries()`, `save_long_term_memory()`, `get_long_term_memory()`, `get_rag_settings()`, `save_rag_settings()` | 1d | `store_base.py`, `store_sqlite.py` |
| A3. Implement compaction logic: `compact_short_to_middle()`, `compact_middle_to_long()` | 1d | new: `src/core/bot_memory.py` |
| A4. Integrate into chat handler: inject memory tiers into LLM context | 0.5d | `bot_handlers.py` |
| A5. Memory UI: Profile → "🧠 Memory" → View/Delete/Toggle per user | 1d | `bot_handlers.py`, `strings.json`, `telegram_menu_bot.py` |
| A6. Admin panel: Memory settings (window sizes, retention) | 0.5d | `bot_admin.py`, `bot_web.py` |
| A7. Tests: T26 memory round-trip, T27 compaction correctness | 0.5d | `test_voice_regression.py` |

**Dependencies:** Phase 2c (dual-write) must be active — ✅ already done.

---

### Phase B: Enhanced RAG Pipeline (5-7 days)

**Goal:** Hybrid retrieval (FTS5 + vector), RRF fusion, adaptive routing, RAG logging.

| Task | Effort | Files |
|------|--------|-------|
| B1. Embedding service: ONNX MiniLM-L6-v2 wrapper with load/unload | 1d | new: `src/core/bot_embeddings.py` |
| B2. Document upload: add embedding step (background thread) | 0.5d | `bot_documents.py` |
| B3. Reciprocal Rank Fusion: combine FTS5 + vector results | 0.5d | new: `src/core/bot_retrieval.py` |
| B4. Adaptive query router (heuristic, no LLM call) | 0.5d | `bot_retrieval.py` |
| B5. Context assembler: ordered injection of memory + RAG + history | 1d | `bot_retrieval.py` |
| B6. RAG activity log: `rag_log` table + write on every retrieval | 0.5d | `store_sqlite.py`, `bot_db.py` |
| B7. Admin dashboard: RAG settings (top_k, max_chars, temperature) | 1d | `bot_admin.py`, `bot_web.py` |
| B8. Admin dashboard: RAG activity viewer (last 50 queries + chunks) | 1d | `bot_admin.py`, `bot_web.py` |
| B9. Tests: T28 RRF correctness, T29 adaptive routing, T30 embedding pipeline | 1d | `test_voice_regression.py` |

**Dependencies:** Phase A must be complete. `sqlite-vec` installed on target for vector tests.

---

### Phase C: Document Management (3-5 days)

**Goal:** Sharing, duplicate detection, download, inline preview, upload restrictions.

| Task | Effort | Files |
|------|--------|-------|
| C1. Document sharing: `doc_sharing` table, share/unshare UI | 1d | `bot_documents.py`, `bot_db.py` |
| C2. Shared document retrieval: search across user's own + shared docs | 0.5d | `store_sqlite.py` |
| C3. Duplicate detection: SHA-256 hash at upload, warn if exists | 0.5d | `bot_documents.py` |
| C4. Document download: original file served from disk | 0.5d | `bot_web.py`, `bot_documents.py` |
| C5. Upload restrictions: max file size, max docs per user, DB size info | 0.5d | `bot_documents.py`, `bot_config.py` |
| C6. Parsing statistics: chunks created, parse time, text quality score | 0.5d | `bot_documents.py` |
| C7. Admin document management: view all users' docs, delete, toggle sharing | 1d | `bot_admin.py`, `bot_web.py` |
| C8. Tests: T31 sharing, T32 duplicate detection | 0.5d | `test_voice_regression.py` |

**Dependencies:** Phase B for embedding-aware sharing.

---

### Phase D: Remote RAG & MCP (2-3 days)

**Goal:** Connect to external knowledge sources via MCP protocol.

| Task | Effort | Files |
|------|--------|-------|
| D1. MCP client: connect to remote RAG server, call `search_knowledge()` tool | 1d | new: `src/core/bot_mcp_client.py` |
| D2. MCP server: expose local knowledge base as MCP tools | 0.5d | new: `src/core/bot_mcp_server.py` |
| D3. Integrate MCP results into RRF pipeline (additional rank list) | 0.5d | `bot_retrieval.py` |
| D4. Admin panel: MCP server configuration (URL, credentials) | 0.5d | `bot_admin.py`, `bot_web.py` |
| D5. Tests: T33 MCP round-trip (mock server) | 0.5d | `test_voice_regression.py` |

**Dependencies:** Phase B complete. MCP Python SDK installed.

---

### Phase E: Multimodal Preparation (Future, 5-7 days)

**Goal:** Extract and embed images/tables from PDFs. CLIP embeddings. Multimodal context.

| Task | Effort | Files |
|------|--------|-------|
| E1. PyMuPDF integration: extract images + tables from PDF | 1d | `bot_documents.py` |
| E2. Table-to-text conversion: structured table → Markdown | 0.5d | `bot_documents.py` |
| E3. Image description: send to vision LLM → text description → embed | 1d | `bot_embeddings.py`, `bot_llm.py` |
| E4. CLIP embeddings (optional): image → 768-dim vector | 1d | `bot_embeddings.py` |
| E5. Multimodal search: text + image results in RRF | 0.5d | `bot_retrieval.py` |
| E6. Admin panel: multimodal toggle, model selection | 0.5d | `bot_admin.py` |
| E7. Tests: T34 PDF image extraction, T35 multimodal retrieval | 0.5d | `test_voice_regression.py` |

**Dependencies:** Phase B + C. Only viable on Pi 5+ or server hardware.

---

### Implementation Timeline

```
Week 1:  Phase A — Memory System (3-5 days)
         ├── A1-A3: Core memory logic + DB schema
         └── A4-A7: Integration + UI + tests

Week 2:  Phase B — Enhanced RAG (5-7 days)
         ├── B1-B5: Embedding + retrieval + fusion
         └── B6-B9: Logging + admin + tests

Week 3:  Phase C — Document Management (3-5 days)
         ├── C1-C4: Sharing + download + dedup
         └── C5-C8: Restrictions + admin + tests

Week 4:  Phase D — Remote RAG (2-3 days)
         └── D1-D5: MCP client/server + integration

Future:  Phase E — Multimodal (5-7 days)
         └── E1-E7: Image/table extraction + CLIP

Eval:    AutoResearch Evaluation (ongoing, after Phase B)
         └── Automated overnight experiments per architecture
             (Pi SSH, AI X1 native, VPS SSH) — see extended-research §6b
```

---

## 8. Consolidated TODO List

### Priority 1 — Memory System (Phase A)

- [ ] Add `memory_summaries`, `memory_long`, `rag_settings` tables to `bot_db.py`
- [ ] Extend `store_base.py` Protocol with memory methods
- [ ] Implement memory methods in `store_sqlite.py`
- [ ] Create `src/core/bot_memory.py` — compaction logic (short→middle→long)
- [ ] Integrate memory tiers into `_handle_chat_message()` context assembly
- [ ] Profile → "🧠 Memory" UI (Telegram + Web): View summaries / Delete all / Toggle on-off
- [ ] Admin panel: Memory window sizes, retention policy
- [ ] Add memory-related i18n keys to `strings.json` (ru/en/de)
- [ ] Tests: T26 `memory_roundtrip`, T27 `memory_compaction`

### Priority 2 — Enhanced RAG (Phase B)

- [ ] Create `src/core/bot_embeddings.py` — ONNX MiniLM-L6-v2 loader with lazy load/unload
- [ ] Add embedding step to document upload pipeline (background thread)
- [ ] Create `src/core/bot_retrieval.py` — RRF fusion, adaptive routing, context assembly
- [ ] Refactor `_handle_chat_message()` to use `bot_retrieval.assemble_context()`
- [ ] Add `rag_log` table to `bot_db.py` + storage methods
- [ ] RAG logging: write chunk selections + timing on every retrieval
- [ ] Admin panel: RAG settings (top_k, max_chars, temperature, system_prompt)
- [ ] Admin panel: RAG activity log viewer (last 50 queries)
- [ ] Tests: T28 `rrf_fusion`, T29 `adaptive_routing`, T30 `embedding_pipeline`

### Priority 3 — Document Management (Phase C)

- [ ] `doc_sharing` table + storage methods
- [ ] Document sharing UI (Telegram + Web): share to all / specific users
- [ ] Shared-aware search: FTS5/vector queries include shared documents
- [ ] Duplicate detection at upload (SHA-256 hash comparison)
- [ ] Document download (original format) via Web UI + Telegram
- [ ] Upload restrictions: max 10 MB per file, 100 docs per user (configurable)
- [ ] Parsing statistics stored and shown to admin after upload
- [ ] Admin: view all documents, manage sharing, delete any document
- [ ] Upload size info shown to user before upload (Telegram + Web)
- [ ] Tests: T31 `doc_sharing`, T32 `duplicate_detection`

### Priority 4 — Remote RAG (Phase D)

- [ ] MCP client module: connect to external RAG server
- [ ] MCP server module: expose local knowledge as MCP tools
- [ ] Integrate remote results into RRF pipeline
- [ ] Admin: MCP server URL/credentials configuration
- [ ] Local + remote RAG combination toggle
- [ ] Test: T33 `mcp_roundtrip` (mock server)

### Priority 5 — Multimodal (Phase E, Future)

- [ ] PyMuPDF for image/table extraction from PDF
- [ ] Table → Markdown conversion
- [ ] Image → text description via vision LLM
- [ ] CLIP embeddings for image search (optional, Pi 5+ only)
- [ ] Multimodal results in RRF
- [ ] Admin: multimodal toggle
- [ ] Tests: T34, T35

### Priority 6 — Cross-Cutting

- [ ] Migrate `chat_history` reads to adapter (remove JSON fallback)
- [ ] All user data in database (notes, calendar, contacts, settings) — TODO §9.1
- [ ] RAG timeout monitoring and circuit breaker
- [ ] Document inline preview (txt, pdf rendered, md rendered) in Web UI
- [ ] Voice-controlled document upload ("загрузи документ") — TODO §12
- [ ] Activity logging for LLM context — TODO §11

---

## 9. Risk Analysis

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Embedding model OOM on Pi 3** | Memory pressure kills bot | Medium | Load/unload pattern. Pi 3: FTS5-only default. |
| **LLM summarization quality** for memory compaction | Lossy compression, lost context | Medium | Use best available LLM (cloud). Review summaries in admin. |
| **sqlite-vec unavailable** on target | No vector search | Low | Graceful fallback to FTS5-only. Capability detection at startup. |
| **Compaction latency** slows chat response | User sees delay | Low | Compaction runs async (background thread after response sent). |
| **RAG chunk irrelevance** (bad retrieval) | LLM hallucination from wrong context | Medium | Adaptive routing skips RAG for simple queries. RRF improves precision. Corrective RAG (future). |
| **MCP server unavailable** | Remote knowledge inaccessible | Low | Timeout + fallback to local-only. Circuit breaker pattern. |
| **Multimodal models too large** for Pi 5 | Cannot run CLIP + LLM simultaneously | Medium | Offload to cloud vision API. Pi 5: text-only embeddings. |
| **Schema migration breaks existing data** | Data loss | Low | Idempotent migrations. Backup before migrate. Foreign key constraints OFF during migration. |

---

## Appendix A: Library Dependency Matrix

| Library | Purpose | Pi 3 | Pi 5 | Server | Optional? |
|---------|---------|:----:|:----:|:------:|:---------:|
| `sqlite3` (stdlib) | FTS5 search, base storage | ✅ | ✅ | ✅ | Required |
| `sqlite-vec` | Vector similarity search | ⚠️ | ✅ | ✅ | Yes |
| `onnxruntime` | MiniLM-L6-v2 inference (no torch) | ⚠️ | ✅ | ✅ | Yes (for vectors) |
| `pdfminer.six` | PDF text extraction | ✅ | ✅ | ✅ | Yes (for PDF upload) |
| `python-docx` | DOCX text extraction | ✅ | ✅ | ✅ | Yes (for DOCX upload) |
| `PyMuPDF` | PDF image/table extraction | ⚠️ | ✅ | ✅ | Yes (multimodal) |
| `mcp` | Model Context Protocol client/server | ✅ | ✅ | ✅ | Yes (remote RAG) |
| `psutil` | Hardware capability detection | ✅ | ✅ | ✅ | Yes (auto-config) |
| `psycopg2` / `asyncpg` | PostgreSQL adapter | N/A | ✅ | ✅ | Yes (OpenClaw) |

## Appendix B: Configuration Reference

```bash
# Memory settings (bot.env)
STORE_HISTORY_WINDOW=50           # Short-term: messages in sliding window
MEMORY_SUMMARY_BATCH=15           # Messages per summary compaction
MEMORY_MIDDLE_MAX=10              # Max middle-term summaries
MEMORY_LONG_REFRESH_DAYS=7        # Long-term refresh interval

# RAG settings (bot.env)
RAG_TOP_K=5                       # Default chunks returned
RAG_MAX_CHARS=2000                # Max total RAG context characters
RAG_CHUNK_SIZE=512                # Characters per chunk at upload
RAG_CHUNK_OVERLAP=50              # Overlap between chunks
RAG_ENABLED=1                     # Global RAG toggle (0=off)

# Embedding settings (bot.env)
EMBED_MODEL=all-MiniLM-L6-v2     # Embedding model name
EMBED_KEEP_RESIDENT=0             # 1=keep model in memory (Pi 5+)
STORE_VECTORS=off                 # on=enable sqlite-vec vector search

# Document settings (bot.env)
DOC_MAX_SIZE_MB=10                # Max upload file size
DOC_MAX_PER_USER=100              # Max documents per user
DOC_SHARE_DEFAULT=private         # private|public

# MCP settings (bot.env)
MCP_REMOTE_URL=                   # External MCP RAG server URL (empty=disabled)
MCP_REMOTE_TOKEN=                 # Auth token for MCP server
MCP_TIMEOUT=10                    # MCP call timeout in seconds
```

## Appendix C: Relation to Existing TODO Items

| TODO Section | Covered by Phase | Notes |
|-------------|-----------------|-------|
| §2.1 Conversation Memory | Phase A | ✅ Already implemented (sliding window). Extend with 3-tier. |
| §3 LLM Provider + RAG docs | Phase B, C | Document sharing, admin management |
| §4 Content & Knowledge (all items) | Phase B, C, D | Timeout monitoring, settings, logging, restrictions |
| §4.1 Local RAG | Phase B | FTS5 + vector hybrid, configurable |
| §4.2 Remote RAG (MCP) | Phase D | MCP client/server |
| §9.1 User data in DB | Phase A (memory in DB) | Parallel work — notes/calendar/contacts migration separate |
| §10 Document upload | Phase B, C | Enhance existing `bot_documents.py` |
| §10.1 Memory tiers | Phase A | Core memory system |
| §11 Central control dashboard | Phase B (RAG settings) | Voice control is separate scope |
| §12 Voice input for text | N/A | Out of scope for this proposal |
| §13 Smart CRM | Phase C (document sharing) | CRM integration uses same knowledge base |

---

*This document consolidates all RAG, memory, and conversational context requirements from TODO.md §2, §3, §4, §9, §10, §11 and proposes a unified implementation architecture with 5 phased stages.*
