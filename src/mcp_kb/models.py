"""
models.py — Pydantic client-side models for MCP KB tool responses.

Architecture (v0.3): N8N MCP Server Trigger is the server. This module
holds response models used in bot_mcp_client.py to parse tool call results.
The FastAPI server files (main.py, auth.py, db.py) have been removed.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ─── Health ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    db_ok: bool
    db_name: str = "taris_kb"


# ─── Tools / list ─────────────────────────────────────────────────────────────

class ToolParam(BaseModel):
    name: str
    type: str
    required: bool
    description: str


class ToolDef(BaseModel):
    name: str
    description: str
    phase: str         # e.g. "1", "2", "3" — which phase implements it
    available: bool    # True once the phase is complete
    params: list[ToolParam] = Field(default_factory=list)


class ToolsListResponse(BaseModel):
    tools: list[ToolDef]
    service: str = "taris-mcp-kb"
    mode: str = "n8n"


# ─── Search ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    chat_id: int
    top_k: int = 5
    mode: Optional[str] = None          # "n8n" | "google" | None = use server default
    filters: Optional[dict[str, Any]] = None


class ChunkResult(BaseModel):
    doc_id: str
    chunk_id: int
    section: Optional[str] = None
    chunk_text: str
    score: float
    source_uri: Optional[str] = None


class SearchResponse(BaseModel):
    chunks: list[ChunkResult]
    latency_ms: int
    mode: str


# ─── Ingest ───────────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    doc_id: str
    title: str
    n_chunks: int
    n_embedded: int
    parse_time_ms: int


# ─── Documents ────────────────────────────────────────────────────────────────

class DocumentMeta(BaseModel):
    doc_id: str
    title: str
    mime: Optional[str]
    n_chunks: int
    created_at: str


class DocumentsListResponse(BaseModel):
    documents: list[DocumentMeta]
    total: int


class DeleteDocumentResponse(BaseModel):
    ok: bool
    doc_id: str


# ─── Memory ───────────────────────────────────────────────────────────────────

class MemoryGetRequest(BaseModel):
    chat_id: int
    tier: str = "short"          # short | middle | long


class MemoryRow(BaseModel):
    seq: int
    role: str
    content: str
    created_at: str


class MemoryGetResponse(BaseModel):
    chat_id: int
    tier: str
    rows: list[MemoryRow]


class MemoryAppendRequest(BaseModel):
    chat_id: int
    role: str          # user | assistant | system
    content: str


class MemoryAppendResponse(BaseModel):
    ok: bool
    compacted: bool = False    # True if compaction was triggered


class MemoryClearRequest(BaseModel):
    chat_id: int
    tier: Optional[str] = None    # None = clear all tiers


class MemoryClearResponse(BaseModel):
    ok: bool
    rows_deleted: int
