# AutoResearch Program — Remote KB RAG Optimization

## Objective

Maximize `rag_score` for the taris Remote Knowledge Base retrieval system.

```
rag_score = 0.5 * Recall@k + 0.3 * MRR + 0.2 * (1 - lat_p95_ms / 5000)
```

## Parameter Space

| Parameter | Type | Range | Default | Description |
|---|---|---|---|---|
| `top_k` | int | 3–10 | 5 | Number of chunks returned per query |
| `MCP_REMOTE_TOP_K` | int | 3–10 | 3 | Server-side retrieval limit |
| `embed_model` | str | see list | `multilingual-e5-small` | Embedding model for queries |
| `chunk_size` | int | 256–1024 | 512 | Document chunk size in tokens |
| `chunk_overlap` | int | 0–200 | 50 | Overlap between chunks |
| `rrf_k` | int | 20–120 | 60 | RRF fusion constant |
| `strategy` | str | remote/local/hybrid | remote | Retrieval strategy to evaluate |

## Evaluation Command

```bash
cd src/tests/autoresearch_kb
python3 evaluate.py --strategy remote --top-k 5
# Returns rag_score to stdout (JSON with --json flag)
```

## Data

- QA pairs: `src/tests/autoresearch_kb/qa_pairs.json` (20 questions, ru/en/de)
- Documents: `src/tests/autoresearch_kb/docs/` (add source PDFs/DOCX here)
- Ingest docs: `python3 prepare.py --ingest`

## Constraints

- `lat_p95_ms` must stay < 5000 ms (hard limit)
- `MCP_REMOTE_URL` must be set in environment (point to running N8N instance)
- Do NOT change `rag_score` formula weights (W_RECALL=0.5, W_MRR=0.3, W_LAT=0.2)

## AutoResearch Protocol

1. Start with default parameters and record baseline `rag_score`.
2. For each parameter in parameter space:
   a. Try 3 values: low / default / high
   b. Run `evaluate.py` and record `rag_score`
   c. Keep the value with highest `rag_score`
3. After single-parameter sweep: try top-2 best combinations.
4. Report final parameters and `rag_score` in a table.

## Success Criteria

| Grade | rag_score | Interpretation |
|---|---|---|
| 🔴 Poor | < 0.40 | Retrieval not usable |
| 🟡 Acceptable | 0.40–0.59 | Works but needs tuning |
| 🟢 Good | 0.60–0.74 | Production-ready |
| ⭐ Excellent | ≥ 0.75 | Optimal configuration |

## Files Modified by AutoResearch

- `N8N_KB_WEBHOOK_INGEST` payload: `KB_CHUNK_SIZE`, `KB_CHUNK_OVERLAP` (N8N Variables)
- `bot.env`: `MCP_REMOTE_TOP_K`
- N8N workflow `KB - MCP Server.json`: `rrf_k` constant in the hybrid search SQL

## Notes

- `qa_pairs.json` `relevant_doc_ids` must be populated after ingesting documents.
  Run `prepare.py --ingest` then update the JSON with returned `doc_id` values.
- Questions without `relevant_doc_ids` are excluded from Recall/MRR computation.
- The benchmark is designed to run in < 5 minutes for 20 questions.
