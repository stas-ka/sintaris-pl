# Review-Auftrag: RAG & Memory Architecture Research

**Datum:** 2026-03-23  
**Branch:** `Taris-UI-POC`  
**Commit:** `b938b7e`  
**Autor:** AI Architecture Analysis (5 Sitzungen, ~50+ Turns)

---

## 1. Zusammenfassung

Über 5 Arbeitssitzungen wurde ein umfassendes Architekturkonzept für RAG (Retrieval-Augmented Generation) und Multi-Level Memory für die Taris-Plattform erstellt. Das Ergebnis umfasst drei Deliverables:

| Deliverable | Datei | Umfang | Status |
|---|---|---|---|
| Hauptkonzept | `concept/rag-memory-architecture.md` | ~1000 Zeilen | Fertig |
| Erweiterte Recherche | `concept/rag-memory-extended-research.md` | ~920 Zeilen | Fertig |
| Roadmap-Items | `TODO.md` §23 | 9 Items (23.1–23.9) | Eingetragen |

**Gesamtumfang:** ~1945 neue Zeilen in 3 Dateien.

---

## 2. Gelieferte Artefakte

### 2.1 Hauptkonzept — `concept/rag-memory-architecture.md`

**Inhalt:**
- **§1** Executive Summary — Empfehlung für Variant C: Hybrid Tiered RAG (Score 4.15/5.0)
- **§2** Ist-Analyse — bestehende Taris-Komponenten (FTS5, sqlite-vec Schema, 6 LLM-Provider, DataStore-Adapter)
- **§3** Anforderungskonsolidierung — abgeleitet aus TODO.md §§2, 3, 4, 9, 10
- **§4** State-of-the-Art — Forschungsüberblick zu RAG-Frameworks, Vektor-DBs, Memory-Systemen
- **§5** 5 Architekturvarianten im Vergleich:

| Variante | Beschreibung | Score |
|---|---|---|
| A — FTS5 Only | Nur Keyword-Suche, kein Vektor | 2.70 |
| B — Full Vector | Vektor-first, hoher RAM-Bedarf | 3.40 |
| **C — Hybrid Tiered** | **FTS5 + optionaler Vektor, hardware-adaptiv** | **4.15 → 4.40** |
| D — Cloud RAG | Vollständig remote (Google Grounding, OpenAI) | 3.25 |
| E — Framework-based | LangChain/LlamaIndex (heavy dependencies) | 2.80 |

- **§6** Detailliertes Design — DB-Schema (SQLite + PostgreSQL), Code-Beispiele, 3-Tier Memory (Short/Middle/Long), Compaction-Pipeline
- **§7** Implementierungsplan mit 6 Phasen
- **§8** Konsolidierte TODO-Liste
- **§9** Risikoanalyse

### 2.2 Erweiterte Recherche — `concept/rag-memory-extended-research.md`

**Internet-Recherche über 8 Runden, 16+ URLs.** Ergebnisse:

| Thema | Ergebnis |
|---|---|
| **MemGPT/Letta** | Virtuelles Kontextmanagement (OS-Metapher). Adoption: Memory-Compaction-Pattern → Taris Memory-Manager |
| **Mem0** | Multi-Level Memory (Graph + Vektor). Adoption: Short/Middle/Long-Tier-Konzept, Auto-Compaction |
| **RAPTOR** | Tree-basierte hierarchische Retrieval. Adoption: Cluster-Summarization für Long-Term Memory |
| **LanceDB** | Embedded-Vektor-DB (Rust/Arrow). Empfehlung: Pi 5 Laptop-Tier (ersetzt sqlite-vec dort) |
| **ChromaDB** | In-Memory, Server-Mode möglich. Bewertung: zu hoher RAM für Pi 3, Option für Server-Tier |
| **Qdrant** | Production-grade, Rust. Empfehlung: Server/Cloud-Tier |
| **hnswlib** | Ultra-lightweight HNSW-only. Empfehlung: Pi 3 Tier (kleinster Footprint) |
| **Docling (IBM)** | Multi-Format-Parser (PDF/DOCX/PPTX/HTML → Markdown). Empfehlung: Ersatz für aktuelle Parsing-Pipeline |
| **Google Grounding** | Server-side RAG over Gemini API mit Google Search. Empfehlung: Optionale Remote-Quelle |
| **Karpathy nanochat** | Edge LLM Fine-Tuning. Empfehlung: Domain-spezifische Modelle auf Pi 5+ |
| **Worksafety-superassistant** | n8n + PostgreSQL + pgvector Referenzarchitektur. Analyse: 8 Patterns übernehmen, 7 Anti-Patterns vermeiden |

**Score-Anhebung:** Variant C von 4.15 → 4.40 durch Integration der Forschungsergebnisse.

### 2.3 TODO.md §23 — Forschungs-Roadmap

9 neue Items zur praktischen Validierung der Architektur:

| Item | Beschreibung |
|---|---|
| 23.1 | OpenClaw auf Laptop installieren — lokale Entwicklung + RAG-Vergleiche |
| 23.2 | n8n + PostgreSQL-Klon auf Laptop — Worksafety-Baseline replizieren |
| 23.3 | Karpathy nanochat Framework — Edge LLM Fine-Tuning auf OpenClaw |
| 23.4 | Hybrid RAG auf Google Grounding — Gemini API evaluieren vs lokal |
| 23.5 | Worksafety-DB + n8n auf OpenClaw klonen |
| 23.6 | Worksafety-DB als Testkorpus für Google Grounding vorbereiten |
| 23.7 | Research Environment konfigurieren — Evaluierungsmetriken (Precision, Recall, Latenz, Kosten) |
| 23.8 | Worksafety-Workflow auf OpenClaw mit Google Grounding implementieren |
| 23.9 | Vergleich Hybrid RAG vs Google Grounding — identische Queries, Qualität/Latenz/Kosten messen |

---

## 3. Review-Checkliste

Bitte prüfe folgende Punkte:

### 3.1 Architektur-Design

- [ ] **Variant C als Empfehlung** — Ist die Hybrid-Tiered-Architektur die richtige Wahl für die Taris Hardware-Tiers (Pi 3 → Pi 5 → Server)?
- [ ] **3-Tier Memory** (Short/Middle/Long) — Ist das Compaction-Modell (Context → Summarize → Merge) praktikabel?
- [ ] **FTS5 als universelle Baseline** — Reicht FTS5 auf Pi 3 als alleiniger Retrieval-Mechanismus aus?
- [ ] **sqlite-vec vs hnswlib** — Soll Pi 3 sqlite-vec oder hnswlib für optionalen Vektor-Support verwenden?
- [ ] **DataStore Protocol Erweiterung** — Passt die vorgeschlagene API-Erweiterung (`search_hybrid()`, `append_memory()`, `compact_memory()`) zum bestehenden Adapter-Pattern?

### 3.2 Technologie-Entscheidungen

- [ ] **Docling statt aktueller Parser** — Soll die bestehende PDF/DOCX-Parsing-Pipeline durch Docling ersetzt werden?
- [ ] **LanceDB für Pi 5 Tier** — Sinnvoller Ersatz für sqlite-vec auf leistungsfähigerer Hardware?
- [ ] **Google Grounding als optionale Remote-Quelle** — Akzeptabel trotz Vendor-Abhängigkeit (Gemini API)?
- [ ] **Worksafety-Patterns** — Stimmen die 8 übernommenen und 7 abgelehnten Patterns mit unserer Architektur überein?
- [ ] **Karpathy nanochat** — Ist Edge Fine-Tuning auf Pi 5 realistisch und prioritär?

### 3.3 TODO §23 Roadmap

- [ ] **Priorisierung** — Welche der 9 Items haben die höchste Priorität?
- [ ] **Laptoptier** — Soll der Laptop als 4. Hardware-Tier (neben PicoClaw/OpenClaw/Server) fest etabliert werden?
- [ ] **Evaluierungsmetriken** (23.7) — Precision/Recall/Latenz/Kosten ausreichend oder weitere Metriken nötig?
- [ ] **Zeitrahmen** — Realistischer Zeitplan für die 9 Items?

### 3.4 Offene Fragen

- [ ] Nicht-proprietäre Anforderung — Sind alle vorgeschlagenen Komponenten wirklich vendor-neutral?
- [ ] RAM-Budget auf Pi 3 — Passt hnswlib + Vosk + Piper + Bot in 1 GB?
- [ ] Migration bestehender FTS5-Daten bei Wechsel auf Hybrid-Pipeline?
- [ ] Multi-User Document Sharing — Ausreichend spezifiziert im Konzept?

---

## 4. Nächste Schritte nach Review

1. **Review-Feedback einarbeiten** in beide Concept-Dokumente
2. **Phase 1 starten** (aus §7 Implementierungsplan): Memory-Tables + Compaction-Loop
3. **TODO §23 priorisieren** und ersten Forschungs-Sprint planen
4. **Laptop-Setup** (23.1) als Voraussetzung für weitere Experimente

---

*Commit `b938b7e` auf Branch `Taris-UI-POC` — pushed 2026-03-23.*
