# Taris Self-Learning & Auto-Research — Architecture Variants

**Version:** 1.0 · **Date:** 2026-04-10  
**Author:** Architecture Proposal · **Status:** Concept  
**Scope:** Self-learning, auto-research, and autonomous optimization for Taris+OpenClaw  
**References:** `concept/taris-n8n-crm-integration.md` §4C · `concept/rag-memory-extended-research.md` §6b (AutoResearch)  
**Parent:** [Taris+N8N+CRM Integration Concept](taris-n8n-crm-integration.md)

---

## 1. Executive Summary

This document proposes **three implementation variants** for making Taris a self-learning, self-optimizing system. Each variant builds on the existing Taris infrastructure (Ollama, PostgreSQL+pgvector, pipeline_logger, N8N) and draws from 19 researched frameworks including Reflexion, Agentic RAG, Self-Refine, LangGraph, Voyager, DSPy, Constitutional AI, STORM, and Karpathy's AutoResearch.

| Variant | Name | Complexity | Timeline | Key Idea |
|---------|------|-----------|----------|----------|
| **A** | Pragmatic Self-Improvement | ⭐⭐ Low | 4-5 weeks | Feedback loops + quality routing + performance monitoring |
| **B** | Agentic Orchestration | ⭐⭐⭐ Medium | 8-10 weeks | Multi-agent with Reflexion + tool-use + Constitutional AI |
| **C** | Full Autonomous Research | ⭐⭐⭐⭐⭐ High | 16+ weeks | Voyager-style skill discovery + STORM research + DSPy prompt optimization |

**Recommendation:** Start with **Variant A** (immediate 30-40% quality improvement), evolve to **Variant B** components as needed, cherry-pick from **Variant C** for long-term vision. This is a **telescoping roadmap** — each variant is a superset of the previous one.

---

## 2. Research Summary — 19 Frameworks Analyzed

### 2.1 Framework Catalog

| # | Framework | What It Does | Feasibility for Taris | Ollama Support | Solo Dev Time |
|---|-----------|-------------|----------------------|----------------|---------------|
| 1 | **Agentic RAG** | Self-correcting retrieval: grade → rewrite → retry | ⭐⭐⭐⭐⭐ Excellent | ✅ | 2 hours |
| 2 | **Self-Refine** | Iterative critique + refinement without human feedback | ⭐⭐⭐⭐⭐ Excellent | ✅ | 1 hour |
| 3 | **Constitutional AI** | Self-critique against defined principles → alignment | ⭐⭐⭐⭐⭐ Excellent | ✅ | 2 hours |
| 4 | **Reflexion** | Agent reflects on failures → stores reflections → improves | ⭐⭐⭐⭐⭐ Excellent | ✅ | 1-2 days |
| 5 | **RLHF-Lite** | Lightweight human preference (👍/👎) → few-shot retrieval | ⭐⭐⭐⭐ Good | ✅ | 1 day |
| 6 | **Online Learning** | Continuous metric monitoring → A/B testing → auto-deploy | ⭐⭐⭐⭐ Good | ✅ | 1-2 days |
| 7 | **LangGraph** | Stateful agent orchestration as directed graph | ⭐⭐⭐⭐⭐ Excellent | ✅ | 1 day |
| 8 | **CrewAI** | Multi-agent with specialized roles + delegation | ⭐⭐⭐⭐ Good | ✅ | 1-2 days |
| 9 | **Self-Play** | Multiple solutions → pairwise evaluation → extract principles | ⭐⭐⭐⭐ Good | ✅ | 1 day |
| 10 | **Multi-Agent Debate** | Pro/con agents → judge synthesizes balanced answer | ⭐⭐⭐ Medium | ✅ | 1-2 days |
| 11 | **GPT-Researcher** | Autonomous web research with source synthesis | ⭐⭐⭐⭐ Good | ✅ | 4 hours |
| 12 | **DSPy** | Programmatic prompt optimization (prompts as weights) | ⭐⭐⭐ Medium | ✅ | 1-2 days |
| 13 | **LATS** | Language Agent Tree Search — multi-path reasoning | ⭐⭐⭐ Medium | ✅ | 2-3 days |
| 14 | **STORM** (Stanford) | Automated research paper generation pipeline | ⭐⭐⭐⭐ Good | ✅ | 1 day |
| 15 | **Voyager** (NVIDIA) | Lifelong learning: skill library + curriculum generator | ⭐⭐⭐⭐ Good | ✅ | 1+ week |
| 16 | **AutoGen** (MS) | Multi-agent conversation loops with human-in-the-loop | ⭐⭐⭐ Medium | ✅ | 2-3 days |
| 17 | **Gorilla** | Fine-tuned LLM for API calling (requires training) | ⭐⭐ Low | ✅ (custom) | 1-2 weeks |
| 18 | **ToolLLM** | Tree-search tool learning framework | ⭐⭐⭐ Medium | ✅ | 3-5 days |
| 19 | **AutoResearch** (Karpathy) | Autonomous agent-driven RAG evaluation & optimization | ⭐⭐⭐⭐ Good | ✅ | 2-3 days |

### 2.2 Key Architectural Patterns Discovered

| Pattern | Description | Used In | Taris Applicability |
|---------|-------------|---------|---------------------|
| **ReAct Loop** | Thought → Action → Observation → Repeat | Reflexion, LangGraph, CrewAI | Core pattern for tool-use agentic loop |
| **Skill Library** | Persistent storage of learned behaviors + retrieval | Voyager | Long-term knowledge accumulation |
| **Reflection Store** | Agent critiques → stored as embeddings → retrieved for similar queries | Reflexion | Self-improvement without retraining |
| **Multi-Armed Bandit** | Explore/exploit model selection based on quality scores | Online Learning, Martian/Not Diamond | Quality-based LLM routing |
| **Constitutional Critique** | Self-check against principles before output | Constitutional AI | Safety and alignment layer |
| **Best-of-N Sampling** | Generate N candidates → score → pick best | Self-Play, Self-Refine | Response quality improvement |
| **Query Rewriting** | Failed retrieval → LLM rewrites query → retry | Agentic RAG | RAG self-correction |
| **Bayesian A/B Testing** | Small-sample hypothesis testing with beta-binomial priors | Online Learning | Prompt/model comparison with few samples |
| **Exponential Moving Average** | `α * new + (1-α) * old` for scoring without full history | Quality routing | Real-time model quality tracking |

### 2.3 What Already Exists in Taris (9 Building Blocks)

| # | Component | File | Self-Learning Potential |
|---|-----------|------|----------------------|
| 1 | Pipeline logger | `pipeline_logger.py` | STT/LLM/TTS latency per request → performance optimization |
| 2 | RAG activity log | `rag_log` table | Query type, chunks, strategy → retrieval optimization |
| 3 | LLM call trace | `llm_calls` table | Provider, model, response_ok → quality routing |
| 4 | Tiered memory | `conversation_summaries` | Short→mid→long summaries → user preference extraction |
| 5 | Per-function routing | `llm_per_func.json` | Manual overrides → foundation for auto-routing |
| 6 | Voice opts per user | `voice_opts` table | 12+ flags → personalized pipeline tuning |
| 7 | Error protocols | `error_protocols/` dir | Structured reports → error pattern mining |
| 8 | Admin model picker | `bot_admin.py` | Runtime model switching → automated via quality signals |
| 9 | MCP circuit breaker | `bot_mcp_client.py` | Self-healing connections → resilience pattern |

**Key gap:** Data infrastructure exists, but there is **no closed-loop feedback** connecting observations → analysis → actions.

---

## 3. Variant A: Pragmatic Self-Improvement

> **Philosophy:** Maximum impact with minimum complexity. No external frameworks. Pure Python + PostgreSQL.
> **Target:** 30-40% quality improvement in 4-5 weeks.

### 3.1 Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    VARIANT A: PRAGMATIC                             │
│                                                                    │
│  USER REQUEST                                                      │
│       ↓                                                            │
│  ┌────────────┐    ┌──────────────┐    ┌────────────────┐         │
│  │ Agentic RAG│───▶│ Quality      │───▶│ Self-Refine    │         │
│  │ (retrieve  │    │ Router       │    │ (critique +    │         │
│  │  + grade   │    │ (bandit      │    │  refine loop)  │         │
│  │  + rewrite)│    │  selection)  │    │                │         │
│  └────────────┘    └──────────────┘    └────────┬───────┘         │
│                                                  ↓                 │
│                                         ┌────────────────┐         │
│                                         │ RESPONSE       │         │
│                                         │ + [👍] [👎]    │         │
│                                         └────────┬───────┘         │
│                                                  ↓                 │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              FEEDBACK & LEARNING LAYER                       │   │
│  │                                                             │   │
│  │  response_feedback ──▶ bot_optimizer.py ──▶ llm_per_func   │   │
│  │  rag_chunk_scores  ──▶ rag_learner.py  ──▶ RRF weights     │   │
│  │  perf_baselines    ──▶ perf_monitor.py ──▶ model switch    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 Components

| Component | Framework Basis | What It Does | New Code |
|-----------|----------------|-------------|----------|
| **Agentic RAG** | Agentic RAG pattern | Grade retrieved chunks → rewrite query if poor → retry | ~150 lines in `bot_rag.py` |
| **Self-Refine** | Self-Refine | Generate → critique → refine (2 iterations max) | ~80 lines in `bot_llm.py` |
| **Quality Router** | Multi-Armed Bandit / Online Learning | Select model based on EMA quality score + 5% exploration | ~120 lines `bot_optimizer.py` |
| **Feedback Collector** | RLHF-Lite | 👍/👎 inline buttons → `response_feedback` table | ~100 lines in handlers |
| **Performance Monitor** | Online Learning | Hourly p95 stats → auto-downgrade slow providers | ~100 lines `bot_perf_monitor.py` |
| **RAG Learner** | Agentic RAG feedback | Chunk scores → RRF boost factors | ~80 lines `bot_rag_learner.py` |

**Total new code:** ~630 lines across 4 new files + extensions to 3 existing files.

### 3.3 Data Flow — Feedback Loop

```python
# 1. Collect feedback (in telegram_menu_bot.py)
# Under every LLM response: inline [👍] [👎] buttons
# Callback: "feedback_pos:<call_id>" / "feedback_neg:<call_id>"

# 2. Store feedback (new: store method)
store.save_response_feedback(chat_id, call_id, provider, model, use_case, rating)

# 3. Analyze (new: bot_optimizer.py — runs nightly or every N feedbacks)
def optimize_provider_routing():
    feedback = store.get_recent_feedback(days=7)
    for use_case in ["chat", "system", "rag", "calendar"]:
        scores = {}
        for provider in feedback.providers:
            subset = feedback.filter(use_case=use_case, provider=provider)
            if len(subset) >= 10:  # minimum sample size
                scores[provider] = subset.avg_rating
        if scores:
            best = max(scores, key=scores.get)
            current = get_per_func_provider(use_case)
            if best != current and scores[best] > scores.get(current, 0) + 0.3:
                set_per_func_provider(use_case, best)
                log_optimization("quality", f"{use_case}: {current} → {best}")

# 4. Apply: next request uses updated routing automatically
```

### 3.4 Self-Refine Implementation

```python
# In bot_llm.py — wraps ask_llm() for high-value responses
def ask_llm_refined(prompt: str, max_iterations: int = 2, **kwargs) -> str:
    """Generate → Critique → Refine loop. No external feedback needed."""
    response = ask_llm(prompt, **kwargs)
    
    for i in range(max_iterations):
        critique = ask_llm(
            f"Critically evaluate this response. List specific problems:\n\n"
            f"Question: {prompt}\nResponse: {response}\n\n"
            f"List problems (or say NONE if response is good):",
            timeout=15
        )
        if "NONE" in critique.upper() or len(critique.strip()) < 20:
            break  # Response is good enough
        
        response = ask_llm(
            f"Improve this response based on critique:\n\n"
            f"Original question: {prompt}\n"
            f"Current response: {response}\n"
            f"Critique: {critique}\n\n"
            f"Write an improved response:",
            timeout=20
        )
    
    return response
```

### 3.5 Agentic RAG Implementation

```python
# In bot_rag.py — self-correcting retrieval
def retrieve_with_correction(query: str, chat_id: int, max_retries: int = 2) -> list:
    """Retrieve → Grade → Rewrite → Retry if poor relevance."""
    for attempt in range(max_retries + 1):
        chunks = retrieve_chunks(query, chat_id)
        
        if not chunks:
            break
        
        # Grade relevance using lightweight LLM call
        grade_prompt = (
            f"Rate relevance 1-5. Query: '{query}'\n"
            f"Retrieved text: '{chunks[0].text[:200]}'\n"
            f"Reply with just a number 1-5:"
        )
        grade = ask_llm(grade_prompt, timeout=5)
        score = int(grade.strip()[0]) if grade.strip()[0].isdigit() else 3
        
        if score >= 3:
            return chunks  # Good enough
        
        if attempt < max_retries:
            # Rewrite query for better retrieval
            rewrite_prompt = (
                f"The search query '{query}' returned irrelevant results. "
                f"Rewrite it to better find the answer. Reply with just the new query:"
            )
            query = ask_llm(rewrite_prompt, timeout=5).strip()
    
    return chunks
```

### 3.6 Database Schema (Variant A)

```sql
-- Feedback collection
CREATE TABLE response_feedback (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    call_id TEXT,
    provider TEXT,
    model TEXT,
    use_case TEXT DEFAULT 'chat',
    rating SMALLINT CHECK (rating BETWEEN 1 AND 5),
    implicit BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- RAG chunk relevance
CREATE TABLE rag_chunk_scores (
    doc_id TEXT NOT NULL,
    chunk_hash TEXT NOT NULL,
    relevance_sum INTEGER DEFAULT 0,
    query_count INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (doc_id, chunk_hash)
);

-- Performance baselines
CREATE TABLE performance_baselines (
    stage TEXT NOT NULL,
    provider TEXT NOT NULL,
    p50_ms REAL,
    p95_ms REAL,
    error_rate REAL,
    sample_count INTEGER,
    measured_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (stage, provider)
);

-- Optimization audit trail
CREATE TABLE optimization_log (
    id SERIAL PRIMARY KEY,
    loop_name TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 3.7 Variant A Roadmap

| Phase | Scope | Effort | Dependencies |
|-------|-------|--------|--------------|
| **A1** | Feedback buttons (👍/👎) + `response_feedback` table | 3 days | None |
| **A2** | Self-Refine wrapper (`ask_llm_refined`) | 1 day | None |
| **A3** | Agentic RAG (grade + rewrite + retry) | 2 days | None |
| **A4** | Performance monitor (hourly stats + degradation alerts) | 3 days | A1 |
| **A5** | Quality router (`bot_optimizer.py` + bandit selection) | 3 days | A1, A4 |
| **A6** | RAG learner (chunk scores + RRF boost) | 2 days | A1, A3 |
| **A7** | Admin dashboard (learning metrics in Web UI) | 2 days | A4, A5 |

**Total: ~4-5 weeks, ~630 lines of new code.**

---

## 4. Variant B: Agentic Orchestration

> **Philosophy:** Structured multi-agent system with self-reflection, tool-use, and constitutional safety.
> **Target:** 50-60% quality improvement + autonomous task execution. 8-10 weeks.
> **Builds on:** All of Variant A + adds agentic capabilities.

### 4.1 Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    VARIANT B: AGENTIC                                │
│                                                                      │
│  USER REQUEST                                                        │
│       ↓                                                              │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │              AGENT ORCHESTRATOR (LangGraph-style)            │     │
│  │                                                             │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  │     │
│  │  │ Intent   │─▶│ Context  │─▶│ Agent    │─▶│ Validate  │  │     │
│  │  │ Classify │  │ Retrieve │  │ Execute  │  │ + Refine  │  │     │
│  │  │          │  │ (Agentic │  │ (ReAct   │  │ (Constit. │  │     │
│  │  │          │  │  RAG)    │  │  Loop)   │  │  AI check)│  │     │
│  │  └──────────┘  └──────────┘  └──────────┘  └───────────┘  │     │
│  │       │                            │              │         │     │
│  │       ▼                            ▼              ▼         │     │
│  │  ┌──────────────────────────────────────────────────────┐   │     │
│  │  │  TOOL REGISTRY                                       │   │     │
│  │  │  • crm_search(query) → contacts                      │   │     │
│  │  │  • n8n_trigger(workflow, payload) → execution_id      │   │     │
│  │  │  • calendar_add(event) → event_id                     │   │     │
│  │  │  • rag_search(query) → chunks                         │   │     │
│  │  │  • send_message(chat_id, text) → ok                   │   │     │
│  │  └──────────────────────────────────────────────────────┘   │     │
│  └─────────────────────────────────────────────────────────────┘     │
│       ↓                                                              │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │              REFLECTION STORE (Reflexion pattern)            │     │
│  │                                                             │     │
│  │  On failure/low-quality:                                    │     │
│  │   → Generate reflection: "What went wrong? How to improve?" │     │
│  │   → Store as pgvector embedding                             │     │
│  │   → Retrieve on similar future queries                      │     │
│  │                                                             │     │
│  │  agent_reflections table:                                   │     │
│  │   (query_embedding, reflection_text, success, created_at)   │     │
│  └─────────────────────────────────────────────────────────────┘     │
│       ↓                                                              │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │              VARIANT A FEEDBACK LAYER (inherited)            │     │
│  │  response_feedback + quality_router + perf_monitor + ...    │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 New Components (beyond Variant A)

| Component | Framework Basis | What It Does | New Code |
|-----------|----------------|-------------|----------|
| **Agent Orchestrator** | LangGraph pattern | State machine: Intent→Context→Execute→Validate | ~300 lines `bot_agent.py` |
| **ReAct Tool Loop** | ReAct / Ollama tool-use | Thought→Action→Observation→Repeat (max 10 iter) | ~200 lines in `bot_agent.py` |
| **Tool Registry** | MCP / OpenClaw skills | Declare tools with schemas → LLM selects + calls | ~150 lines `bot_tools.py` |
| **Constitutional Check** | Constitutional AI | Self-critique against 5-6 principles before output | ~80 lines in `bot_agent.py` |
| **Reflection Store** | Reflexion | Store failure critiques as embeddings → retrieve later | ~120 lines `bot_reflections.py` |
| **Specialized Agents** | CrewAI pattern | CRM Agent, Calendar Agent, Research Agent | ~200 lines `bot_crew.py` |

**Total new code (Variant B only):** ~1050 lines across 4 new files.
**Total with Variant A:** ~1680 lines.

### 4.3 ReAct Tool Loop (Ollama native tool-use)

```python
# bot_agent.py — Agentic execution with Ollama tool calling
def agent_execute(query: str, chat_id: int, tools: list, max_iter: int = 10) -> str:
    """ReAct loop: LLM reasons, selects tools, observes results."""
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": query}
    ]
    
    # Retrieve relevant reflections from past failures
    reflections = retrieve_reflections(query, k=3)
    if reflections:
        messages[0]["content"] += f"\n\nLessons from past mistakes:\n{reflections}"
    
    for i in range(max_iter):
        response = ollama_chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=[t.schema for t in tools],  # Ollama native tool-use
            options={"temperature": 0.3}
        )
        
        msg = response["message"]
        messages.append(msg)
        
        # Check for tool calls
        if msg.get("tool_calls"):
            for call in msg["tool_calls"]:
                result = execute_tool(call["function"]["name"],
                                       call["function"]["arguments"], tools)
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result)
                })
        else:
            # No tool call = final answer
            answer = msg["content"]
            
            # Constitutional AI check
            if not constitutional_check(query, answer):
                answer = refine_for_alignment(query, answer)
            
            return answer
    
    return "Could not complete the task within iteration limit."
```

### 4.4 Reflexion Store

```python
# bot_reflections.py — Learn from failures
def generate_and_store_reflection(query: str, response: str,
                                    feedback: str, success: bool):
    """On failure: generate reflection, embed, store for future retrieval."""
    if success:
        return  # Only learn from failures
    
    reflection = ask_llm(
        f"A user asked: '{query}'\n"
        f"The system responded: '{response}'\n"
        f"User feedback: '{feedback}'\n\n"
        f"What went wrong? What should the system do differently next time? "
        f"Be specific and actionable.",
        timeout=15
    )
    
    embedding = compute_embedding(f"{query} {reflection}")
    store.save_reflection(query, reflection, embedding, success)

def retrieve_reflections(query: str, k: int = 3) -> str:
    """Retrieve past reflections relevant to current query."""
    embedding = compute_embedding(query)
    reflections = store.search_reflections_by_embedding(embedding, limit=k)
    if not reflections:
        return ""
    return "\n".join(f"- {r.reflection_text}" for r in reflections)
```

### 4.5 Constitutional AI Check

```python
# Taris Constitution — principles for self-alignment
TARIS_CONSTITUTION = [
    "Be helpful and answer the user's question directly.",
    "Be honest — if you don't know, say so. Never fabricate information.",
    "Respect privacy — never reveal personal data of other users.",
    "Be professional and appropriate for a business context.",
    "Prefer concise answers unless the user asks for detail.",
    "When referencing data (contacts, calendar), cite the source."
]

def constitutional_check(query: str, response: str) -> bool:
    """Check response against constitution. Returns True if aligned."""
    check_prompt = (
        f"Check if this response follows ALL these principles:\n"
        + "\n".join(f"{i+1}. {p}" for i, p in enumerate(TARIS_CONSTITUTION))
        + f"\n\nUser query: {query}\nResponse: {response}\n\n"
        f"Reply YES if all principles are followed, or NO with the violated principle number."
    )
    result = ask_llm(check_prompt, timeout=10)
    return result.strip().upper().startswith("YES")
```

### 4.6 Additional Database Schema (Variant B)

```sql
-- Reflexion store
CREATE TABLE agent_reflections (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    query_embedding VECTOR(384),
    reflection_text TEXT NOT NULL,
    success BOOLEAN DEFAULT FALSE,
    use_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON agent_reflections USING ivfflat (query_embedding vector_cosine_ops);

-- Tool execution log (for learning which tools work best)
CREATE TABLE tool_executions (
    id SERIAL PRIMARY KEY,
    tool_name TEXT NOT NULL,
    args JSONB,
    result_preview TEXT,
    success BOOLEAN,
    latency_ms INTEGER,
    agent_session TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Constitutional violations log
CREATE TABLE constitutional_violations (
    id SERIAL PRIMARY KEY,
    query TEXT,
    response TEXT,
    violated_principle INTEGER,
    auto_corrected BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.7 Variant B Roadmap (builds on Variant A)

| Phase | Scope | Effort | Dependencies |
|-------|-------|--------|--------------|
| **B1** | Tool Registry + schemas for existing features | 3 days | A-complete |
| **B2** | ReAct loop with Ollama native tool-use | 4 days | B1 |
| **B3** | Agent Orchestrator (state machine: intent→context→execute→validate) | 3 days | B2 |
| **B4** | Constitutional AI check layer | 2 days | B2 |
| **B5** | Reflexion store (generate + embed + retrieve reflections) | 3 days | B2, B4 |
| **B6** | Specialized agents (CRM Agent, Calendar Agent) | 4 days | B3 |
| **B7** | Tool execution analytics + auto-routing | 3 days | B2, A5 |

**Total Variant B only: ~5-6 weeks. Total A+B: ~10 weeks.**

---

## 5. Variant C: Full Autonomous Research System

> **Philosophy:** System that autonomously discovers new skills, researches topics, optimizes its own prompts, and improves without human intervention.
> **Target:** Autonomous self-improvement cycle. 16+ weeks.
> **Builds on:** Variant A + Variant B + adds autonomous components.

### 5.1 Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    VARIANT C: AUTONOMOUS                                  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    AUTONOMOUS RESEARCH ENGINE                       │  │
│  │                    (runs in background, periodic)                   │  │
│  │                                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐   │  │
│  │  │ STORM-lite   │  │ DSPy-lite    │  │ Voyager-lite          │   │  │
│  │  │ Research     │  │ Prompt       │  │ Skill                 │   │  │
│  │  │              │  │ Optimizer    │  │ Discovery             │   │  │
│  │  │ • Web search │  │              │  │                       │   │  │
│  │  │ • RAG query  │  │ • Collect    │  │ • Curriculum gen.     │   │  │
│  │  │ • Source     │  │   examples   │  │ • Try new tool combos │   │  │
│  │  │   synthesis  │  │ • Propose    │  │ • Evaluate outcomes   │   │  │
│  │  │ • Report to  │  │   variants   │  │ • Store successful    │   │  │
│  │  │   knowledge  │  │ • A/B test   │  │   skills in library   │   │  │
│  │  │   base       │  │ • Adopt best │  │ • Curriculum++        │   │  │
│  │  └──────────────┘  └──────────────┘  └───────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│       ↓                       ↓                       ↓                  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  VARIANT B AGENTIC LAYER (inherited)                               │  │
│  │  Agent Orchestrator + ReAct + Tools + Constitutional AI + Reflect  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│       ↓                                                                  │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  VARIANT A FEEDBACK LAYER (inherited)                              │  │
│  │  Feedback + Quality Router + Perf Monitor + RAG Learner            │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 5.2 New Components (beyond Variant B)

| Component | Framework Basis | What It Does | New Code |
|-----------|----------------|-------------|----------|
| **STORM-lite Research** | STORM (Stanford) | Autonomous topic research → RAG knowledge base | ~250 lines `bot_researcher.py` |
| **DSPy-lite Optimizer** | DSPy + A/B testing | Collect examples → propose prompt variants → A/B test → adopt | ~200 lines `bot_prompt_optimizer.py` |
| **Voyager-lite Skills** | Voyager (NVIDIA) | Discover tool combinations → store as skills → retrieve | ~300 lines `bot_skill_library.py` |
| **Curriculum Generator** | Voyager | Propose progressively harder tasks → test agent capability | ~150 lines in `bot_skill_library.py` |
| **Cost Optimizer** | Online Learning | Track token spend → budget-aware routing → monthly reports | ~120 lines `bot_cost_optimizer.py` |
| **Self-Play Evaluator** | Self-Play | Generate N answers → pairwise judge → extract principles | ~150 lines `bot_self_play.py` |

**Total new code (Variant C only):** ~1170 lines across 5 new files.
**Total A+B+C:** ~2850 lines.

### 5.3 STORM-lite Research Engine

```python
# bot_researcher.py — Autonomous knowledge acquisition
class TarisResearcher:
    """Periodically research topics relevant to user queries."""
    
    def research_topic(self, topic: str, max_sources: int = 5) -> str:
        """Multi-step research: query → gather → synthesize → store."""
        # Step 1: Generate research questions
        questions = ask_llm(
            f"Generate 3 specific research questions about: {topic}\n"
            f"Format: one question per line.",
            timeout=10
        ).strip().split("\n")
        
        # Step 2: Gather information from existing RAG + web search
        findings = []
        for q in questions[:3]:
            # Try local RAG first
            chunks = retrieve_with_correction(q, chat_id=0)
            if chunks:
                findings.append(f"[Local KB] {chunks[0].text[:500]}")
            
            # Try web search if available (via N8N workflow)
            if N8N_ENABLED:
                web_result = trigger_workflow("web-search", {"query": q})
                if web_result.get("data"):
                    findings.append(f"[Web] {web_result['data'][:500]}")
        
        # Step 3: Synthesize into knowledge document
        synthesis = ask_llm(
            f"Topic: {topic}\n\n"
            f"Research findings:\n" + "\n".join(findings) + "\n\n"
            f"Write a concise, factual summary (200-400 words). "
            f"Cite sources where possible.",
            timeout=30
        )
        
        # Step 4: Store in RAG knowledge base
        store.add_document(
            title=f"Research: {topic}",
            content=synthesis,
            source="auto_research",
            metadata={"auto_generated": True, "topic": topic}
        )
        
        return synthesis
    
    def identify_knowledge_gaps(self) -> list[str]:
        """Analyze recent queries with poor RAG results → suggest research topics."""
        poor_queries = store.get_queries_with_low_relevance(days=7, min_count=3)
        
        topics = ask_llm(
            f"These user queries had poor knowledge base results:\n"
            + "\n".join(f"- {q}" for q in poor_queries[:10]) + "\n\n"
            f"What 3 topics should be researched to fill these gaps?\n"
            f"Format: one topic per line.",
            timeout=15
        ).strip().split("\n")
        
        return topics[:3]
```

### 5.4 DSPy-lite Prompt Optimizer

```python
# bot_prompt_optimizer.py — A/B test system prompts autonomously
class PromptOptimizer:
    """Optimize system prompts using feedback + LLM analysis."""
    
    def optimize_cycle(self):
        """Run every 100 conversations. Propose → Test → Adopt."""
        # Step 1: Collect best and worst responses
        best = store.get_top_rated_responses(n=10, days=14)
        worst = store.get_bottom_rated_responses(n=10, days=14)
        
        if len(best) < 5 or len(worst) < 5:
            return  # Not enough data
        
        current_prompt = get_system_prompt()
        
        # Step 2: LLM analyzes patterns
        analysis = ask_llm(
            f"Current system prompt:\n{current_prompt}\n\n"
            f"Best responses (user rated 5/5):\n"
            + "\n".join(f"Q: {r.query}\nA: {r.response}" for r in best[:5]) +
            f"\n\nWorst responses (user rated 1-2/5):\n"
            + "\n".join(f"Q: {r.query}\nA: {r.response}" for r in worst[:5]) +
            f"\n\nAnalyze: What patterns make good responses? What causes bad ones? "
            f"Propose an improved system prompt.",
            timeout=30
        )
        
        # Step 3: Extract proposed prompt
        new_prompt = extract_prompt_from_analysis(analysis)
        
        # Step 4: Start A/B test
        store.create_ab_experiment(
            name=f"prompt_opt_{datetime.now():%Y%m%d}",
            variant_a=current_prompt,
            variant_b=new_prompt,
            traffic_split=0.5
        )
    
    def check_experiment_results(self):
        """After 50+ ratings per variant, decide winner."""
        active = store.get_active_experiments()
        for exp in active:
            a_ratings = store.get_experiment_ratings(exp.id, variant="A")
            b_ratings = store.get_experiment_ratings(exp.id, variant="B")
            
            if len(a_ratings) >= 30 and len(b_ratings) >= 30:
                a_avg = sum(a_ratings) / len(a_ratings)
                b_avg = sum(b_ratings) / len(b_ratings)
                
                if b_avg > a_avg + 0.2:  # Significant improvement
                    adopt_prompt(exp.variant_b)
                    log_optimization("prompt", f"Adopted new prompt (Δ={b_avg-a_avg:.2f})")
                else:
                    log_optimization("prompt", f"Kept current prompt (Δ={b_avg-a_avg:.2f})")
                
                store.close_experiment(exp.id)
```

### 5.5 Voyager-lite Skill Library

```python
# bot_skill_library.py — Discover and store reusable tool chains
class SkillLibrary:
    """Persistent storage of learned agent behaviors."""
    
    def discover_skill(self, task: str, tool_chain: list[dict], outcome: dict):
        """After successful multi-tool execution, store as reusable skill."""
        skill_description = ask_llm(
            f"Task: {task}\n"
            f"Tools used: {json.dumps(tool_chain)}\n"
            f"Outcome: {json.dumps(outcome)}\n\n"
            f"Describe this as a reusable skill in one sentence.",
            timeout=10
        )
        
        embedding = compute_embedding(skill_description)
        store.save_skill(
            description=skill_description,
            tool_chain=tool_chain,
            embedding=embedding,
            success_rate=1.0,  # Initial; updated with feedback
            use_count=1
        )
    
    def retrieve_skill(self, task: str, k: int = 3) -> list:
        """Find skills relevant to current task."""
        embedding = compute_embedding(task)
        return store.search_skills_by_embedding(embedding, limit=k)
    
    def generate_curriculum(self) -> list[str]:
        """Propose progressively harder tasks for self-testing."""
        existing_skills = store.get_all_skills(limit=20)
        skill_names = [s.description for s in existing_skills]
        
        curriculum = ask_llm(
            f"The system has learned these skills:\n"
            + "\n".join(f"- {s}" for s in skill_names) +
            f"\n\nPropose 3 new, slightly harder tasks the system should try. "
            f"Each should combine existing skills or require a new tool.",
            timeout=15
        )
        return curriculum.strip().split("\n")[:3]
```

### 5.6 Additional Database Schema (Variant C)

```sql
-- Skill library
CREATE TABLE agent_skills (
    id SERIAL PRIMARY KEY,
    description TEXT NOT NULL,
    description_embedding VECTOR(384),
    tool_chain JSONB NOT NULL,
    success_rate FLOAT DEFAULT 1.0,
    use_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON agent_skills USING ivfflat (description_embedding vector_cosine_ops);

-- A/B experiments
CREATE TABLE ab_experiments (
    id TEXT PRIMARY KEY,
    name TEXT,
    variant_a TEXT,
    variant_b TEXT,
    traffic_split FLOAT DEFAULT 0.5,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

-- Research log
CREATE TABLE auto_research_log (
    id SERIAL PRIMARY KEY,
    topic TEXT NOT NULL,
    questions JSONB,
    findings_summary TEXT,
    documents_created INTEGER DEFAULT 0,
    triggered_by TEXT,  -- 'gap_detection', 'user_request', 'curriculum'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Cost tracking
CREATE TABLE llm_cost_log (
    id SERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost_usd FLOAT,
    use_case TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 5.7 Variant C Roadmap (builds on Variant A+B)

| Phase | Scope | Effort | Dependencies |
|-------|-------|--------|--------------|
| **C1** | Skill Library (store + retrieve + discover) | 4 days | B-complete |
| **C2** | DSPy-lite Prompt Optimizer (collect + propose + A/B test) | 5 days | A1 (feedback) |
| **C3** | STORM-lite Researcher (knowledge gap detection + research) | 4 days | A3 (Agentic RAG) |
| **C4** | Self-Play Evaluator (multi-candidate + pairwise judging) | 3 days | B2 (tools) |
| **C5** | Curriculum Generator (propose tasks + self-test) | 3 days | C1 |
| **C6** | Cost Optimizer (token tracking + budget routing) | 2 days | A5 (router) |
| **C7** | Autonomous Research Scheduler (hourly gap detection + research) | 3 days | C3 |
| **C8** | Learning Dashboard (all metrics, experiments, skills) | 4 days | C1-C7 |

**Total Variant C only: ~6-8 weeks. Total A+B+C: ~16-20 weeks.**

---

## 6. Variant Comparison Matrix

### 6.1 Feature Comparison

| Feature | Variant A | Variant B | Variant C |
|---------|-----------|-----------|-----------|
| Feedback collection (👍/👎) | ✅ | ✅ | ✅ |
| Self-Refine (critique loop) | ✅ | ✅ | ✅ |
| Agentic RAG (self-correcting) | ✅ | ✅ | ✅ |
| Quality-based LLM routing | ✅ | ✅ | ✅ |
| Performance monitoring | ✅ | ✅ | ✅ |
| RAG chunk learning | ✅ | ✅ | ✅ |
| Tool-use (Ollama native) | ❌ | ✅ | ✅ |
| ReAct agent loop | ❌ | ✅ | ✅ |
| Constitutional AI | ❌ | ✅ | ✅ |
| Reflexion (learn from failures) | ❌ | ✅ | ✅ |
| Specialized agents (CRM/Calendar) | ❌ | ✅ | ✅ |
| Autonomous prompt optimization | ❌ | ❌ | ✅ |
| Skill discovery & library | ❌ | ❌ | ✅ |
| Auto-research (knowledge gaps) | ❌ | ❌ | ✅ |
| Self-play evaluation | ❌ | ❌ | ✅ |
| Cost optimization | ❌ | ❌ | ✅ |
| Curriculum generation | ❌ | ❌ | ✅ |

### 6.2 Resource Comparison

| Metric | Variant A | Variant B | Variant C |
|--------|-----------|-----------|-----------|
| **New code lines** | ~630 | ~1680 | ~2850 |
| **New files** | 4 | 8 | 13 |
| **New DB tables** | 4 | 7 | 11 |
| **Timeline** | 4-5 weeks | 8-10 weeks | 16-20 weeks |
| **RAM overhead** | ~50 MB | ~100 MB | ~200 MB |
| **LLM calls per request** | 1-3 | 3-8 | 5-15 |
| **Latency impact** | +0.5-1s | +2-5s | +3-10s |
| **External dependencies** | None | None | Optional (web search) |
| **Minimum model size** | gemma4:e2b (3.2GB) | qwen3.5 (9.9GB) | qwen3.5 (9.9GB) |
| **Works on TariStation2** | ✅ (with smaller model) | ⚠️ (tight RAM) | ❌ (needs SintAItion) |

### 6.3 Quality Impact Estimate

| Quality Dimension | Variant A | Variant B | Variant C |
|-------------------|-----------|-----------|-----------|
| **Response quality** | +30-40% | +50-60% | +60-75% |
| **RAG relevance** | +25% | +35% | +45% |
| **Task success rate** | — | +40% (tool-use) | +55% (skill reuse) |
| **Alignment/safety** | Unchanged | +Constitutional AI | +Constitutional AI |
| **Knowledge freshness** | Unchanged | Unchanged | +Auto-research |
| **Prompt quality** | Unchanged | Unchanged | +A/B optimization |
| **Cost efficiency** | Unchanged | Unchanged | +Budget routing |

### 6.4 Risk Comparison

| Risk | Variant A | Variant B | Variant C |
|------|-----------|-----------|-----------|
| Implementation complexity | ⭐ Low | ⭐⭐⭐ Medium | ⭐⭐⭐⭐⭐ High |
| Debugging difficulty | ⭐ Easy | ⭐⭐⭐ Medium | ⭐⭐⭐⭐ Hard |
| Latency regression | ⭐ Minimal | ⭐⭐⭐ Noticeable | ⭐⭐⭐⭐ Significant |
| Optimization drift | ⭐⭐ Low (EMA dampens) | ⭐⭐⭐ Medium | ⭐⭐⭐⭐ High (auto changes) |
| Data privacy | ⭐ Local only | ⭐ Local only | ⭐⭐ Web search leaks |
| Runaway costs | ⭐ None | ⭐ None | ⭐⭐⭐ Cloud API spend |

---

## 7. Unified Roadmap — Telescoping Implementation

> **Key principle:** Each phase delivers value independently. Stop at any phase and the system is useful.

```
PHASE 1: Foundation (Variant A - Core)          WEEKS 1-2
├─ A1: Feedback buttons (👍/👎)                    ████
├─ A2: Self-Refine wrapper                        ██
├─ A3: Agentic RAG (grade+rewrite+retry)          ████
└─ MILESTONE: 25% quality improvement ✅

PHASE 2: Optimization (Variant A - Analytics)    WEEKS 3-5
├─ A4: Performance monitor                        ████
├─ A5: Quality router (bandit)                    ████
├─ A6: RAG chunk learner                          ████
├─ A7: Learning dashboard (Web UI)                ████
└─ MILESTONE: 35% quality + auto-routing ✅

──── DECISION GATE 1: Continue to Variant B? ────

PHASE 3: Tools (Variant B - Foundation)          WEEKS 6-8
├─ B1: Tool registry + schemas                   ████
├─ B2: ReAct loop (Ollama tool-use)               ██████
├─ B3: Agent orchestrator (state machine)         ████
├─ B4: Constitutional AI check                    ████
└─ MILESTONE: Tool-use + safety layer ✅

PHASE 4: Intelligence (Variant B - Learning)     WEEKS 9-11
├─ B5: Reflexion store                            ████
├─ B6: Specialized agents (CRM, Calendar)         ██████
├─ B7: Tool execution analytics                   ████
└─ MILESTONE: 55% quality + learns from mistakes ✅

──── DECISION GATE 2: Continue to Variant C? ────

PHASE 5: Autonomy (Variant C - Discovery)        WEEKS 12-15
├─ C1: Skill library                              ██████
├─ C2: DSPy-lite prompt optimizer                 ██████
├─ C3: STORM-lite researcher                      ██████
├─ C5: Curriculum generator                       ████
└─ MILESTONE: Autonomous skill learning ✅

PHASE 6: Production (Variant C - Hardening)      WEEKS 16-20
├─ C4: Self-play evaluator                        ████
├─ C6: Cost optimizer                             ████
├─ C7: Autonomous research scheduler              ████
├─ C8: Full learning dashboard                    ██████
└─ MILESTONE: Full autonomous system ✅
```

### 7.1 Decision Gates

| Gate | When | Question | Go/No-Go Criteria |
|------|------|----------|-------------------|
| **Gate 1** | After Phase 2 | "Is quality routing + feedback loop delivering value?" | ≥20 feedback entries/week, measurable quality delta |
| **Gate 2** | After Phase 4 | "Is tool-use and reflexion improving task completion?" | ≥50% tool-use success rate, reflections reducing repeated errors |

---

## 8. AutoResearch (Karpathy) — Deep Dive

> **When to read:** Specifically evaluating the Karpathy AutoResearch pattern from `rag-memory-extended-research.md` §6b.

### 8.1 What It Is

AutoResearch (Andrej Karpathy, 2024) proposes an autonomous agent that:
1. Takes a research question
2. Designs experiments to answer it
3. Runs experiments (RAG queries, benchmarks, A/B tests)
4. Analyzes results
5. Publishes findings (adds to knowledge base)
6. Generates new research questions based on findings
7. Repeats

### 8.2 How It Maps to Taris

| AutoResearch Step | Taris Implementation | Variant |
|-------------------|---------------------|---------|
| Research question generation | `identify_knowledge_gaps()` — analyze failed RAG queries | C |
| Experiment design | `generate_curriculum()` — propose test tasks | C |
| Experiment execution | Agent loop with tools (ReAct) | B |
| Result analysis | `optimize_provider_routing()` + `check_experiment_results()` | A + C |
| Publication | `add_document()` to RAG knowledge base | C |
| New question generation | Gap detection → next research cycle | C |

### 8.3 Practical AutoResearch for Taris

```python
# Autonomous research cycle (runs weekly)
def auto_research_cycle():
    """Karpathy-inspired: identify gaps → research → store → measure."""
    researcher = TarisResearcher()
    
    # 1. Identify knowledge gaps from user interactions
    topics = researcher.identify_knowledge_gaps()
    log.info(f"[AutoResearch] Found {len(topics)} knowledge gaps: {topics}")
    
    for topic in topics:
        # 2. Research the topic
        report = researcher.research_topic(topic)
        
        # 3. Log the research
        store.log_auto_research(topic, report)
        
        # 4. Notify admin
        notify_admin(f"📚 Auto-research completed: {topic}\n{report[:200]}...")
    
    # 5. Generate new research questions from findings
    new_questions = researcher.generate_followup_questions(topics)
    store.queue_research_topics(new_questions)
```

### 8.4 AutoResearch Applicability Assessment

| Criterion | Score | Comment |
|-----------|-------|---------|
| **Data availability** | ⭐⭐⭐⭐ | Taris has query logs, RAG logs, feedback — rich signal for gap detection |
| **Execution capability** | ⭐⭐⭐ | Can query RAG + web via N8N, but limited experimentation sandbox |
| **Evaluation quality** | ⭐⭐⭐ | Depends on feedback collection (Variant A prerequisite) |
| **Knowledge storage** | ⭐⭐⭐⭐⭐ | pgvector RAG is ideal for storing research findings |
| **Loop closure** | ⭐⭐⭐⭐ | Can verify: "did new knowledge improve answer quality?" |
| **Hardware fit** | ⭐⭐⭐⭐ | Runs on SintAItion (48GB RAM). Background scheduling avoids user-facing latency |
| **Solo dev feasibility** | ⭐⭐⭐⭐ | ~250 lines for STORM-lite + ~150 for scheduler = manageable |

**Verdict:** AutoResearch is **highly applicable** to Taris as a Variant C component. It directly addresses the "knowledge freshness" gap that neither Variant A nor B solves. The key prerequisite is Variant A feedback collection (to identify which queries have poor results).

---

## 9. Hardware Constraints & Model Selection

### 9.1 Per-Variant Model Requirements

| Variant | Minimum Model | Recommended Model | GPU VRAM Required |
|---------|--------------|-------------------|-------------------|
| A | gemma4:e2b (3.2 GB) | qwen3.5:latest (9.9 GB) | 4-10 GB |
| B | qwen3.5:latest (9.9 GB) | qwen3.5:latest + gemma4:e2b as judge | 10-14 GB |
| C | qwen3.5:latest (9.9 GB) | qwen3.5 + gemma4:e2b + research model | 10-16 GB |

### 9.2 Hardware Fit

| Target | RAM | GPU | Variant A | Variant B | Variant C |
|--------|-----|-----|-----------|-----------|-----------|
| **SintAItion** | 48 GB | AMD 890M 16GB shared | ✅ Full | ✅ Full | ✅ Full |
| **TariStation2** | 7.6 GB | None (CPU) | ⚠️ Limited (e2b only) | ❌ Too tight | ❌ No |
| **OpenClawPI2** | 8 GB | None | ⚠️ Limited (e2b only) | ❌ No | ❌ No |

### 9.3 Latency Budget

| Pipeline Stage | Today | Variant A | Variant B | Variant C |
|----------------|-------|-----------|-----------|-----------|
| STT | 1.1s | 1.1s | 1.1s | 1.1s |
| RAG | 0.3s | 0.5s (+grade) | 0.5s | 0.5s |
| LLM (response) | 4.7s | 5.2s (+refine) | 7-12s (+tools+const.) | 8-15s (+self-play) |
| TTS | 1.2s | 1.2s | 1.2s | 1.2s |
| **Total** | **7.3s** | **8.0s** | **10-15s** | **11-18s** |

> **Mitigation:** Use Self-Refine and Constitutional AI only for complex/high-stakes queries. Simple queries skip to reduce latency.

---

## 10. Safety & Guardrails

| Risk | Variant A Mitigation | Variant B Mitigation | Variant C Mitigation |
|------|---------------------|---------------------|---------------------|
| **Optimization drift** | EMA dampens sudden changes; 24h cool-down between switches | + Constitutional AI catches drift | + Skill library rollback |
| **Feedback gaming** | Min 10 samples; weight recent higher | + Reflexion validates via reflection | + A/B testing with control group |
| **Runaway costs** | N/A (local only) | N/A (local only) | Hard daily budget cap; auto-switch to local |
| **Prompt injection** | Sanitize feedback text | + Constitutional check blocks injection | + Research content sandboxed |
| **Knowledge pollution** | N/A | N/A | Auto-research flagged for admin review before RAG injection |
| **Model switching instability** | 24h cool-down | + Reflection evaluates switch quality | + A/B test before permanent switch |
| **Privacy** | All data local | All data local | Web search may leak queries → opt-in only |
| **Admin override** | `OPTIMIZER_LOOPS=quality,perf` | + `AGENT_MODE=disabled` | + `AUTO_RESEARCH=disabled` |

---

## 11. Decision Points for Owner

| # | Question | Options | Recommended | Impacts |
|---|----------|---------|-------------|---------|
| **D1** | Which variant to start with? | A (Pragmatic) / B (Agentic) / C (Full) | **A** (then evolve) | Timeline, complexity |
| **D2** | Feedback UI format? | 👍/👎 (simple) / 1-5 stars (detailed) / both | **👍/👎** (lower friction) | Data quality |
| **D3** | Optimization autonomy? | Fully automatic / Admin-approval required | **Auto with admin alerts** | Speed vs safety |
| **D4** | Self-Refine on all responses or complex only? | All / Complex only (>20 words) | **Complex only** (latency) | Latency vs quality |
| **D5** | Constitutional AI principles? | Approve proposed 6 principles / customize | **Approve + add custom** | Alignment scope |
| **D6** | Tool-use models? | Ollama native tool-use / prompt-based JSON | **Native** (qwen3.5 supports) | Reliability |
| **D7** | A/B testing scope? | System prompts only / also models+providers | **Prompts first**, models later | Experimentation breadth |
| **D8** | Auto-research triggers? | Weekly scheduled / on-demand / gap-detection | **Gap-detection** (data-driven) | Knowledge freshness |
| **D9** | Learning data retention? | Forever / 90-day rolling / configurable | **Configurable, default 180d** | Storage vs learning |
| **D10** | Target for learning system? | SintAItion only / both targets | **SintAItion only** (hardware) | Deployment scope |

---

## 12. Relationship to Other Concept Documents

| Document | Relationship |
|----------|-------------|
| `taris-n8n-crm-integration.md` §4C | **Supersedes** — this document replaces the original §4C with expanded variants |
| `taris-n8n-crm-integration.md` §4B | **Extends** — Variant B builds on the agentic loop architecture proposed in §4B |
| `rag-memory-architecture.md` | **Complementary** — Variant A's Agentic RAG builds on the RAG pipeline described there |
| `rag-memory-extended-research.md` §6b | **Implements** — Variant C implements the AutoResearch concept described in §6b |
| `taris-n8n-crm-integration.md` §10 | **Depends** — Variant C's STORM-lite requires N8N integration (Phase 1 from §10) for web search |

---

→ [Back to Integration Concept](taris-n8n-crm-integration.md) · [RAG Architecture](rag-memory-architecture.md) · [TODO.md](../TODO.md)
